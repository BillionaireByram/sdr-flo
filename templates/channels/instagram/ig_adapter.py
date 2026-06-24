#!/usr/bin/env python3
"""
SDR Flo — Instagram comment->DM->qualify->book adapter (official Graph API only).

Flow:
  IG comment "FLO" → keyword router → (public reply) + private DM opener  [as the configured persona]
  lead replies     → SDR Flo brain (Byram-voice SOUL, NEPQ) → qualify → book / give value
  everything       → the spine (leads, conversations, events, acquisition_sources)

This is a channel ADAPTER that feeds the canonical SDR Flo brain + spine. It is NOT a
parallel bot. Persona is per-niche config — for Client Zero (Byram's personal IG) the
agent speaks AS BYRAM, never "Flo" and never any internal tool name.

Shadow-first: SDR_FLO_DRAFT_ONLY=true (default) drafts + persists everything and sends
NOTHING. Live sending requires explicit env flags. Idempotent on comment/message ids.

Run:  python3 ig_adapter.py            # starts the webhook server
Test: import handle_comment / handle_message directly (see tests/).
"""
import json, os, re, sqlite3, time, urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from meta_client import MetaClient

HERE = Path(__file__).resolve().parent


def env(k, d=""): return os.environ.get(k, d)

DRAFT_ONLY = env("SDR_FLO_DRAFT_ONLY", "true").lower() in ("1", "true", "yes")
DB = env("IG_DB", str(HERE / "ig_state.db"))
LOG = env("IG_LOG", str(HERE / "ig_adapter.log.jsonl"))
SOUL_PATH = env("IG_SOUL", str(HERE / "SOUL.byram.md"))
CONFIG_PATH = env("IG_CONFIG", str(HERE / "config.example.json"))
BRIDGE = env("RELAY_BRIDGE", "")          # reasoning endpoint; empty => offline template draft
MODEL = env("RELAY_MODEL", "claude-sonnet-4-6")
VERIFY_TOKEN = env("META_VERIFY_TOKEN", "")
GUARD_TAGS = {"booked", "customer", "existing-client", "human-owned", "opted-out",
              "do-not-contact", "support", "billing", "refund", "complaint"}
STOP_WORDS = ("stop", "unsubscribe", "don't message", "do not message", "leave me alone")


def logj(o):
    o["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    Path(LOG).parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps(o) + "\n")


def db():
    con = sqlite3.connect(DB)
    con.executescript("""
      CREATE TABLE IF NOT EXISTS processed(id TEXT PRIMARY KEY, kind TEXT, ts REAL);
      CREATE TABLE IF NOT EXISTS leads(igsid TEXT PRIMARY KEY, username TEXT, source TEXT,
        keyword TEXT, media_id TEXT, stage TEXT, tags TEXT, created REAL);
      CREATE TABLE IF NOT EXISTS conversations(igsid TEXT, role TEXT, content TEXT, ts REAL);
      CREATE TABLE IF NOT EXISTS events(igsid TEXT, type TEXT, meta TEXT, ts REAL);
      CREATE TABLE IF NOT EXISTS sources(igsid TEXT PRIMARY KEY, media_id TEXT, comment_id TEXT,
        keyword TEXT, campaign TEXT, value_link TEXT, first_touch REAL);
    """)
    return con


def seen(con, _id):
    return bool(con.execute("SELECT 1 FROM processed WHERE id=?", (_id,)).fetchone())


def mark(con, _id, kind):
    con.execute("INSERT OR IGNORE INTO processed VALUES(?,?,?)", (_id, kind, time.time())); con.commit()


def load_config():
    cfg = json.loads(Path(CONFIG_PATH).read_text())
    # index campaigns by keyword (lowercased) for O(1) match
    by_kw = {}
    for c in cfg.get("campaigns", []):
        for kw in c.get("keywords", []):
            by_kw[kw.strip().lower()] = c
    cfg["_by_kw"] = by_kw
    return cfg


def match_keyword(text, by_kw):
    norm = re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split()
    for w in norm:
        if w in by_kw:
            return by_kw[w]
    return None


# ---- the brain (Byram voice). Calls the SDR Flo reasoning bridge; offline => template. ----
def think(history, inbound, profile, campaign):
    soul = Path(SOUL_PATH).read_text() if Path(SOUL_PATH).exists() else "You are Byram. Be natural, give value, qualify, book a call."
    offer = campaign.get("offer", "a version of the AI operator")
    sysmsg = (soul + f"\n\n## CONTEXT\nThey commented '{campaign.get('label','')}' on your post. Offer: {offer}. "
              f"Objective: book a call if they're a fit; otherwise give value. "
              f"What you know: {json.dumps(profile)}\n"
              'Return STRICT JSON: {"reply":"<message in Byram first-person voice, no dashes, never name any tool>",'
              '"actions":[{"tool":"tag","tags":["..."]},{"tool":"book"},{"tool":"escalate","reason":"..."}],'
              '"profile":{"business":"","bottleneck":"","lead_volume":"","urgency":"","fit":"","notes":""}}')
    if not BRIDGE:   # offline template draft so shadow/tests work with no model
        return {"reply": f"Appreciate you reaching out. Quick q so I point you right, what does your business do and where are most of your leads coming from right now?",
                "actions": [{"tool": "tag", "tags": ["ig-engaged"]}], "profile": {}}
    msgs = [{"role": "system", "content": sysmsg}] + history + [{"role": "user", "content": inbound}]
    try:
        req = urllib.request.Request(BRIDGE, data=json.dumps({"model": MODEL, "messages": msgs, "temperature": 0.6}).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer x"}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            content = json.loads(r.read().decode())["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        return json.loads(m.group(0)) if m else {"reply": content, "actions": []}
    except Exception as e:
        logj({"error": "think", "detail": str(e)[:160]})
        return {"reply": "", "actions": []}


def clean(t):  # no dashes lead-facing
    t = (t or "").replace("—", ", ").replace("–", ", ").replace(" - ", ", ")
    return re.sub(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])", " ", t).strip()


# ---- handlers (pure + testable) ----
def handle_comment(event, *, client=None, cfg=None, con=None):
    cfg = cfg or load_config(); con = con or db()
    cid = event.get("comment_id") or event.get("id")
    if not cid: return {"skip": "no-comment-id"}
    if seen(con, cid): return {"skip": "dup-comment", "comment_id": cid}
    text = event.get("text", ""); igsid = event.get("from_igsid") or event.get("from", {}).get("id")
    username = event.get("username") or event.get("from", {}).get("username", "")
    media_id = event.get("media_id", "")
    camp = match_keyword(text, cfg["_by_kw"])
    mark(con, cid, "comment")
    if not camp:
        logj({"skip": "no-keyword", "comment_id": cid, "text": text}); return {"skip": "no-keyword"}
    # persist lead + source + event (the spine)
    con.execute("INSERT OR IGNORE INTO leads VALUES(?,?,?,?,?,?,?,?)",
                (igsid, username, "ig-comment", camp.get("label"), media_id, "new", "ig-engaged", time.time()))
    con.execute("INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?)",
                (igsid, media_id, cid, camp.get("label"), camp.get("campaign", ""), camp.get("value_link", ""), time.time()))
    con.execute("INSERT INTO events VALUES(?,?,?,?)", (igsid, "comment_keyword", json.dumps({"comment_id": cid, "kw": camp.get("label")}), time.time()))
    con.commit()
    out = {"comment_id": cid, "igsid": igsid, "campaign": camp.get("label"), "drafted": {}}
    # public reply (optional)
    if camp.get("public_reply_enabled") and client:
        pr = clean(camp.get("public_reply", "just dmd you, check your inbox"))
        client.reply_to_comment(cid, pr); out["drafted"]["public_reply"] = pr
    # private DM opener (value-first, in persona voice + the value link)
    if camp.get("private_dm_enabled", True):
        opener = clean(camp.get("dm_opener", "Hey, appreciate you commenting. Here is what I mentioned: {link} . Quick q so I send the right angle, what does your business do?").replace("{link}", camp.get("value_link", "")))
        if client: client.private_reply_to_comment(cid, opener)
        con.execute("INSERT INTO conversations VALUES(?,?,?,?)", (igsid, "assistant", opener, time.time())); con.commit()
        out["drafted"]["dm_opener"] = opener
    logj({"handled": "comment", **{k: out[k] for k in ("comment_id", "igsid", "campaign")}, "draft_only": DRAFT_ONLY})
    return out


def handle_message(event, *, client=None, cfg=None, con=None):
    cfg = cfg or load_config(); con = con or db()
    mid = event.get("message_id") or event.get("mid")
    if mid and seen(con, mid): return {"skip": "dup-message", "message_id": mid}
    if mid: mark(con, mid, "message")
    igsid = event.get("sender_igsid") or event.get("sender", {}).get("id")
    text = event.get("text", "")
    if not (igsid and text): return {"skip": "no-route"}
    row = con.execute("SELECT tags FROM leads WHERE igsid=?", (igsid,)).fetchone()
    tags = set((row[0] or "").split(",")) if row else set()
    if tags & GUARD_TAGS:
        logj({"skip": "suppressed", "igsid": igsid}); return {"skip": "suppressed"}
    if any(s in text.lower() for s in STOP_WORDS):
        con.execute("UPDATE leads SET tags=tags||',opted-out' WHERE igsid=?", (igsid,)); con.commit()
        logj({"skip": "opt-out", "igsid": igsid}); return {"skip": "opt-out"}
    con.execute("INSERT INTO conversations VALUES(?,?,?,?)", (igsid, "user", text, time.time())); con.commit()
    hist = [{"role": r, "content": c} for r, c in con.execute(
        "SELECT role,content FROM conversations WHERE igsid=? ORDER BY ts", (igsid,)).fetchall()][-40:]
    # campaign context for this lead (from their source)
    src = con.execute("SELECT keyword,value_link FROM sources WHERE igsid=?", (igsid,)).fetchone()
    camp = next((c for c in cfg.get("campaigns", []) if c.get("label") == (src[0] if src else None)), cfg.get("campaigns", [{}])[0] if cfg.get("campaigns") else {})
    out = think(hist[:-1], text, {"tags": sorted(tags)}, camp)
    reply = clean((out.get("reply") or "").strip())
    for a in out.get("actions", []):
        if a.get("tool") == "book":
            con.execute("INSERT INTO events VALUES(?,?,?,?)", (igsid, "booking_intent", "{}", time.time()))
        elif a.get("tool") == "escalate":
            logj({"escalate": igsid, "reason": a.get("reason")})
    if reply:
        if client: client.send_dm(igsid, reply)
        con.execute("INSERT INTO conversations VALUES(?,?,?,?)", (igsid, "assistant", reply, time.time()))
    con.execute("INSERT INTO events VALUES(?,?,?,?)", (igsid, "dm_reply", "{}", time.time())); con.commit()
    logj({"handled": "message", "igsid": igsid, "reply": reply[:120], "draft_only": DRAFT_ONLY})
    return {"igsid": igsid, "reply": reply, "actions": out.get("actions", [])}


def normalize_and_dispatch(payload, *, client=None, cfg=None, con=None):
    """Meta IG webhook envelope -> handlers. Returns list of results."""
    results = []
    for entry in payload.get("entry", []):
        for ch in entry.get("changes", []):
            if ch.get("field") == "comments":
                v = ch.get("value", {})
                results.append(handle_comment({
                    "comment_id": v.get("id"), "text": v.get("text", ""),
                    "from_igsid": (v.get("from") or {}).get("id"),
                    "username": (v.get("from") or {}).get("username", ""),
                    "media_id": (v.get("media") or {}).get("id", ""),
                }, client=client, cfg=cfg, con=con))
        for msg in entry.get("messaging", []):
            if msg.get("message"):
                results.append(handle_message({
                    "message_id": msg["message"].get("mid"),
                    "sender_igsid": (msg.get("sender") or {}).get("id"),
                    "text": msg["message"].get("text", ""),
                }, client=client, cfg=cfg, con=con))
    return results


# ---- webhook server ----
def make_client():
    return MetaClient(token=env("PAGE_ACCESS_TOKEN"), ig_user_id=env("META_IG_USER_ID"),
                      version=env("META_GRAPH_VERSION", "v21.0"), app_secret=env("META_APP_SECRET"),
                      public_reply_live=(not DRAFT_ONLY) and env("IG_PUBLIC_REPLY_ENABLED", "false").lower() in ("1", "true", "yes"),
                      private_reply_live=(not DRAFT_ONLY) and env("IG_PRIVATE_REPLY_ENABLED", "false").lower() in ("1", "true", "yes"),
                      logger=logj)


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        ch = make_client().verify_challenge(q.get("hub.mode", [""])[0], q.get("hub.verify_token", [""])[0],
                                            q.get("hub.challenge", [""])[0], VERIFY_TOKEN)
        if ch is not None:
            self.send_response(200); self.end_headers(); self.wfile.write(ch.encode())
        else:
            self.send_response(403); self.end_headers()

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("content-length", 0) or 0))
        client = make_client()
        if not client.valid_signature(raw, self.headers.get("X-Hub-Signature-256", "")):
            self.send_response(401); self.end_headers(); return
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            payload = {}
        normalize_and_dispatch(payload, client=client)
        self.send_response(200); self.end_headers(); self.wfile.write(b"EVENT_RECEIVED")

    def log_message(self, *a): pass


if __name__ == "__main__":
    port = int(env("IG_PORT", "8820"))
    print(f"SDR Flo IG adapter on :{port} (DRAFT_ONLY={DRAFT_ONLY})")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
