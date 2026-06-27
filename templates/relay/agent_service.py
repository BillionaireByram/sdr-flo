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
        logj({"act": "send", "dry": True, "contact": contact, "text": text}); return
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
    logj({"act": "send", "status": s, "contact": contact, "text": text})

def add_tags(contact, tags):
    if tags and LIVE: ghl("POST", f"/contacts/{contact}/tags", {"tags": tags})
    logj({"act": "tag", "contact": contact, "add": tags, "dry": not LIVE})

def escalate(contact, reason):
    logj({"act": "escalate", "contact": contact, "reason": reason})
    add_tags(contact, ["ai-escalated"])
    # TODO: alert the operator (Slack/Telegram/iMessage)

# ---- output hygiene ----
def clean_text(t):
    if not t: return t
    urls = re.findall(r"https?://\S+", t)
    for k, u in enumerate(urls): t = t.replace(u, "\x00%d\x00" % k)
    t = t.replace("—", ", ").replace("–", ", ")
    t = t.replace(" -- ", ", ").replace(" - ", ", ")
    t = re.sub(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])", " ", t)
    t = re.sub(r"[ ]{2,}", " ", t)
    for k, u in enumerate(urls): t = t.replace("\x00%d\x00" % k, u)
    return t.strip()

# ---- the brain ----
def think(hist, inbound, profile):
    prof = ("\n\n## WHAT YOU ALREADY KNOW (never re-ask):\n" + json.dumps(profile)) if profile else ""
    sysmsg = SOUL + prof + "\n\n## CURRENT CONVERSATION\nYou are MID conversation. Continue, never restart.\n" + TOOLS_DOC
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

# ---- handle ----
def pick(p, names):
    for n in names:
        v = p.get(n)
        if isinstance(v, str) and v.strip(): return v.strip()
    return ""

def handle(p):
    contact = pick(p, ["contact_id", "contactId", "id"])
    text = pick(p, ["text", "message", "body"])
    if not (contact and text):
        logj({"skip": "no-route"}); return {"ok": True, "skipped": True}
    tags = contact_tags(contact)                       # FAIL-CLOSED: CRM is authoritative
    if tags is None:
        logj({"skip": "tag-fetch-failed", "contact": contact}); return {"ok": True, "skipped": "tag-fetch-failed"}
    if any(t in tags for t in GUARD_TAGS):
        logj({"skip": "guard", "contact": contact}); return {"ok": True, "skipped": "guard"}
    if ENABLE_TAG and ENABLE_TAG not in tags:          # not opted-in yet
        # Keyword-OR-tag: if they OPENED with a campaign keyword, self-tag + engage (don't wait on
        # the CRM to tag them). Otherwise skip — this is what keeps the bot out of personal DMs.
        if KEYWORDS and any(k in (text or "").lower() for k in KEYWORDS):
            add_tags(contact, [ENABLE_TAG]); tags.append(ENABLE_TAG)
            logj({"selftag": ENABLE_TAG, "contact": contact})
        else:
            logj({"skip": "not-keyword-lead", "contact": contact}); return {"ok": True, "skipped": "not-keyword-lead"}
    con = db()
    con.execute("INSERT INTO turns VALUES(?,?,?,?)", (contact, "user", text, time.time())); con.commit()
    hist = [{"role": r, "content": cc} for r, cc in con.execute(
        "SELECT role,content FROM turns WHERE contact=? ORDER BY ts", (contact,)).fetchall()][-40:]
    row = con.execute("SELECT data FROM profiles WHERE contact=?", (contact,)).fetchone()
    profile = json.loads(row[0]) if row else {}
    out = think(hist[:-1], text, profile)
    reply = clean_text((out.get("reply") or "").strip())
    if isinstance(out.get("profile"), dict):
        merged = {**profile, **{k: v for k, v in out["profile"].items() if v}}
        con.execute("INSERT OR REPLACE INTO profiles VALUES(?,?)", (contact, json.dumps(merged))); con.commit()
    for a in (out.get("actions") or []):
        if a.get("tool") == "tag": add_tags(contact, a.get("tags") or [])
        elif a.get("tool") == "escalate": escalate(contact, a.get("reason", ""))
    if reply:
        send_reply(contact, reply)
        con.execute("INSERT INTO turns VALUES(?,?,?,?)", (contact, "assistant", reply, time.time())); con.commit()
        # TODO: mirror to Supabase (conversations_log + events, channel-tagged)
    logj({"handled": True, "contact": contact, "reply": reply[:120]})
    return {"ok": True, "reply": reply}

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.headers.get("x-webhook-secret") != SECRET:
            self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":"secret"}'); return
        body = self.rfile.read(int(self.headers.get("content-length", 0) or 0))
        try: p = json.loads(body or b"{}")
        except Exception: p = {}
        out = handle(p)
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(out).encode())
    def log_message(self, *a): pass

if __name__ == "__main__":
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    print(f"SDR Flo relay on :{PORT} (LIVE={LIVE}, enable_tag={ENABLE_TAG})")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
