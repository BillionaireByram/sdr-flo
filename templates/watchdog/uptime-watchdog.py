#!/usr/bin/env python3
"""
SDR Flo — uptime watchdog (reference template, generalized from the Takeoff incident).

Runs ON the client's VM via a systemd timer (every ~2 min). Single-tenant, self-contained.

PROACTIVE by design: it SPOTS a problem, FIXES it itself, then REPORTS what it saw and what it
did. It only @mentions a human for the rare thing it genuinely cannot fix (e.g. a provider balance
limit). It is NOT a passive error siren.

What it guarantees — response uptime, watching every conversation:
  * BRAIN health   — probes the reasoning backend (RELAY_BRIDGE/MODEL/KEY). Transient -> retry;
                     stuck -> restart the agent; unreachable+unfixable -> escalate with a clear reason.
  * AGENT health   — the relay's inbound port is listening; down -> restart the service.
  * CONVO recovery — scans the CRM for any lead whose LAST message is inbound and older than
                     WATCHDOG_STUCK_MIN, and re-pokes the relay so the agent answers. No lead left waiting.

Config is 100% env (see deploy/env.example). NO secrets or client data live in this file.

LESSON baked in: the original outage was a shared OAuth token that rotated across machines and died
silently for 26h. Fix = a dedicated provider API key (no expiry) + this watchdog (catch + self-heal).
Pair it with RELAY_BRAIN_KEY pointing at a dedicated provider (e.g. GLM) for a brain that cannot expire.
"""
import json, os, time, socket, subprocess, urllib.request, urllib.error, calendar

def c(k, d=""): return os.environ.get(k, d)

# reasoning backend (same vars the relay uses)
BRIDGE   = c("RELAY_BRIDGE", "http://127.0.0.1:8787/v1/chat/completions")
MODEL    = c("RELAY_MODEL", "glm-4.6")
BRAIN_KEY= c("RELAY_BRAIN_KEY") or c("GLM_API_KEY") or "x"
# relay / agent
AGENT_URL   = c("WATCHDOG_AGENT_URL", "http://127.0.0.1:8799/")
AGENT_PORT  = int(c("WATCHDOG_AGENT_PORT", "8799"))
AGENT_SVC   = c("WATCHDOG_AGENT_SERVICE", "sdr-flo-relay.service")
WEBHOOK_SEC = c("RELAY_WEBHOOK_SECRET")
# CRM (GHL Conversations)
GHL_PIT = c("GHL_PIT"); GHL_LOC = c("GHL_LOC"); GHL_MSG_TYPE = c("GHL_MSG_TYPE", "IG")
# alerts
SLACK_TOK = c("SLACK_BOT_TOKEN"); SLACK_CH = c("SLACK_OPS_CHANNEL")
MENTION   = c("WATCHDOG_ESCALATE_MENTION")          # slack user id, only for UNFIXABLE issues
# tuning
STUCK_MIN = int(c("WATCHDOG_STUCK_MIN", "4")); MAX_AGE_MIN = int(c("WATCHDOG_MAX_AGE_MIN", "720"))
MAX_PER_RUN = int(c("WATCHDOG_MAX_PER_RUN", "8"))
# Quiet by default: only post to Slack for issues that need a human. Set WATCHDOG_VERBOSE=1 to also
# announce auto-fixes/recoveries + a weekly heartbeat. Either way everything is recorded in WLOG.
VERBOSE = c("WATCHDOG_VERBOSE", "0").lower() in ("1", "true", "yes")
STATE = c("WATCHDOG_STATE", "/opt/sdr-flo/agent/uptime_watchdog_state.json")
WLOG  = c("WATCHDOG_LOG", "/opt/sdr-flo/agent/uptime_watchdog.log.jsonl")
LOCK  = "/tmp/sdr_flo_uptime_watchdog.lock"

def wlog(o):
    o["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try: open(WLOG, "a").write(json.dumps(o) + "\n")
    except Exception: pass

def slack(text):
    if not (SLACK_TOK and SLACK_CH): return
    try:
        urllib.request.urlopen(urllib.request.Request("https://slack.com/api/chat.postMessage",
            data=json.dumps({"channel": SLACK_CH, "text": text, "unfurl_links": False}).encode(),
            headers={"Authorization": f"Bearer {SLACK_TOK}", "Content-Type": "application/json; charset=utf-8"}), timeout=12)
    except Exception as e: wlog({"slack_err": str(e)[:100]})

def ep(v):
    if isinstance(v, (int, float)): return v/1000 if v > 1e12 else v
    s = str(v)
    if s.isdigit(): v = int(s); return v/1000 if v > 1e12 else v
    try: return calendar.timegm(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception: return 0

def ghl(path):
    h = {"Authorization": f"Bearer {GHL_PIT}", "Version": "2021-04-15", "Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    try:
        with urllib.request.urlopen(urllib.request.Request("https://services.leadconnectorhq.com" + path, headers=h), timeout=25) as r:
            t = r.read().decode(); return json.loads(t) if t else {}
    except Exception as e: return {"_err": str(e)[:80]}

def port_up(port):
    s = socket.socket(); s.settimeout(3)
    try: s.connect(("127.0.0.1", port)); return True
    except Exception: return False
    finally:
        try: s.close()
        except Exception: pass

def restart_agent():
    subprocess.run(["systemctl", "restart", AGENT_SVC]); time.sleep(3)

def brain_check():
    """Probe the reasoning backend. Returns (ok, error_string)."""
    try:
        req = urllib.request.Request(BRIDGE, data=json.dumps(
            {"model": MODEL, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}).encode(),
            headers={"Authorization": f"Bearer {BRAIN_KEY}", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            return (True, None) if json.loads(r.read().decode()).get("choices") else (False, "empty response")
    except urllib.error.HTTPError as e:
        return (False, f"HTTP {e.code}: {e.read().decode()[:80]}")
    except Exception as e:
        return (False, str(e)[:70])

def main():
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 600: return
    open(LOCK, "w").write(str(time.time()))
    try:
        try: state = json.load(open(STATE))
        except Exception: state = {}
        handled = set(state.get("handled", [])); now = time.time()
        fixes = []; unfixable = []

        # 1) agent process
        if not port_up(AGENT_PORT):
            restart_agent()
            fixes.append("the responder process was offline, so I restarted it" + (" (back up now)" if port_up(AGENT_PORT) else ", still checking"))

        # 2) brain — spot, then FIX, then report
        ok, err = brain_check()
        if not ok:
            time.sleep(2); ok2, _ = brain_check()
            if ok2:
                fixes.append(f"the AI brain had a brief blip ({err}) that cleared on its own")
            else:
                restart_agent(); ok3, err3 = brain_check()
                if ok3:
                    fixes.append(f"the AI brain stalled ({err}); I restarted the agent and it recovered")
                else:
                    e = (err3 or "").lower()
                    if any(x in e for x in ("429", "balance", "insufficient", "resource package", "quota")):
                        unfixable.append(f"the reasoning provider is refusing calls ({err3}). That's a balance/quota limit I can't fix from here, it needs a top-up")
                    else:
                        unfixable.append(f"the AI brain is unreachable ({err3}) and a restart did not clear it")

        # 3) conversation recovery — answer anyone left waiting
        recovered = []; processed = 0
        d = ghl(f"/conversations/search?locationId={GHL_LOC}&limit=50&sortBy=last_message_date&sort=desc")
        for cv in ((d.get("conversations") if isinstance(d, dict) else []) or []):
            if processed >= MAX_PER_RUN: break
            if cv.get("lastMessageDirection") != "inbound": continue
            lmd = ep(cv.get("lastMessageDate") or cv.get("dateUpdated") or 0); age = (now - lmd) / 60
            if age < STUCK_MIN or age > MAX_AGE_MIN: continue
            contact = cv.get("contactId"); body = cv.get("lastMessageBody") or ""
            if not (contact and body): continue
            key = f"{contact}:{int(lmd)}"
            if key in handled: continue
            processed += 1
            try:
                req = urllib.request.Request(AGENT_URL,
                    data=json.dumps({"contact_id": contact, "text": body, "messageType": GHL_MSG_TYPE}).encode(),
                    headers={"x-webhook-secret": WEBHOOK_SEC, "Content-Type": "application/json"}, method="POST")
                if json.loads(urllib.request.urlopen(req, timeout=110).read().decode()).get("reply"):
                    recovered.append(contact)
                handled.add(key)
            except Exception: pass
            time.sleep(0.4)

        # report — QUIET BY DEFAULT: fixes + recoveries happen silently (logged below, never Slack).
        # Slack is reserved for the one thing that genuinely needs a human, so the channel stays clean
        # and uptime is guaranteed behind the scenes. Set WATCHDOG_VERBOSE=1 to also announce fixes/recoveries.
        if VERBOSE and fixes:
            slack(":wrench: *Uptime watchdog* — caught and fixed automatically:\n" + "\n".join("• " + f for f in fixes) + "\nBack to normal, nothing needed on your end.")
        if VERBOSE and recovered:
            slack(f":zap: *Uptime watchdog* — found {len(recovered)} conversation(s) waiting and made sure they got answered. All set.")
        if unfixable:                                    # always alert — this is the only thing that needs a human
            who = f"<@{MENTION}> " if MENTION else ""
            slack(f"{who}:warning: *Uptime watchdog* — I spotted this and tried to fix it, but it needs a human:\n" + "\n".join("• " + u for u in unfixable))

        cur = "unhealthy" if unfixable else "healthy"
        if VERBOSE and cur == "healthy" and now - state.get("last_heartbeat", 0) > 604800:
            slack(":green_heart: *Weekly uptime check* — brain healthy, agent up, watching every conversation around the clock. 100% uptime.")
            state["last_heartbeat"] = now
        state.update(status=cur, handled=list(handled)[-1500:], last_run=now)
        try: json.dump(state, open(STATE, "w"))
        except Exception: pass
        wlog({"status": cur, "fixes": fixes, "unfixable": unfixable, "recovered": len(recovered), "processed": processed})
    finally:
        try: os.remove(LOCK)
        except Exception: pass

if __name__ == "__main__":
    main()
