# SDR Flo

**The canonical DigitalFlo framework for AI client-acquisition agents.** One install pattern that captures, qualifies, books, sells, and follows up across every channel — DM (Instagram, TikTok, Facebook), SMS, iMessage, email, and voice — runs the same NEPQ sales brain everywhere, keeps score, and gets smarter on its own.

> Build it once here. Deploy it per client. Never start from scratch again.

This repo is the distilled output of every setter/SDR we have shipped — Takeoff Financial, Setter Flo (Client Zero), LGH, CommunityFlow — turned into a reusable, documented, templated framework.

---

## What SDR Flo is

SDR Flo is a **single-tenant, per-client AI Sales Development Rep**. Each client gets their own install: their own agent ("Flo" to the lead), their own number/inbox, their own calendar, their own data. It does the full top-of-funnel acquisition job:

- **Capture** every inbound lead from every channel into one brain.
- **Qualify** with a real sales framework (NEPQ + Cole Gordon setter method + SPIN), gap-filling until each gate is met.
- **Convert** to whatever the objective is: *book a call*, *push to a community / webinar*, or *sell a low-ticket offer*.
- **Follow up** on a deterministic ladder, remind booked leads, reactivate cold ones.
- **Keep score** of every conversation and action, and **self-optimize** the prompt over time — safely.

It is not a chatbot. It is an operator that runs a lead from first touch to objective and learns from every conversation.

## The four layers

| Layer | Role | What runs it |
| --- | --- | --- |
| **Brain** | One Flo: qualify, convert, follow up, reactivate, self-improve | AI Flo / Hermes agent (Codex or client Claude Max — **zero API credits**) + the NEPQ stage machine |
| **Spine** | Single source of truth for every lead, message, event, score | **Supabase** (`leads`, `conversations`, `events`, `lead_intel`, `acquisition_sources`) |
| **Face** | Where the operator sees the business | Operator dashboard + Twenty CRM (read/work surface over the spine) |
| **Hands** | Reach the lead + take action | Channel adapters (GHL Conversations, Photon iMessage, Twilio, Gmail), Retell voice, Google Calendar |

## The channels (one brain behind all of them)

| Channel | How it connects | Doc |
| --- | --- | --- |
| Instagram / Facebook DM | GHL Conversations relay | [docs/02-channels.md](docs/02-channels.md) |
| TikTok DM | GHL native TikTok → Conversations relay | [docs/02-channels.md](docs/02-channels.md) |
| SMS | GHL SMS or Twilio | [docs/02-channels.md](docs/02-channels.md) |
| iMessage | Photon line + sidecar | [docs/02-channels.md](docs/02-channels.md) |
| Email | Gmail connector (IMAP/SMTP) or AgentMail | [docs/02-channels.md](docs/02-channels.md) |
| Voice | Retell (or any provider), warm-only | [docs/02-channels.md](docs/02-channels.md) |
| Webinar funnel | WebinarKit / Zoom → registration + attendance | [docs/02-channels.md](docs/02-channels.md) |

## The intelligence layer (keeps score + gets smarter)

Every install ships with the **scoreboard + self-optimizer**:
- **Scoreboard** tallies every conversation + action, scores objective hits, writes a plain-English daily/weekly report.
- **Optimizer** reads the scoreboard, analyzes real transcripts, and — only when a challenger *measurably beats* the live prompt on a fixed test, without touching a protected core — promotes a better prompt. Versioned, auto-rollback, forward-only, evolve-only-when-needed.

See [docs/05-intelligence.md](docs/05-intelligence.md). Engine in [templates/intelligence/](templates/intelligence/).

## Repo map

```
sdr-flo/
├── README.md                  ← you are here
├── PRD.md                     ← the canonical product spec
├── docs/
│   ├── 01-architecture.md     ← four layers, high-level integration
│   ├── 02-channels.md         ← every channel: contracts, endpoints, gotchas
│   ├── 03-the-brain.md        ← SOUL, NEPQ stage machine, profiles, isolation, hardening
│   ├── 04-objectives.md       ← book / community / sell / webinar — how to configure each
│   ├── 05-intelligence.md     ← scoreboard + champion/challenger optimizer
│   ├── 06-backend-data.md     ← Supabase spine, Twenty CRM, the data model
│   ├── 07-deployment.md       ← VM, systemd, auth (no API credits), per-client install
│   ├── 08-training-hermes.md  ← author SOUL/skills, train in-channel
│   └── 09-outreach.md         ← cold outbound: deliverability, signals, copy, cadence
├── templates/
│   ├── relay/                 ← the channel relay (capture → reason → reply)
│   ├── intelligence/          ← scoreboard + optimizer engine + config
│   ├── soul/                  ← SOUL.template.md
│   ├── skill/                 ← appointment-setter SKILL.md (the stage machine)
│   ├── channels/              ← per-channel adapter config + notes
│   └── deploy/                ← systemd units, install.sh, env templates
└── CHANGELOG.md
```

## Quickstart (new client)

1. Read [docs/07-deployment.md](docs/07-deployment.md) and [PRD.md](PRD.md).
2. Stand up the client VM (or pod), install the AI Flo engine, create an isolated profile.
3. Fill `templates/soul/SOUL.template.md` with the client's offer, persona, and **objective** (book / community / sell / webinar).
4. Wire the channels the client uses ([docs/02-channels.md](docs/02-channels.md)) into the relay.
5. Point the spine at the client's Supabase ([docs/06-backend-data.md](docs/06-backend-data.md)).
6. Drop in the intelligence layer ([templates/intelligence/](templates/intelligence/)), start in shadow mode.
7. Dry-run the gauntlet, then go live one channel at a time.

## Non-negotiables

- **Single-tenant, per-client installs.** No multi-tenant build. One seat per client.
- **Zero API credits.** Codex subscription or the client's own Claude Max. Never bill per-token.
- **Supabase = single source of truth.** No competing knowledge bases.
- **No dashes** in anything a lead sees. **Never name internal tools** to a lead (it is "Flo" / "your AI operator").
- **Build complete or not at all.** Verify end-to-end before claiming done.

## Roadmap

- Cold **outbound** engine — framework specced in [docs/09-outreach.md](docs/09-outreach.md) (deliverability-first, signal-anchored, gift-first, 3-7-7 multichannel, replies routed into the brain). Runtime build next.
- Real-time push (sub-second) instead of polling.
- Shared operator dashboard across the fleet.

See [CHANGELOG.md](CHANGELOG.md).
