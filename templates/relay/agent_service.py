#!/usr/bin/env python3
"""
SDR Flo — channel relay (reference template, generalized from the Takeoff Setter).

Capture -> reason (one brain) -> reply, for any non-gateway channel
(IG / FB / TikTok / SMS via GHL Conversations; swap send_reply() for Twilio,
Photon, or SMTP). Battle-tested invariants are baked in:

  * secret-validated inbound
  * FAIL-CLOSED tag gate (checks the CRM live, not just the webhook payload)
  * per-contact isolation (SQLite, never mix contacts)
  * continuity + destination (never restart; drive to the objective) — in the SOUL
  * dash-strip + degenerate/empty suppression + retry on bad model output
  * dry-run gate (*_LIVE=false) for validation
  * mirror every message to the spine (Supabase)

Configure via env (.env). This is a TEMPLATE: fill the TODOs, point send_reply()
at the client's channel, and load the client's SOUL + skill.
"""
import json, os, re, sqlite3, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from access_grant import commit_grant, peek_grant
from outbound import begin_outbound, mark_accepted, remember_provider_id
from copy_config import load_client_copy
from ghl_calendar import CalendarReceiptError, appointment_body, free_slots_path, parse_free_slots
from ghl_poll import fetch_inbound
from turn_engine import booking_instructions, fresh_state, run_turn

# ---- config (env) ----
def c(k, d=""): return os.environ.get(k, d)
SECRET      = c("RELAY_WEBHOOK_SECRET")
PORT        = int(c("RELAY_PORT", "8799"))
DB          = c("RELAY_DB", "/opt/sdr-flo/agent/state.db")
LOG         = c("RELAY_LOG", "/opt/sdr-flo/agent/agent.log.jsonl")
LIVE        = c("RELAY_LIVE", "false").lower() in ("1", "true", "yes")   # dry-run gate
SOUL        = Path(c("RELAY_SOUL", "/opt/sdr-flo/profile/SOUL.md")).read_text()
ENABLE_TAG  = c("RELAY_ENABLE_TAG", "ai-dm-start").lower()               # the "on" tag
# campaign keywords: a lead who OPENS with one of these is self-tagged + engaged even before the
# CRM tags them (CRM tagging races/misses). Empty = require the tag only. (Lesson: a pure tag gate
# silently blocks every lead when the CRM workflow isn't reliably tagging them.)
KEYWORDS    = [k.strip().lower() for k in c("RELAY_KEYWORDS", "").split(",") if k.strip()]
# Guard tags = INTENTIONAL kill switches ONLY. Do NOT add a tag here that some workflow mass-applies
# (a noisy "ai off"-style tag will silently mute your whole pipeline). Keep this list curated.
GUARD_TAGS  = [t.strip().lower() for t in c("RELAY_GUARD_TAGS",
                "existing-client,manual,dnd,do-not-contact").split(",")]
# ---- reasoning backend (pluggable, OpenAI-compatible) ----
# Point at ANY OpenAI-compatible endpoint: a dedicated provider API (GLM via api.z.ai, OpenRouter),
# a Codex (ai-flo -z) bridge, or a local Claude Max CLI bridge on :8787.
# LESSON (Takeoff outage): an OAuth token shared across machines rotates and DIES silently. A dedicated
# provider API KEY never expires and is single-tenant per client -> the most stable brain. Prefer it.
BRIDGE       = c("RELAY_BRIDGE", "http://127.0.0.1:8787/v1/chat/completions")
MODEL        = c("RELAY_MODEL", "glm-4.6")
BRAIN_KEY    = c("RELAY_BRAIN_KEY") or c("GLM_API_KEY") or "x"   # provider key; "x" for a no-auth local bridge
BRAIN_MAXTOK = int(c("RELAY_BRAIN_MAX_TOKENS", "1024"))
# channel send (GHL Conversations example)
GHL_API     = "https://services.leadconnectorhq.com"
GHL_PIT     = c("GHL_PIT")
GHL_MSG_TYPE = c("GHL_MSG_TYPE", "IG")   # IG | FB | TIKTOK | SMS

TOOLS_DOC = ('Return STRICT JSON only: {"reply":"<lead-facing message, empty if none>",'
             '"actions":[{"tool":"tag","tags":["..."]},{"tool":"escalate","reason":"..."}],'
             '"profile":{"name":"","situation":"","problem":"","desired_outcome":"","stage":"","notes":""}}')

def logj(o):
    o["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    open(LOG, "a").write(json.dumps(o) + "\n")

def db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS turns(contact TEXT,role TEXT,content TEXT,ts REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS profiles(contact TEXT PRIMARY KEY,data TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS engine_state(contact TEXT PRIMARY KEY, data TEXT)")
    return con

# ---- CRM (GHL) helpers — swap for the client's channel ----
def ghl(method, path, body=None):
    h = {"Authorization": f"Bearer {GHL_PIT}", "Version": "2021-04-15",
         "Accept": "application/json", "Content-Type": "application/json",
         "User-Agent": "Mozilla/5.0"}  # Cloudflare needs a browser UA or 1010
    req = urllib.request.Request(GHL_API + path,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            t = r.read().decode(); return r.status, (json.loads(t) if t else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return 0, str(e)[:200]

def contact_tags(contact):
    """Authoritative tags from the CRM (fail-closed: None on failure -> skip)."""
    s, d = ghl("GET", f"/contacts/{contact}")
    if isinstance(d, dict):
        return [str(t).strip().lower() for t in ((d.get("contact") or {}).get("tags") or [])]
    return None

def send_reply(contact, text):
    if not LIVE:
        logj({"act": "send", "dry": True, "contact": contact}); return {"ok": False, "provider_id": ""}
    if c("RELAY_SENDER", "ghl").lower() == "loop":
        try:
            provider_id = _send_loop(text)
        except Exception as exc:
            logj({"act": "send", "channel": "loop", "error": str(exc)[:160]})
            return {"ok": False, "provider_id": ""}
        return {"ok": bool(provider_id), "provider_id": provider_id or ""}
    s, d = ghl("POST", "/conversations/messages",
               {"type": GHL_MSG_TYPE, "contactId": contact, "message": text})
    # Channel fallback: the same CRM location often holds IG + SMS leads. Sending the wrong
    # type for a conversation returns 422 and the reply silently never delivers. Fall back.
    if s in (400, 422):
        for alt in ("SMS", "Email", "FB"):
            if alt == GHL_MSG_TYPE: continue
            s2, _ = ghl("POST", "/conversations/messages",
                        {"type": alt, "contactId": contact, "message": text})
            if s2 in (200, 201):
                logj({"act": "send-fallback", "type": alt, "status": s2, "contact": contact}); s = s2; break
    provider_id = ""
    if isinstance(d, dict):
        provider_id = str(d.get("messageId") or d.get("id") or "").strip()
    logj({"act": "send", "status": s, "contact": contact, "has_receipt": bool(provider_id)})
    return {"ok": s in (200, 201) and bool(provider_id), "provider_id": provider_id}

def _send_loop(text):
    phone = c("RELAY_ALLOWED_PHONE")
    sender = c("LOOP_SENDER_ID")
    key = c("LOOP_MESSAGE_API_KEY")
    if not (phone and sender and key):
        logj({"act": "send", "skipped": "loop-not-configured"}); return ""
    req = urllib.request.Request(
        "https://a.loopmessage.com/api/v1/message/send/",
        data=json.dumps({"contact": phone, "text": text, "sender": sender, "passthrough": "sdr-relay"}).encode(),
        headers={"Authorization": key, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        body = json.loads(response.read().decode() or "{}")
    provider_id = str(body.get("message_id") or body.get("id") or "").strip()
    logj({"act": "send", "channel": "loop", "status": response.status, "has_receipt": bool(provider_id)})
    return provider_id


def provider_status(provider_id):
    if not provider_id or c("RELAY_SENDER", "ghl").lower() != "loop":
        return "unknown"
    key = c("LOOP_MESSAGE_API_KEY")
    if not key:
        return "unknown"
    req = urllib.request.Request(
        f"https://a.loopmessage.com/api/v1/message/status/{provider_id}/",
        headers={"Authorization": key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            body = json.loads(response.read().decode() or "{}")
    except Exception:
        return "unknown"
    raw = str(body.get("status") or "").lower()
    if raw in ("sent", "delivered"):
        return "accepted"
    if raw in ("failed", "error"):
        return "failed"
    return "unknown"


def deliver_outbound(con, dedupe_key, contact, kind, body):
    plan = begin_outbound(con, dedupe_key, contact, kind, body)
    if plan["action"] == "blocked":
        return {"ok": False, "sent": False, "reason": "unconfirmed"}
    if plan["action"] == "readback":
        if provider_status(plan["provider_id"]) == "accepted":
            mark_accepted(con, dedupe_key)
            return {"ok": True, "sent": False, "already": True, "provider_id": plan["provider_id"]}
        return {"ok": False, "sent": False, "reason": "unconfirmed"}
    try:
        receipt = send_reply(contact, plan["body"]) or {}
    except Exception as exc:
        logj({"act": "send", "error": str(exc)[:160]})
        return {"ok": False, "sent": False, "reason": "send_failed"}
    provider_id = str(receipt.get("provider_id") or "").strip() if isinstance(receipt, dict) else ""
    if not provider_id:
        return {"ok": False, "sent": False, "reason": "no_receipt"}
    remember_provider_id(con, dedupe_key, provider_id)
    if provider_status(provider_id) != "accepted":
        return {"ok": False, "sent": False, "reason": "readback"}
    mark_accepted(con, dedupe_key)
    return {"ok": True, "sent": True, "provider_id": provider_id}


def add_tags(contact, tags):
    if tags and LIVE: ghl("POST", f"/contacts/{contact}/tags", {"tags": tags})
    logj({"act": "tag", "contact": contact, "add": tags, "dry": not LIVE})

def escalate(contact, reason):
    logj({"act": "escalate", "contact": contact, "reason": reason})
    add_tags(contact, ["ai-escalated"])
    # TODO: alert the operator (Slack/Telegram/iMessage)

# ---- structured-payload guard (NEVER leak raw model JSON to a lead) ----
# Field lesson: when the model emits malformed/fenced JSON, a naive fallback can send the whole
# {"reply":...,"actions":...,"profile":...} blob straight to the lead. Extract the real reply, and
# if it STILL looks structured, block the send entirely (clean_text returns "" -> send_reply skips).
def _looks_structured_payload(t):
    if not isinstance(t, str): return False
    probe = t.strip()
    if not probe: return False
    if probe[0] in "[{": return True
    lowered = probe.lower()
    return any(m in lowered for m in ('"reply"', "'reply'", '"actions"', "'actions'",
                                      '"profile"', "'profile'", '"contact_info"', "'contact_info'"))

def _extract_reply_from_structured(value, depth=0):
    if depth > 4 or value is None: return ""
    if isinstance(value, dict): return _extract_reply_from_structured(value.get("reply", ""), depth + 1)
    if not isinstance(value, str): return str(value).strip() if value else ""
    text = value.strip()
    if not text: return ""
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S | re.I)
    if fenced: text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "reply" in parsed: return _extract_reply_from_structured(parsed.get("reply", ""), depth + 1)
        if isinstance(parsed, str): return _extract_reply_from_structured(parsed, depth + 1)
        return ""
    except Exception: pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict) and "reply" in parsed: return _extract_reply_from_structured(parsed.get("reply", ""), depth + 1)
        except Exception: pass
    return text

# ---- output hygiene ----
def clean_text(t):
    if not t: return t
    t = _extract_reply_from_structured(t)
    if _looks_structured_payload(t):
        logj({"error": "blocked-structured-reply", "preview": str(t)[:160]})
        return ""
    urls = re.findall(r"https?://\S+", t)
    isos = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", t)
    held = urls + isos
    for k, u in enumerate(held): t = t.replace(u, "\x00%d\x00" % k)
    t = t.replace("—", ", ").replace("–", ", ")
    t = t.replace(" -- ", ", ").replace(" - ", ", ")
    t = re.sub(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])", " ", t)
    t = re.sub(r"[ ]{2,}", " ", t)
    for k, u in enumerate(held): t = t.replace("\x00%d\x00" % k, u)
    return t.strip()

# ---- the brain ----
def think(hist, inbound, profile):
    prof = ("\n\n## WHAT YOU ALREADY KNOW (never re-ask):\n" + json.dumps(profile)) if profile else ""
    tools = TOOLS_DOC
    if c("GHL_CALENDAR_ID") and c("GHL_LOCATION_ID"):
        tools += "\n" + booking_instructions(_required_fields())
    sysmsg = SOUL + prof + "\n\n## CURRENT CONVERSATION\nYou are MID conversation. Continue, never restart.\n" + tools
    msgs = [{"role": "system", "content": sysmsg}] + hist + [{"role": "user", "content": inbound}]
    for _ in range(2):  # retry on empty/degenerate
        content = ""
        try:
            req = urllib.request.Request(BRIDGE, data=json.dumps(
                {"model": MODEL, "messages": msgs, "temperature": 0.5, "max_tokens": BRAIN_MAXTOK}).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {BRAIN_KEY}"}, method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:
                _m = json.loads(r.read().decode())["choices"][0]["message"]
                # reasoning models (e.g. glm-5.2) may put text in reasoning_content; prefer content
                content = ((_m.get("content") or _m.get("reasoning_content") or "")).strip()
        except Exception as e:
            logj({"error": "think", "detail": str(e)[:160]})
        if not content: continue
        mt = re.search(r"\{.*\}", content, re.S)
        try: out = json.loads(mt.group(0)) if mt else {"reply": content, "actions": []}
        except Exception: out = {"reply": content, "actions": []}
        rep = (out.get("reply") or "").strip()
        if len(re.sub(r"[^A-Za-z0-9]", "", rep)) >= 3: return out  # reject "?", empty
        logj({"error": "degenerate", "reply": rep[:60]})
    return {"reply": "", "actions": []}

def _csv(name):
    return tuple(item.strip() for item in c(name, "").split(",") if item.strip())


def _client_copy():
    return load_client_copy(c("RELAY_COPY_FILE"))


def _required_fields():
    raw = _csv("RELAY_REQUIRED_FIELDS")
    if raw:
        return raw
    required = _client_copy().get("required") or []
    return tuple(required) or ("project", "location", "timeline", "intent")


def _load_engine(con, contact):
    row = con.execute("SELECT data FROM engine_state WHERE contact=?", (contact,)).fetchone()
    state = fresh_state()
    if not row:
        legacy = con.execute("SELECT data FROM profiles WHERE contact=?", (contact,)).fetchone()
        if legacy:
            try:
                saved = json.loads(legacy[0])
                if isinstance(saved, dict):
                    state["profile"] = {k: v for k, v in saved.items() if isinstance(v, str)}
            except Exception:
                pass
        return state
    try:
        saved = json.loads(row[0])
    except Exception:
        return state
    if isinstance(saved, dict):
        for key in state:
            if key in saved:
                state[key] = saved[key]
    return state


def _save_engine(con, contact, state):
    con.execute("INSERT OR REPLACE INTO engine_state VALUES(?,?)", (contact, json.dumps(state)))
    con.execute("INSERT OR REPLACE INTO profiles VALUES(?,?)", (contact, json.dumps(state.get("profile") or {})))
    con.commit()


# ---- handle ----
def pick(p, names):
    for n in names:
        v = p.get(n)
        if isinstance(v, str) and v.strip(): return v.strip()
    return ""

def _same_phone(left, right):
    digits = lambda value: "".join(ch for ch in str(value or "") if ch.isdigit())
    a, b = digits(left), digits(right)
    return bool(a and b and a[-10:] == b[-10:])


def handle(p):
    contact = pick(p, ["contact_id", "contactId", "id"])
    text = pick(p, ["text", "message", "body"])
    if not (contact and text):
        logj({"skip": "no-route"}); return {"ok": True, "skipped": True}
    allowed_phone = c("RELAY_ALLOWED_PHONE")
    inbound_phone = pick(p, ["phone"])
    if allowed_phone and inbound_phone and not _same_phone(allowed_phone, inbound_phone):
        logj({"skip": "phone", "contact": contact}); return {"ok": True, "skipped": "phone"}
    con = db()
    state = _load_engine(con, contact)
    if p.get("consented") is True:
        state["consented"] = True
        if not state.get("consented_at"):
            state["consented_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _save_engine(con, contact, state)
    provider_time = pick(p, ["occurredAt", "dateAdded", "receivedAt"])
    if state.get("consented_at") and provider_time and provider_time < state["consented_at"] and p.get("consented") is not True:
        event_id = pick(p, ["providerEventId", "messageId", "eventId", "event_id"])
        if event_id and event_id not in state["handled_events"]:
            state["handled_events"].append(event_id)
            _save_engine(con, contact, state)
        logj({"skip": "before-consent", "contact": contact}); return {"ok": True, "skipped": "before-consent", "sent": False}
    tags = None if state.get("consented") else contact_tags(contact)
    if tags is None and not state.get("consented"):
        logj({"skip": "tag-fetch-failed", "contact": contact}); return {"ok": True, "skipped": "tag-fetch-failed"}
    tags = tags or []
    if any(t in tags for t in GUARD_TAGS):
        logj({"skip": "guard", "contact": contact}); return {"ok": True, "skipped": "guard"}
    if not state.get("consented") and ENABLE_TAG and ENABLE_TAG not in tags:
        # Keyword-OR-tag: if they OPENED with a campaign keyword, self-tag + engage (don't wait on
        # the CRM to tag them). Otherwise skip — this is what keeps the bot out of personal DMs.
        if KEYWORDS and any(k in (text or "").lower() for k in KEYWORDS):
            add_tags(contact, [ENABLE_TAG]); tags.append(ENABLE_TAG)
            logj({"selftag": ENABLE_TAG, "contact": contact})
        else:
            logj({"skip": "not-keyword-lead", "contact": contact}); return {"ok": True, "skipped": "not-keyword-lead"}
    event_id = pick(p, ["providerEventId", "messageId", "eventId", "event_id"])
    if event_id and event_id in state["handled_events"]:
        logj({"skip": "duplicate", "contact": contact}); return {"ok": True, "duplicate": True, "sent": False}
    con.execute("INSERT INTO turns VALUES(?,?,?,?)", (contact, "user", text, time.time())); con.commit()
    hist = [{"role": r, "content": cc} for r, cc in con.execute(
        "SELECT role,content FROM turns WHERE contact=? ORDER BY ts", (contact,)).fetchall()][-40:]
    tools_enabled = bool(c("GHL_CALENDAR_ID") and c("GHL_LOCATION_ID"))
    captured = {}

    def brain(inbound, profile, offered):
        del offered
        captured["out"] = think(hist[:-1], inbound, profile)
        return captured["out"]

    def slots_fn():
        now_ms = int(time.time() * 1000)
        path = free_slots_path(c("GHL_CALENDAR_ID"), now_ms, now_ms + 14 * 86_400_000, c("GHL_CALENDAR_TIMEZONE", "America/New_York"))
        status, data = ghl("GET", path)
        if status != 200:
            raise CalendarReceiptError("free slots were not accepted")
        return parse_free_slots(data)

    def request_for(slot):
        return appointment_body(
            calendar_id=c("GHL_CALENDAR_ID"),
            location_id=c("GHL_LOCATION_ID"),
            contact_id=contact,
            start_time=slot,
            slot_minutes=int(c("GHL_SLOT_MINUTES", "30") or "30"),
            title=c("GHL_APPOINTMENT_TITLE", "Consultation"),
            notify=c("GHL_APPOINTMENT_NOTIFY", "false").lower() in ("1", "true", "yes"),
        )

    def book_fn(slot):
        if not LIVE:
            raise CalendarReceiptError("relay is not live")
        body = request_for(slot)
        status, data = ghl("POST", "/calendars/events/appointments", body)
        if status not in (200, 201) or not isinstance(data, dict):
            raise CalendarReceiptError("appointment was not accepted")
        return data

    state, effect = run_turn(
        state=state,
        event_id=event_id,
        text=text,
        brain=brain,
        slots_fn=slots_fn,
        book_fn=book_fn,
        required=_required_fields(),
        in_area=_csv("RELAY_IN_AREA") or tuple(_client_copy().get("in_area") or []),
        out_of_area=_csv("RELAY_OUT_OF_AREA") or tuple(_client_copy().get("out_of_area") or []),
        tools_enabled=tools_enabled,
        appointment_request=request_for,
        templates=_client_copy(),
    )
    _save_engine(con, contact, state)
    for action in (captured.get("out") or {}).get("actions") or []:
        if action.get("tool") == "tag":
            add_tags(contact, action.get("tags") or [])
        elif action.get("tool") == "escalate":
            escalate(contact, action.get("reason", ""))
    raw_reply = effect.get("reply") or ""
    reply = clean_text(raw_reply) if state.get("stage") == "open" else raw_reply
    if effect.get("opt_out"):
        add_tags(contact, ["do-not-contact"])
    if effect.get("booked") and (not effect.get("appointment_id") or str(effect.get("appointment_id")) not in reply):
        reply = ""
        effect = {**effect, "send": False, "booked": False}
    sent = False
    if effect.get("send") and reply:
        if c("RELAY_SENDER", "ghl").lower() == "loop":
            delivered = deliver_outbound(con, f"reply:{event_id or 'none'}", contact, "reply", reply)
            sent = bool(delivered.get("ok"))
        else:
            send_reply(contact, reply)
            sent = True
        if sent:
            con.execute("INSERT INTO turns VALUES(?,?,?,?)", (contact, "assistant", reply, time.time())); con.commit()
    logj({"handled": True, "contact": contact, "reply": (reply or "")[:120], "booked": bool(effect.get("booked"))})
    return {"ok": True, "reply": reply if sent or not effect.get("booked") else "", "sent": sent, "duplicate": False, "booked": bool(effect.get("booked") and sent)}

def _phone_last4(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 4:
        return digits
    return digits[-4:] if len(digits) >= 10 else ""


def accept_public(p, action: str):
    grant = peek_grant(
        db(),
        pick(p, ["accessCode", "access_code"]),
        c("DEMO_ACCESS_SECRET"),
        pick(p, ["rateKey", "rate_key"]) or action,
        LIVE,
    )
    if not grant["ok"]:
        return grant
    phrase = pick(p, ["phrase"])
    expected_phrase = c("OPT_IN_PHRASE").strip()
    if not expected_phrase or phrase.upper() != expected_phrase.upper() or _phone_last4(pick(p, ["last4"])) != _phone_last4(c("RELAY_ALLOWED_PHONE")):
        return {"ok": False, "httpStatus": 400, "sent": False, "message": "Opt-in phrase or last four digits did not match. Nothing was sent."}
    return {"ok": True, "code_hash": grant.get("code_hash", "")}


def _mark_consent(con, contact):
    state = _load_engine(con, contact)
    state["consented"] = True
    if not state.get("consented_at"):
        state["consented_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["stage"] = "awaiting_reply"
    _save_engine(con, contact, state)


def accept_opt_in(p):
    gate = accept_public(p, "opt-in")
    if not gate.get("ok"):
        return gate
    copy = _client_copy()
    opener = str(copy.get("opener") or "").strip()
    if "?" not in opener:
        return {"ok": False, "httpStatus": 503, "sent": False, "message": "The opener does not invite a reply. Nothing was sent."}
    contact = c("RELAY_CONTACT_ID") or pick(p, ["contactId", "contact_id"])
    code = pick(p, ["accessCode", "access_code"])
    if not contact or not code:
        return {"ok": False, "httpStatus": 503, "sent": False, "message": "The relay has no contact. Nothing was sent."}
    con = db()
    delivered = deliver_outbound(con, f"opener:{gate['code_hash']}", contact, "opener", opener)
    if not delivered.get("ok"):
        return {"ok": False, "httpStatus": 502, "sent": False, "message": "The opener was not confirmed by the provider. Nothing was marked consented."}
    _mark_consent(con, contact)
    commit_grant(con, code)
    if delivered.get("sent"):
        con.execute("INSERT INTO turns VALUES(?,?,?,?)", (contact, "assistant", opener, time.time()))
        con.commit()
    return {"ok": True, "httpStatus": 200, "sent": bool(delivered.get("sent")), "reply": opener, "booked": False}


def accept_pull(p):
    gate = accept_public(p, "pull")
    if not gate.get("ok"):
        return gate
    conversation_id = c("GHL_CONVERSATION_ID")
    if not conversation_id:
        return {"ok": False, "httpStatus": 503, "sent": False, "message": "The relay has no conversation to read. Nothing was sent."}

    def ghl_get(path):
        return ghl("GET", path)

    try:
        messages = fetch_inbound(ghl_get, conversation_id)
    except Exception:
        return {"ok": False, "httpStatus": 502, "sent": False, "message": "GHL inbound could not be read. Nothing was sent."}
    sent = False
    forwarded = 0
    for message in messages:
        result = handle({
            "contactId": c("RELAY_CONTACT_ID"),
            "phone": c("RELAY_ALLOWED_PHONE"),
            "text": message["body"],
            "messageId": message["id"],
            "occurredAt": message["occurredAt"],
        })
        forwarded += 1
        sent = sent or bool(result.get("sent"))
    if forwarded == 0 or sent:
        commit_grant(db(), pick(p, ["accessCode", "access_code"]))
    return {"ok": True, "httpStatus": 200, "sent": sent, "forwarded": forwarded, "message": "The relay checked the conversation."}


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] not in ("/health", "/"):
            self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "live": bool(LIVE), "service": "sdr-relay"}).encode())

    def do_POST(self):
        if self.headers.get("x-webhook-secret") != SECRET:
            self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":"secret"}'); return
        body = self.rfile.read(int(self.headers.get("content-length", 0) or 0))
        try: p = json.loads(body or b"{}")
        except Exception: p = {}
        path = self.path.split("?")[0]
        if path == "/opt-in":
            out = accept_opt_in(p)
        elif path == "/pull":
            out = accept_pull(p)
        else:
            out = handle(p)
            out.setdefault("httpStatus", 200)
        status = int(out.get("httpStatus") or 200)
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(out).encode())
    def log_message(self, *a): pass

if __name__ == "__main__":
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    print(f"SDR Flo relay on :{PORT} (LIVE={LIVE}, enable_tag={ENABLE_TAG})")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
