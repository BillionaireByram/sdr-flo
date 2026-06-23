# Changelog

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
