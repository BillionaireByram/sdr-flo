#!/usr/bin/env python3
"""
DigitalFlo Intelligence Layer  (client-VM, cron-driven, self-contained)
=======================================================================
Two jobs, one engine, shared metrics:

  1. SCOREBOARD  - tally every conversation + action, score objective hits
                   (TU = community link sent, BFP = call booked), render a
                   plain-English report. This is the SOURCE OF TRUTH for
                   "are we hitting the goal."

  2. OPTIMIZER   - read the scoreboard, analyze the conversations, and ONLY
                   when there is a material problem, produce a challenger
                   prompt, prove it beats the current one on a fixed gauntlet
                   WITHOUT touching the protected core, then promote it.
                   Versioned + auto-rollback. Forward-only. Non-destructive.

Design = CHAMPION / CHALLENGER with eval-gated promotion:
  - the live prompt is the "champion"
  - the optimizer only ever proposes a "challenger"
  - a challenger is promoted ONLY if it (a) keeps every protected anchor
    verbatim, (b) stays within size bounds, and (c) scores >= champion on
    the gauntlet with no regression on any scenario the champion passed
  - after promotion the agent is restarted and smoke-checked; any failure
    auto-rolls-back to the previous champion
  - if there is no material problem, it PASSES and changes nothing
    ("evolve only when needed, never break itself")

Usage:  intelligence.py daily       # soft: 24h scoreboard + soft optimize
        intelligence.py weekly      # deep: 7d full report + deep optimize
        intelligence.py scoreboard [daily|weekly]   # report only, no changes
        intelligence.py rollback <motion>           # revert to previous champion
"""
import json, os, re, sys, time, sqlite3, shutil, subprocess, urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "config.json").read_text())
VERS = HERE / "versions"; REPORTS = HERE / "reports"
VERS.mkdir(exist_ok=True); REPORTS.mkdir(exist_ok=True)
LOGF = HERE / "intelligence.log.jsonl"
DAY = 86400


def log(o):
    o["ts"] = datetime.now(timezone.utc).isoformat()
    with open(LOGF, "a") as f:
        f.write(json.dumps(o) + "\n")
    print(json.dumps(o, ensure_ascii=False))


def llm(messages, max_tokens=2200, temp=0.3):
    """Reasoning call. Takeoff routes through the local Max bridge (no API credits).
    Framework note: per-client this points at that client's provider/bridge."""
    body = {"model": CFG["model"], "messages": messages, "temperature": temp, "max_tokens": max_tokens}
    req = urllib.request.Request(CFG["bridge"], data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer x"},
                                 method="POST")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=200) as r:
                return (json.loads(r.read().decode())["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            log({"warn": "llm", "attempt": attempt, "err": str(e)[:160]})
            time.sleep(4)
    return ""


def jparse(s):
    m = re.search(r"\{.*\}", s or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ---------------------------------------------------------------- SCOREBOARD
def collect(window_secs):
    """Pull per-contact conversation records + outcomes for the window."""
    cut = time.time() - window_secs
    con = sqlite3.connect(CFG["state_db"]); con.row_factory = sqlite3.Row
    active = [r["contact"] for r in con.execute(
        "SELECT DISTINCT contact FROM turns WHERE ts>=?", (cut,)).fetchall()]

    sends, books, escalated, errors = {}, set(), set(), []
    if os.path.exists(CFG["log"]):
        for line in open(CFG["log"]):
            try:
                o = json.loads(line)
            except Exception:
                continue
            c = o.get("contact")
            if o.get("act") == "send" and c:
                sends.setdefault(c, []).append(o.get("text", ""))
            if o.get("act") == "book" and c:
                books.add(c)
            if o.get("act") == "tag" and c and "ai-escalated" in (o.get("add") or []):
                escalated.add(c)
            if o.get("error"):
                errors.append({"error": o.get("error"), "detail": o.get("detail", "")})

    records = []
    for c in active:
        turns = [{"role": r["role"], "content": r["content"]} for r in con.execute(
            "SELECT role,content FROM turns WHERE contact=? AND ts>=? ORDER BY ts",
            (c, cut - 7 * DAY)).fetchall()]
        mrow = con.execute("SELECT motion FROM convo WHERE contact=?", (c,)).fetchone()
        motion = mrow["motion"] if mrow else "TU"
        m = CFG["motions"].get(motion, {})
        out_text = " ".join(t["content"] for t in turns if t["role"] == "assistant") + " " + " ".join(sends.get(c, []))
        if m.get("objective_kind") == "book":
            hit = c in books
        else:
            hit = bool(m.get("objective_marker")) and m["objective_marker"] in out_text
        lead_msgs = sum(1 for t in turns if t["role"] == "user")
        records.append({"contact": c, "motion": motion, "turns": turns,
                        "lead_msgs": lead_msgs, "engaged": lead_msgs >= 2,
                        "hit": hit, "escalated": c in escalated})
    con.close()
    return records, errors


def tally(records, errors):
    out = {"total_people": len(records), "engaged": 0, "objective_hits": 0,
           "escalated": len(set(r["contact"] for r in records if r["escalated"])),
           "errors": len(errors), "by_motion": {}}
    for mname in CFG["motions"]:
        rs = [r for r in records if r["motion"] == mname]
        eng = [r for r in rs if r["engaged"]]
        hits = [r for r in rs if r["hit"]]
        out["by_motion"][mname] = {
            "people": len(rs), "engaged": len(eng), "hits": len(hits),
            "outcome_name": CFG["motions"][mname]["outcome_name"],
            "hit_rate": round(len(hits) / len(eng), 3) if eng else 0.0}
    out["engaged"] = sum(1 for r in records if r["engaged"])
    out["objective_hits"] = sum(1 for r in records if r["hit"])
    out["hit_rate"] = round(out["objective_hits"] / out["engaged"], 3) if out["engaged"] else 0.0
    return out


def render_scoreboard(t, period_label, narrative=None):
    L = []
    L.append(f"# {CFG['display_name']} — Scoreboard ({period_label})")
    L.append("")
    L.append("## The numbers, plain English")
    L.append(f"- People the agent talked to: **{t['total_people']}**")
    L.append(f"- Real conversations (they actually replied): **{t['engaged']}**")
    L.append(f"- Hit the goal (objective reached): **{t['objective_hits']}**  "
             f"({int(round(t['hit_rate']*100))}% of real conversations)")
    L.append(f"- Needed a human (escalated): **{t['escalated']}**")
    L.append(f"- Hiccups caught and auto-handled: **{t['errors']}**")
    L.append("")
    L.append("## By goal")
    for mname, mm in t["by_motion"].items():
        if mm["people"] == 0:
            continue
        L.append(f"- **{mname}** ({mm['outcome_name']}): {mm['people']} people, "
                 f"{mm['engaged']} real convos, **{mm['hits']} {mm['outcome_name']}** "
                 f"({int(round(mm['hit_rate']*100))}%)")
    if narrative:
        L.append("")
        L.append("## What that means")
        L.append(narrative)
    return "\n".join(L)


# ---------------------------------------------------------------- ANALYZE
def analyze(records, t):
    """LLM reads the real transcripts + the scoreboard, returns a structured
    verdict. PASS = no material problem. OPTIMIZE = evidence-backed fixes."""
    cap = CFG.get("max_transcripts_to_llm", 30)
    sample = []
    # prioritize the conversations that MISSED the objective (that's where the lessons are)
    for r in sorted(records, key=lambda x: (x["hit"], -x["lead_msgs"]))[:cap]:
        convo = "\n".join(f"{'LEAD' if x['role']=='user' else 'AGENT'}: {x['content']}" for x in r["turns"])
        sample.append(f"[motion {r['motion']} | objective_hit={r['hit']} | escalated={r['escalated']}]\n{convo}")
    prompt = f"""You are the optimization analyst for the {CFG['display_name']} AI setter.
You are reviewing real conversations to find concrete, forward-only ways to hit the objective more often.
Objectives: TU = {CFG['motions']['TU']['objective_label']}; BFP = {CFG['motions']['BFP']['objective_label']}.

SCOREBOARD (this window): {json.dumps(t)}
TARGET hit_rate: {CFG['targets']['hit_rate']}

CONVERSATIONS (objective-missing ones first):
{chr(10).join(sample) if sample else "(none)"}

Return STRICT JSON only:
{{
 "summary": "2-3 plain-English sentences on how it is doing",
 "whats_working": ["..."],
 "whats_dropping": ["specific places conversations stalled, looped, or missed the objective, with the pattern"],
 "errors_seen": ["..."],
 "verdict": "PASS" or "OPTIMIZE",
 "severity": 0,
 "proposed_changes": ["each = one specific, minimal, additive prompt improvement tied to a pattern above. forward-only, never remove core rules"]
}}
Rules: verdict=PASS if the agent is basically hitting the objective and you see no clear, repeated failure pattern (do NOT invent work). severity 0-5 (0 none, 5 severe). Propose changes ONLY for real, repeated, evidenced problems. Never propose anything that weakens identity, the no-dash rule, tag gating, escalation, qualification, or the objective itself."""
    rep = jparse(llm([{"role": "user", "content": prompt}])) or {}
    rep.setdefault("verdict", "PASS"); rep.setdefault("severity", 0)
    rep.setdefault("proposed_changes", []); rep.setdefault("summary", "No analysis produced.")
    return rep


def materiality_ok(rep, t, mode):
    need = CFG["min_convos"]["weekly" if mode == "weekly" else "daily"]
    if t["engaged"] < need:
        return False, f"insufficient data ({t['engaged']} < {need} real convos) — never optimize on noise"
    if rep.get("verdict") != "OPTIMIZE":
        return False, "analyst verdict = PASS (no material problem)"
    if int(rep.get("severity", 0)) < 2:
        return False, f"severity {rep.get('severity')} below threshold (2)"
    if not rep.get("proposed_changes"):
        return False, "no concrete changes proposed"
    return True, "material problem with concrete fixes"


# ---------------------------------------------------------------- GAUNTLET
def run_soul_on(soul_text, motion_hint, history, user, system_extra=""):
    sys_msg = soul_text + system_extra + f"\n\n## CURRENT CONVERSATION\nMOTION: {motion_hint}. You are MID conversation, continue, never restart. Reply with the lead-facing message only."
    msgs = [{"role": "system", "content": sys_msg}] + \
           [{"role": role, "content": txt} for role, txt in history] + \
           [{"role": "user", "content": user}]
    out = llm(msgs, max_tokens=400, temp=0.4)
    j = jparse(out)
    if j and isinstance(j.get("reply"), str):
        return j["reply"]
    return out


def gauntlet_score(soul_text, motion):
    scenarios = CFG["gauntlet"].get(motion, [])
    passed, detail = 0, []
    for sc in scenarios:
        reply = (run_soul_on(soul_text, motion, sc.get("history", []), sc["user"]) or "").lower()
        ok = True
        if any(b.lower() in reply for b in sc.get("fail_if", [])):
            ok = False
        if ok and sc.get("pass_if") and not any(g.lower() in reply for g in sc["pass_if"]):
            ok = False
        passed += 1 if ok else 0
        detail.append({"name": sc["name"], "pass": ok})
    return passed, len(scenarios), detail


# ---------------------------------------------------------------- GENERATE + VALIDATE
def generate_challenger(motion, champion, rep):
    prot = CFG["motions"][motion]["protected"]
    prompt = f"""You are improving a production AI-setter prompt. Output the FULL improved prompt and nothing else.

HARD RULES:
- This is forward-only optimization. Keep everything that works. Only apply the specific improvements below.
- These exact strings MUST appear, unchanged, in your output (they are the protected core): {json.dumps(prot)}
- Never remove or weaken: the identity, the objective, the no-dash rule, tag gating awareness, escalation, qualification logic, the continuity/destination rules.
- Use NO dashes anywhere (no hyphens, en or em dashes) in any example the lead would see.
- Keep length close to the original. Make targeted edits, not a rewrite.

IMPROVEMENTS TO APPLY (from analysis of real conversations):
{json.dumps(rep.get('proposed_changes', []), indent=2)}

CURRENT PROMPT:
<<<
{champion}
>>>

Return only the full improved prompt text."""
    cand = llm([{"role": "user", "content": prompt}], max_tokens=4000, temp=0.4)
    return cand.strip()


def validate(motion, champion, challenger):
    """Return (promote: bool, reason, scores). Non-destructive gate."""
    if not challenger or len(challenger) < 200:
        return False, "challenger empty/too short", {}
    # 1. protected core verbatim
    for p in CFG["motions"][motion]["protected"]:
        if p not in challenger:
            return False, f"protected anchor missing: {p[:40]!r}", {}
    # 2. size bounds (not gutted, not bloated)
    ratio = len(challenger) / max(1, len(champion))
    if ratio < 0.85 or ratio > 1.45:
        return False, f"size ratio {ratio:.2f} out of bounds (0.85-1.45)", {}
    # 3. no NEW raw dashes introduced into lead-facing examples (rough guard)
    if challenger.count(" — ") > champion.count(" — ") or challenger.count(" - ") > champion.count(" - ") + 1:
        return False, "introduced dashes", {}
    # 4. behavioral gauntlet: challenger must >= champion, no regression
    cp, cn, cd = gauntlet_score(champion, motion)
    hp, hn, hd = gauntlet_score(challenger, motion)
    champ_by = {d["name"]: d["pass"] for d in cd}
    for d in hd:  # no scenario the champion passed may now fail
        if champ_by.get(d["name"]) and not d["pass"]:
            return False, f"regression on '{d['name']}' (champion passed, challenger fails)", {"champion": cp, "challenger": hp}
    if hp < cp:
        return False, f"challenger gauntlet {hp}/{hn} < champion {cp}/{cn}", {"champion": cp, "challenger": hp}
    return True, f"challenger {hp}/{hn} >= champion {cp}/{cn}, core intact", {"champion": cp, "challenger": hp}


def promote(motion, challenger):
    if os.environ.get("INTEL_DRY") == "1":
        log({"event": "DRY_would_promote", "motion": motion, "challenger_len": len(challenger)})
        return False, "dry-run"
    soul = CFG["motions"][motion]["soul"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = VERS / f"SOUL.{motion}.{stamp}.md"
    shutil.copy(soul, backup)                      # version the champion
    Path(soul).write_text(challenger)              # promote challenger
    subprocess.run(["systemctl", "restart", CFG["service"]], check=False)
    time.sleep(4)
    # smoke: service up + bridge ok + one live gauntlet scenario passes
    active = subprocess.run(["systemctl", "is-active", CFG["service"]],
                            capture_output=True, text=True).stdout.strip()
    sp, sn, _ = gauntlet_score(challenger, motion)
    healthy = (active == "active") and (sp >= max(1, sn - 1))
    if not healthy:
        shutil.copy(backup, soul)                  # AUTO-ROLLBACK
        subprocess.run(["systemctl", "restart", CFG["service"]], check=False)
        log({"event": "ROLLBACK", "motion": motion, "active": active, "smoke": f"{sp}/{sn}"})
        return False, backup.name
    # prune old versions
    olds = sorted(VERS.glob(f"SOUL.{motion}.*.md"))
    for f in olds[:-CFG.get("keep_versions", 30)]:
        f.unlink()
    log({"event": "PROMOTED", "motion": motion, "backup": backup.name, "smoke": f"{sp}/{sn}"})
    return True, backup.name


def rollback(motion):
    olds = sorted(VERS.glob(f"SOUL.{motion}.*.md"))
    if not olds:
        print("no versions to roll back to"); return
    last = olds[-1]
    shutil.copy(last, CFG["motions"][motion]["soul"])
    subprocess.run(["systemctl", "restart", CFG["service"]], check=False)
    log({"event": "MANUAL_ROLLBACK", "motion": motion, "restored": last.name})


# ---------------------------------------------------------------- REPORT
def save_report(text, mode, t):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    name = f"{mode}-{stamp}.md"
    (REPORTS / name).write_text(text)
    vault = CFG.get("vault_reports")
    if vault:
        try:
            Path(vault).mkdir(parents=True, exist_ok=True)
            (Path(vault) / name).write_text(text)
        except Exception as e:
            log({"warn": "vault-write", "err": str(e)[:120]})
    log({"event": "report", "mode": mode, "file": name, "hit_rate": t["hit_rate"]})


# ---------------------------------------------------------------- ORCHESTRATION
def run(mode):
    window = 7 * DAY if mode == "weekly" else DAY
    period = ("Week ending " if mode == "weekly" else "Day ending ") + \
             datetime.now(timezone.utc).strftime("%Y-%m-%d")
    records, errors = collect(window)
    t = tally(records, errors)

    rep = analyze(records, t) if records else {"verdict": "PASS", "summary": "No conversations in window.", "severity": 0, "proposed_changes": []}

    # OPTIMIZER (gated)
    optimizer_note = ""
    ok, why = materiality_ok(rep, t, mode)
    if not ok:
        optimizer_note = f"No prompt change this {mode}: {why}."
        log({"event": "optimize-skip", "mode": mode, "why": why, "verdict": rep.get("verdict"), "severity": rep.get("severity")})
    else:
        changed_any = False
        for motion in CFG["motions"]:
            champion = Path(CFG["motions"][motion]["soul"]).read_text()
            challenger = generate_challenger(motion, champion, rep)
            promote_ok, reason, scores = validate(motion, champion, challenger)
            if not promote_ok:
                log({"event": "challenger-rejected", "motion": motion, "reason": reason})
                continue
            done, backup = promote(motion, challenger)
            changed_any = changed_any or done
            log({"event": "promote-result", "motion": motion, "promoted": done, "reason": reason, "scores": scores})
        optimizer_note = ("Prompt improved this %s (validated against the gauntlet, protected core intact, auto-rollback armed)."
                          % mode) if changed_any else ("Analysis found issues but no challenger beat the current prompt safely, so nothing changed this %s." % mode)

    narrative = rep.get("summary", "")
    if rep.get("whats_dropping"):
        narrative += "\n\n**Where it is dropping:** " + "; ".join(rep["whats_dropping"][:5])
    if rep.get("whats_working"):
        narrative += "\n\n**What is working:** " + "; ".join(rep["whats_working"][:5])
    narrative += "\n\n**Optimizer:** " + optimizer_note

    report = render_scoreboard(t, period, narrative)
    save_report(report, mode, t)
    print("\n" + report)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if cmd in ("daily", "weekly"):
        run(cmd)
    elif cmd == "scoreboard":
        mode = sys.argv[2] if len(sys.argv) > 2 else "weekly"
        window = 7 * DAY if mode == "weekly" else DAY
        records, errors = collect(window)
        t = tally(records, errors)
        period = ("Week ending " if mode == "weekly" else "Day ending ") + datetime.now(timezone.utc).strftime("%Y-%m-%d")
        print(render_scoreboard(t, period))
    elif cmd == "rollback" and len(sys.argv) > 2:
        rollback(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
