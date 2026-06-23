# 08 — Training the agent

How a Flo gets good: authored once (SOUL + skill), trained in-channel, and improved automatically by the intelligence layer.

## Author the brain
- **`SOUL.md`** — identity, voice, the one objective, the hard rules (continuity, destination, no-dash, no internal tool names, escalation). Loaded fresh every message (no restart needed). Start from [../templates/soul/SOUL.template.md](../templates/soul/SOUL.template.md) and fill the client's offer, persona, objective, qualification, and proof points.
- **`skills/appointment-setter/SKILL.md`** — the stage machine. Start from [../templates/skill/appointment-setter.SKILL.md](../templates/skill/appointment-setter.SKILL.md); adjust the qualification gate and the Stage-8 convert step for the motion.
- Skills are additive files discovered by the engine — drop in a new `SKILL.md` and it is available.

## Train in-channel, not in config files
The fastest way to shape a Flo is to **talk to it** in its own channel (Telegram/Slack for ops, or the live lead channel in a test thread) and correct it. It applies feedback within the session. Then **persist** the durable lessons:
- tone/identity changes → `SOUL.md`
- new procedure → a skill `SKILL.md`
- channel tokens / limits → `config.yaml` / `.env`
- strategic decisions → the vault

Do not try to pre-program every case in config. Author the frame, train the edges in-channel, persist what sticks.

## Let the intelligence layer do the rest
Once live, the optimizer (see [05-intelligence.md](05-intelligence.md)) reads the scoreboard nightly and proposes safe, evidence-backed prompt improvements — gated so it never breaks the core. This is the agent training itself from real conversations, with a human-reviewable shadow period first.

## Memory & continuity
- Per-lead profile + last ~40 turns drive every reply (the relay injects them).
- Conversation state is mirrored to the spine; warm leads resume mid-stage across sessions.
- Operator-level learnings and decisions live in the vault (read by the agent, written via the agent-outbox, not edited directly).

## Hardening checklist (before go-live)
Run the adversarial gauntlet: injection-reveal, role-swap, angry/refund→escalate, existing-client→escalate, off-topic, bot-test, plus the motion gauntlet (continuity/no-restart, drive-to-objective, qualify, no-dash, stop). The same gauntlet is what the optimizer uses to gate every future change — so writing good scenarios here pays off forever.
