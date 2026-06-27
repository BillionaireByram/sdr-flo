# Uptime watchdog (proactive: spot → fix → report)

A self-contained guardian that runs **on the client's own VM** and guarantees response uptime. Born from a real incident (a shared OAuth token rotated across two machines and died silently for 26 hours — every lead got silence and nobody knew). The watchdog makes that class of failure impossible to miss *and* mostly self-healing.

> **Proactive, not a siren.** It spots a problem, **fixes it itself**, then reports *what it saw and what it did*. It only @mentions a human for the rare thing it genuinely can't fix (e.g. a provider balance limit).

## What it does every ~2 minutes
- **Brain health** — probes the reasoning backend (`RELAY_BRIDGE`/`RELAY_MODEL`/`RELAY_BRAIN_KEY`). Transient blip → retry. Stuck → restart the agent. Unreachable + unfixable → escalate with a plain-English reason.
- **Agent health** — the relay's inbound port is listening; down → restart the service.
- **Conversation recovery** — scans the CRM for any lead whose **last message is inbound** and older than `WATCHDOG_STUCK_MIN`, and re-pokes the relay so the agent answers. *No lead is left waiting*, whatever the cause.

## Why it's reliable now
Pair it with a **dedicated provider API key** for the brain (e.g. GLM via `api.z.ai`, `RELAY_MODEL=glm-4.6`). A dedicated key never expires and is single-tenant per client — so the original failure mode (a shared, rotating OAuth token) simply cannot happen. The watchdog then catches everything else and self-heals.

## Install (per client)
1. Copy `uptime-watchdog.py` to `/opt/sdr-flo/agent/uptime-watchdog.py`.
2. Ensure the relay env (`/opt/sdr-flo/.env`, see `../deploy/env.example`) has the brain, `GHL_PIT`/`GHL_LOC`, `RELAY_WEBHOOK_SECRET`, `SLACK_BOT_TOKEN`, `SLACK_OPS_CHANNEL`, and (optional) `WATCHDOG_ESCALATE_MENTION`.
3. Install the units: `uptime-watchdog.service` + `uptime-watchdog.timer` → `/etc/systemd/system/`.
4. `systemctl daemon-reload && systemctl enable --now uptime-watchdog.timer`.

## Config
All via env — see [`../deploy/env.example`](../deploy/env.example) (`WATCHDOG_*`, `RELAY_BRAIN_*`, `GHL_LOC`). Nothing is hardcoded; no secrets live in the script.

## Alert channel
Point `SLACK_OPS_CHANNEL` at wherever the team already watches. Wording is intentionally calm and client-safe (it reports fixes and recoveries, not raw stack traces), so it's fine in a shared channel — it turns an incident into a visible *"caught it, fixed it"* trust signal.

## Tuning
- `WATCHDOG_STUCK_MIN` (default 4) — how long a lead may wait before a re-poke.
- `WATCHDOG_MAX_PER_RUN` (default 8) — cap on re-pokes per run (prevents a slow first pass over a backlog).
- `WATCHDOG_MAX_AGE_MIN` (default 720) — ignore conversations older than this.
