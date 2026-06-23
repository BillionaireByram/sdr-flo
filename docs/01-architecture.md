# 01 — Architecture

SDR Flo is four layers. Keep them separate; never collapse them.

```
        ┌──────────────────────── BRAIN ────────────────────────┐
        │  One Flo: NEPQ stage machine, per-lead profile,        │
        │  injection-hardened, self-improving.                   │
        │  Runs on AI Flo / Hermes (Codex or client Claude Max). │
        └───────────────▲───────────────────────┬───────────────┘
                        │ reason                 │ act
        ┌───────────────┴───────────┐   ┌────────▼───────────────┐
        │          HANDS            │   │         SPINE          │
        │ channel adapters + relay  │   │  Supabase = truth      │
        │ GHL / Photon / Twilio /   │   │  leads, conversations, │
        │ Gmail / Retell / Calendar │   │  events, lead_intel,   │
        └───────────────▲───────────┘   │  acquisition_sources   │
                        │               └────────▲───────────────┘
                   lead │ channel                │ read/work
        ┌───────────────┴───────────────────────┴───────────────┐
        │                         FACE                           │
        │      operator dashboard  +  Twenty CRM (mirror)        │
        └────────────────────────────────────────────────────────┘
```

## Brain
One operator identity ("Flo" to the lead). Reasoning runs on the AI Flo (Hermes) engine, **Codex `gpt-5.5`** or the client's **Claude Max** via a local CLI bridge — never a metered API. The brain is channel-agnostic: it receives a normalized message + the lead's history + profile and returns `{reply, actions, profile}`. Voice (Retell) and text are two surfaces of the same brain and the same lead record. See [03-the-brain.md](03-the-brain.md).

## Spine (truth)
Supabase holds every lead, message, event, score, and source. Nothing competes with it. The brain reads/writes the spine; the Face reads it; the Hands log to it. See [06-backend-data.md](06-backend-data.md).

## Face
The operator dashboard + Twenty CRM are **read/work surfaces** over the spine, not separate databases. The operator sees every conversation, where each lead came from, and what Flo did.

## Hands
Two integration shapes:
- **Native gateway channels** (Telegram, Discord, Slack) — the agent gateway binds the platform directly.
- **Adapter/relay channels** (IG, FB, TikTok, SMS, iMessage, email, voice) — a lightweight relay receives an inbound webhook, calls the brain one-shot, and sends the reply via the channel's API. This is how a non-native channel reaches the same brain. See [02-channels.md](02-channels.md).

## The relay (the load-bearing pattern)
Most client channels are not gateway-native, so the **relay** is the standard integration:

```
channel inbound (webhook)  →  relay :PORT/inbound
    validate secret → normalize {contact_id, text, channel, tags, name, phone, email}
    fail-closed tag gate (only engage tagged/opted-in contacts)
    load per-contact history + profile (SQLite local, never mix contacts)
    one-shot reasoning over the brain (Codex/Max), with the SOUL + skill
    → {reply, actions, profile}
    strip dashes · suppress degenerate/empty output · retry on bad output
    send reply via channel adapter (GHL Conversations / Twilio / Photon / SMTP)
    apply tags · mirror to Supabase (conversations + events, channel-tagged)
```

Reference implementation: [../templates/relay/agent_service.py](../templates/relay/agent_service.py) (generalized from the Takeoff Setter). Key invariants baked in:
- **Fail-closed tag gate** — only respond to contacts carrying the client's enable tag (checked against the CRM live, not just the webhook payload).
- **Per-contact isolation** — history keyed by contact id; conversations never bleed.
- **Continuity + destination** — never restart mid-conversation; always drive to the objective.
- **Dash-free, no internal tool names, no degenerate/empty sends.**
- **Dry-run gate** (`*_LIVE=false`) — compose + log without sending, for validation.

## Single-tenant doctrine
Every client is a physically separate install (own VM/profile, own Supabase, own credentials). No cross-client compute or data. This is the security model and the "one seat per client" rule. See [07-deployment.md](07-deployment.md).
