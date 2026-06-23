# Changelog

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
