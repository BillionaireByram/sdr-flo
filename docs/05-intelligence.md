# 05 — Intelligence (scoreboard + self-optimization)

Every SDR Flo install ships with the intelligence layer: a **scoreboard** that measures whether Flo is hitting the objective, and an **optimizer** that safely improves the prompt over time. Engine: [../templates/intelligence/intelligence.py](../templates/intelligence/intelligence.py) + [config.example.json](../templates/intelligence/config.example.json).

## Two jobs, one engine, shared metrics

### Scoreboard (the measuring stick)
Tallies every conversation + action from the relay's store (per-contact turns + the action log), scores **objective hits** per motion (link sent / call booked / sold / registered), and writes a **plain-English** report:
- People talked to · real conversations (they replied) · objective hits + % · escalations · auto-handled hiccups.
- Broken out **by motion**.
- Saved daily (snapshot) + weekly (full report) to the VM and the vault.

This is the source of truth the optimizer reads — you cannot improve what you do not measure.

### Optimizer (gets smarter, safely)
Reads the scoreboard, analyzes the real transcripts (objective-missing ones first), and — only when warranted — improves the prompt. The safety model is **champion / challenger with eval-gated promotion**:

- The live prompt is the **champion**. The optimizer only ever builds a **challenger**.
- A challenger is **promoted only if ALL gates pass**:
  1. **Protected core verbatim** — a per-client list of must-keep strings (identity, the objective/link, no-dash rule, tag-gating, escalation, qualification, continuity/destination). Missing one → reject.
  2. **Size bounds** — within 0.85×–1.45× of champion (not gutted, not bloated).
  3. **No new dashes** in lead-facing copy.
  4. **Gauntlet** — a fixed scenario set (continuity/no-restart, drive-to-objective, qualify, no-dash, stop/escalate) run through champion AND challenger; challenger must score **≥ champion with zero regressions** on any scenario the champion passed.
- **Materiality gate** (before any of that): proceed only if there is enough data (min real convos) AND the analyst verdict is `OPTIMIZE` with severity ≥ 2 AND concrete changes. Otherwise **PASS, change nothing** ("evolve only when needed").
- **Versioning + auto-rollback** — every promotion backs up the champion, restarts the agent, smoke-tests it (service active + live gauntlet); any failure auto-restores. Manual `rollback <motion>` anytime.
- **Fail-safe** — if the reasoning bridge is down/throttled, analysis returns empty → PASS → no change. It can never do harm by failing.

## Cadence
systemd timers: **daily 00:00** (soft, 24h window) + **weekly Sun 00:30** (deep report, 7d window), `Persistent=true` so a powered-off VM catches up. Midnight is chosen for low lead traffic + low operator usage (so heavy analysis does not compete with the live agent for the model).

## Rollout — shadow first
Deploy with `INTEL_DRY=1` (shadow) in `intel.env`: it produces the scoreboard + a "here is what I WOULD change and why" report, promoting nothing. Review the first report, then set `INTEL_DRY=0` to enable live self-optimization. One-line, reversible.

## Per-client config (what changes)
`config.json` declares: `state_db` / `log` / `service` (the agent's store + action log + systemd unit), `bridge` + `model` (the client's reasoning provider — match the no-API rule), `vault_reports`, `targets.hit_rate`, `min_convos`, and per-motion `objective_marker` + `objective_kind` + **`protected`** anchors + a **`gauntlet`** (3–5 scenarios each).

## What stays fixed (the framework)
Champion/challenger promotion · protected-core + size + gauntlet + no-regression gates · materiality gate · versioning + auto-rollback · shadow→live · the scoreboard tally + plain-English report · daily/weekly cadence.

## Why this is safe
An agent that rewrites its own production prompt is dangerous by default. The gates make every change **forward-only** (must beat the current prompt), **non-destructive** (protected core can never be deleted — proven by feeding it destructive rewrites, all rejected), **reversible** (versioned + auto-rollback), and **rare** (only when materially needed). That is the whole point of the design.
