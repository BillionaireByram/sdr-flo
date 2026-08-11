# PRD — SDR Flo (DigitalFlo's AI Client-Acquisition Agent)

> **Status:** canonical · **Owner:** Byram · **Updated:** 2026-06-23
> Single source of truth for what SDR Flo is and how it is built. Distilled from Takeoff Financial, Setter Flo (Client Zero), LGH, and CommunityFlow.

## 1. Vision

One AI operator — **Flo** — that runs a business's entire top-of-funnel: captures every lead from every channel, qualifies with a real sales framework, converts to the objective (book / community / sell / webinar), follows up, reactivates, keeps score, and gets smarter every night. Installed per client, branded as theirs.

## 2. Operating model — single-tenant, installed per client

- Each client gets their **own** install: their agent (Flo), their number/inbox, their calendar, their Supabase, their credentials.
- Isolation is **physical** (separate installs/profiles), not logical tenancy.
- **One seat per client** — no shared Claude Max / Codex across clients.
- **Zero API credits**: Codex subscription (`gpt-5.5`, ChatGPT backend) or the client's own Claude Max via a local CLI bridge. The runtime never calls a metered API directly.

## 3. What it does — the jobs

SDR Flo is configured to ONE primary objective per motion (a client can run several motions):

| Motion | Objective | Conversion event | Example |
| --- | --- | --- | --- |
| **Book** | Qualify → book a call | Calendar event created | Takeoff BFP, LGH strategy call |
| **Community** | Nurture → push to a paid/free community | Tracked link sent + joined | a paid community, CommunityFlow |
| **Sell** | Qualify → sell a low-ticket offer | Checkout link / payment | low-ticket SLO |
| **Webinar** | Qualify → register + show up to a training | Registration + attendance | LGH workshop |

All motions run the **same NEPQ stage machine**; only the final "close" stage and the objective marker change.

## 4. Architecture — four layers

**Brain** — one Flo across text + voice. **Pluggable reasoning backend** (OpenAI-compatible): a dedicated provider API key (GLM `glm-4.6`, recommended — never expires, single-tenant), Codex (`ai-flo -z`), or a client Max bridge. NEPQ + Cole Gordon + SPIN stage machine. Per-lead profile, injection-hardened, escalation triggers, self-improving.

**Spine** — Supabase, the single source of truth: `leads`, `conversations`, `events`, `lead_intel`, `acquisition_sources`. (Names standardized here; existing installs keep `sales_flo_leads` / `setter_flo_conversations` as stable identifiers.)

**Face** — operator dashboard + Twenty CRM as read/work surfaces over the spine.

**Hands** — channel adapters (GHL Conversations, Photon iMessage, Twilio, Gmail), Retell voice, Google Calendar booking.

**Guardian** — a proactive uptime watchdog on the client's own VM (spot → fix → report): heals a downed agent/brain and re-pokes any waiting conversation so no lead is ever left unanswered. See [docs/10-uptime-watchdog.md](docs/10-uptime-watchdog.md).

See [docs/01-architecture.md](docs/01-architecture.md).

## 5. Channels — capture + reach everything

Native gateway channels (Telegram/Discord/Slack) bind directly. Everything a lead actually uses — **IG, FB, TikTok, SMS, iMessage, email, voice** — comes through an **adapter/relay**: inbound webhook → relay → one-shot reasoning over the brain → reply via the channel's send API. One brain, one lead record, every channel. See [docs/02-channels.md](docs/02-channels.md).

### Instagram organic-content CTA (built)
IG can run two ways: via **GHL Conversations** (the Takeoff path) or **direct official Meta Graph API** (no GHL). The direct-API channel is built at [templates/channels/instagram/](templates/channels/instagram/): a lead **comments a keyword** (e.g. "FLO") on a post → keyword router → public reply + private DM opener → DM replies route into the brain to qualify + book. **Official Graph API only** — never the unofficial/private API (account-ban risk). Shadow-first, idempotent, suppression-gated, never fakes a booking. This is the reusable social-CTA module every future client gets.

### Persona is per-niche config (not a fork)
The lead-facing persona is a config layer. Default is **"Flo."** For Client Zero (Byram's personal IG) the persona is **Byram himself** (`SOUL.byram.md`) — same SDR Flo brain + stage machine, different voice. Swap the persona per client/niche; never fork the framework for it.

## 6. The lead lifecycle (the loop)

```
CAPTURE → PROFILE → SCORE → SPEED-TO-LEAD → QUALIFY (stage machine)
   → CONVERT (book / community / sell / webinar) → FOLLOW-UP → REACTIVATE → LEARN ↺
```

- **Capture:** any channel writes a lead + first-touch source (idempotent).
- **Profile:** enrichment builds a per-lead intel profile; Flo opens with context, never re-asks.
- **Qualify:** the stage machine (Open → Situation → Problem → Cost → Desire → Qualify → Transition → Convert → Lock-in), gap-filling each gate, skipping ahead for warm leads.
- **Convert:** motion-specific close (book on Google Calendar / send the tracked community link / send checkout / drive registration). Sticky once converted.
- **Follow-up:** deterministic ladder (30m / 1d / 3d / 7d) for quiet leads; 24h + 2h reminders for booked.
- **Reactivate:** score-decay re-engagement.
- **Learn:** the intelligence layer turns outcomes into prompt improvements.

See [docs/03-the-brain.md](docs/03-the-brain.md) and [docs/04-objectives.md](docs/04-objectives.md).

## 7. Intelligence — scoreboard + self-optimization

- **Scoreboard** tallies every conversation + action, scores objective hits, writes a plain-English daily snapshot + weekly report. This is the metric the optimizer reads.
- **Nightly call audit** reviews each completed recorded sales call once and produces three least-privilege reports: Marketing gets upstream message/expectation fixes, the Sales Manager gets rep coaching and training actions, and the Owner gets the raw unfiltered operating view. This is a reusable client module for any approved transcript source.
- **Optimizer** (champion/challenger, eval-gated): only promotes a new prompt if it beats the live one on a fixed gauntlet, keeps a protected core verbatim, stays in size bounds, and regresses nothing. Versioned + auto-rollback. Materiality-gated (evolve only when needed). Fail-safe (bridge down → no change). Ships in shadow mode; flip one flag to go live.

See [docs/05-intelligence.md](docs/05-intelligence.md).

## 8. Data model (spine)

`leads` (intake + pipeline state), `conversations` (per-lead state + transcript + booking, sticky), `lead_intel` (AI-enriched 12-point profile), `events` (behavioral log + scoring), `acquisition_sources` (attribution + performance). Mirror to Twenty CRM. See [docs/06-backend-data.md](docs/06-backend-data.md).

## 9. Deployment

Per-client VM (Proxmox) or pod. One AI Flo engine, an isolated profile per agent (`HERMES_HOME`), systemd services + timers. Codex auth (no API key) or client Max bridge. Channels wired via the relay. Supabase as the spine. See [docs/07-deployment.md](docs/07-deployment.md).

## 10. Install/duplication (Client → Client N)

1. New Supabase project (the spine).
2. Channel lines: GHL location (IG/FB/TikTok/SMS), Photon line (iMessage), Twilio (SMS fallback), Gmail (email), Retell agent+number (voice).
3. Client Google Calendar (booking).
4. Client persona + objective in `SOUL.md` + skill.
5. Deploy the relay + intelligence layer; seed offer/qualification config.
6. Shadow → dry-run gauntlet → live one channel at a time.

## 11. Non-negotiables

- Single-tenant, per-client. One seat per client. Zero API credits.
- Supabase = single source of truth.
- No dashes lead-facing. Never name internal tools to a lead.
- Verify end-to-end before claiming done. Non-destructive optimization only.

## 12. Roadmap

Cold outbound engine — framework in [docs/09-outreach.md](docs/09-outreach.md) (deliverability-first, signal-anchored, gift-first, 3-7-7 multichannel, replies → the brain); runtime build next · **Instagram v2** (value-post → gift-for-email/phone with per-post tracked links) · **Chatwoot DM inbox / human-handoff** surface · real-time push · shared fleet dashboard · richer voice provider abstraction.
