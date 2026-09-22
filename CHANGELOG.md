# Changelog

## v0.7.4 — 2026-09-22 — Opener delivery receipt
- The relay stores a pending opener before sending and marks consent only after the provider id is read back as sent or delivered.
- A failed or unconfirmed send is not retried, so a lost response cannot create a second opener. A pending row alone is not treated as delivery.

## v0.7.3 — 2026-09-22 — Client copy on the relay send path
- Opt-in sends the configured opener. It does not invent an inbound lead message.
- Slot offer, booking confirmation, follow-up, and qualification questions come from a client file. Defaults stay generic.
- A private CLI writes one short-lived access code to a file and does not print it.

## v0.7.2 — 2026-09-22 — Relay-owned demo access and GHL pull
- `/opt-in` and `/pull` check a signed, single-use access code on the relay. Provider calls stay off unless the relay is live.
- GHL conversation reads live in the relay, not in the public app.

## v0.7.1 — 2026-09-22 — Persistent relay inbound
- The relay HTTP server keeps consent and conversation state across inbound posts.
- Messages from before consent are stored as skipped and do not send. Booking stays off unless the relay is live.
- Optional Loop sender is used only when `RELAY_SENDER=loop` and the relay is live. Default send path is unchanged.

## v0.7.0 — 2026-09-22 — Relay consent gate and GHL booking tools
- Added a client-agnostic STOP/opt-out gate and one-time confirmation in the relay. A later message does not re-enter the model.
- Added GHL free-slot and appointment tools. Slots offered to a lead come from the provider payload. A booking is confirmed only after the appointment receipt includes matching `id`, `calendarId`, `locationId`, `contactId`, and `startTime`.
- Added inbound event idempotency so a repeated provider message does not send or book twice.
- No service install, timer, or live relay is started by this change.

## v0.6.0 — 2026-08-11 — Nightly sales-call audit intelligence
- Added an evidence-backed transcript audit contract with strict validation and timestamped quote requirements.
- Added deterministic JSON + Markdown reports for three distinct jobs: Marketing message correction, Sales Manager coaching, and Owner unfiltered operating truth.
- Added portable CLI, client configuration reference, privacy/routing doctrine, rollout guidance, and automated tests.

## v0.5.0 — 2026-06-27 — Pluggable brain + proactive uptime watchdog (100% uptime)
Hardened from a live 26h outage: a setter's brain ran on a Claude Max OAuth token **shared across two VMs**; the token rotated, died silently, and every lead got `502` with no one watching. Two upgrades, generalized for every client (no client data replicated):
- **Pluggable brain** (`templates/relay/agent_service.py`): the reasoning call now takes any OpenAI-compatible endpoint via `RELAY_BRIDGE`/`RELAY_MODEL`/`RELAY_BRAIN_KEY` + `RELAY_BRAIN_MAX_TOKENS`, with a `reasoning_content` fallback. **A dedicated provider API key (e.g. GLM `glm-4.6`) never expires and is single-tenant — the shared-OAuth failure mode is gone.** New default model `glm-4.6` (avoid `glm-5.2` for real-time: reasoning-heavy, empty without huge budgets).
- **Uptime watchdog** (`templates/watchdog/`): a self-contained systemd timer on the client's VM that is **proactive — spot → fix → report**. Restarts a downed agent, clears brain stalls, and re-pokes any conversation left waiting so the agent answers — then reports *what it saw and fixed*. Only @mentions a human for the rare unfixable (e.g. provider balance). New doc: `docs/10-uptime-watchdog.md`.
- **Scrubbed** `templates/intelligence/config.example.json` to a generic placeholder (removed a prior client's link slug, rep name, offer figures, and paths).

## v0.4.0 — 2026-06-24 — Instagram social-CTA channel (comment->DM->qualify->book)
First social channel adapter, `templates/channels/instagram/` — **official Meta Graph API only** (no unofficial/private API). Lifted the best open-source patterns (InstaAuto comment->DM + Supabase shape, ig-mcp official send paths) into our own brain-owning implementation.
- Comment "FLO" keyword router -> public reply + private DM opener; DM replies route to the SDR Flo brain (NEPQ) to qualify + book.
- Per-niche persona = **Byram's voice** (`SOUL.byram.md`) for Client Zero (his personal IG) — speaks as Byram, never "Flo" or any internal name.
- Shadow-first (`SDR_FLO_DRAFT_ONLY=true`), idempotent (comment+message ids), suppression (opt-out/guard tags), no dashes, never fakes a booking. Writes leads/conversations/events/sources to the spine.
- 10 tests + fixtures pass offline/dry-run; end-to-end dry-run proof verified.


## v0.3.0 — 2026-06-24 — Canonical + field-hardening + sales-brain reference
- **Made sdr-flo the canonical framework** + locked the naming contract (SDR Flo / Setter Flo / Sales Flo / Agent Flo) in the README. `agent-flo/sales_flo` is now a reference implementation that conforms to this framework.
- **Folded in agent-flo's sales-brain reference** at `templates/workflows/` (typed data model, qualify scoring, intent + **disposition taxonomy**, call-intelligence, daily report, escalation, sticky-suppression).
- **Field-hardened the relay** from the live Takeoff debugging:
  - **Keyword-OR-tag gate** — engage on enable-tag OR a campaign keyword (self-tag on keyword), so a flaky CRM tagging workflow can't silently block the whole pipeline.
  - **Channel send-fallback** — retry SMS/Email/FB on a 422 (one CRM location holds IG + SMS leads; wrong type = silent non-delivery).
  - **Guard tags = intentional kill switches only** (removed the mass-applied "ai off" trap) + a recovery-sweep note.

## v0.2.0 — 2026-06-23 — Outbound module
Added `docs/09-outreach.md`: the cold outbound engine framework, folding the existing DigitalFlo Cold Outreach Engine (`digitalflo-app`, 2026-05-07) together with 2026 winning practices from fresh research.
- **Deliverability-first** (Layer 0): separate aged domains, pre-warmed mailbox pools, SPF/DKIM/DMARC, ~25–30 sends/inbox/day, continuous warmup, performance-based inbox rotation, bounce/spam guardrails.
- **Signal-first targeting** (Layer 1): every prospect anchored to a buying signal (the 5x lever — 15–25% vs 3.43% reply).
- **Waterfall enrichment** (Layer 2), signal-led 12-point research + scoring (Layer 3), gift-first proof asset (Layer 4).
- **Copy** (Layer 5): signal-anchored opener (compliment openers banned), <80 words, soft CTA.
- **Cadence** (Layer 6): 4–6 touches, 3-7-7 timing, value-add each touch, break-up email, multichannel.
- **Fold-in** (Layer 7–8): positive replies route into the NEPQ brain; email via the Gmail connector; metrics (reply/positive-reply north star) into the intelligence layer.
- Kept the existing build (model, 8-table schema, API, UI, gifts) as the control plane; listed runtime build tickets.

## v0.1.0 — 2026-06-23 — Initial framework
First canonical SDR Flo framework, distilled from Takeoff Financial, Setter Flo (Client Zero), LGH, and CommunityFlow.

- **README + PRD** — vision, four-layer architecture, single-tenant doctrine, non-negotiables.
- **docs/** — architecture, channels (IG/FB/TikTok/SMS/iMessage/email/voice/webinar), the NEPQ brain + stage machine, the four objectives (book/community/sell/webinar), the intelligence layer, the Supabase spine + data model, deployment, training.
- **templates/relay/** — generalized channel relay (fail-closed tag gate, per-contact isolation, continuity + destination, dash-strip, degenerate-suppression, retry, dry-run, GHL Conversations adapter).
- **templates/intelligence/** — scoreboard + champion/challenger optimizer (protected core, gauntlet, materiality gate, versioning, auto-rollback, shadow→live).
- **templates/soul/** + **templates/skill/** — SOUL template (with protected sections) + the appointment-setter stage-machine skill.
- **templates/deploy/** + **templates/channels/** — systemd units, env example, per-channel config.

### Roadmap
- Cold **email outreach** engine (sequencer + warmup + deliverability).
- Real-time push (replace polling). Shared fleet operator dashboard. Voice-provider abstraction layer.
