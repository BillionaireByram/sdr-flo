# 10 — Uptime watchdog & the pluggable brain

Two upgrades, field-proven in a real outage, that every client install now gets. Goal: **100% response uptime** — no lead ever sits unanswered, and the system heals itself before a human has to ask.

## The incident (why this exists)
A setter's brain ran on an OAuth token (Claude Max) that was **shared across two machines**. The token rotated, one machine invalidated the other's copy, and the brain returned `502` on every message for **26 hours** — the agent received every lead but could reply to none. Nobody noticed until the client did. Two root problems: (1) a brain auth that could expire/conflict, and (2) no one watching.

## Fix #1 — pluggable brain, dedicated key (no token to expire)
The relay's reasoning call is now **any OpenAI-compatible endpoint** via `RELAY_BRIDGE` / `RELAY_MODEL` / `RELAY_BRAIN_KEY`:

```
RELAY_BRIDGE=https://api.z.ai/api/coding/paas/v4/chat/completions
RELAY_MODEL=glm-4.6
RELAY_BRAIN_KEY=<provider key>
```

- A **dedicated provider API key** (e.g. GLM) **never expires** and is single-tenant per client — the shared-OAuth failure mode simply cannot happen. This is the recommended default.
- Codex (`ai-flo -z`) or a local Claude Max CLI bridge still work — set `RELAY_BRAIN_KEY=x` for a no-auth local bridge.
- Reasoning models that return text in `reasoning_content` are handled (the relay falls back to it). **Avoid `glm-5.2` for real-time setters** — it spends its budget "thinking" and returns empty without huge token allowances; `glm-4.6` is fast and clean.

## Fix #2 — the uptime watchdog (proactive)
A systemd timer on the **client's own VM** (`templates/watchdog/`), every ~2 minutes. It is **proactive: spot → fix → report**, not a passive error siren.

| Check | Action it takes itself | What it reports |
| --- | --- | --- |
| Reasoning backend down | retry → restart agent → (if truly stuck) escalate with a reason | "caught and fixed" / "needs a human: provider balance" |
| Agent process down | restart the service | "the responder was offline, I restarted it" |
| Lead waiting > `WATCHDOG_STUCK_MIN` | re-poke the relay so the agent answers | "found N waiting and answered them" |

- It **only @mentions a human** (`WATCHDOG_ESCALATE_MENTION`) for the rare thing it can't fix (e.g. a provider balance/quota limit).
- Reports go to `SLACK_OPS_CHANNEL` in calm, client-safe language — so a shared channel turns an incident into a visible *"caught it, fixed it"* trust signal.
- Conversation recovery is idempotent (a `handled` set keyed by contact+message-time) so it never double-answers.

See [`../templates/watchdog/README.md`](../templates/watchdog/README.md) and the `WATCHDOG_*` / `RELAY_BRAIN_*` keys in [`../templates/deploy/env.example`](../templates/deploy/env.example).

## Install checklist (per client)
1. Point the brain at a dedicated key (`RELAY_BRAIN_KEY`, `RELAY_MODEL=glm-4.6`).
2. Drop `uptime-watchdog.py` on the VM, wire the `.service` + `.timer`, `enable --now`.
3. Set `GHL_LOC`, `SLACK_OPS_CHANNEL`, and (optional) `WATCHDOG_ESCALATE_MENTION`.
4. Confirm one run logs `status: healthy`. Done — the client is now self-healing.
