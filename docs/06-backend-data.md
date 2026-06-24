# 06 — Backend & Data (the spine)

**Supabase is the single source of truth.** The brain reads/writes it, the Face mirrors it, the Hands log to it. No competing knowledge bases. Twenty CRM is a read/work mirror, not a second truth.

> Note on names: SDR Flo standardizes the table names below. Existing installs (Setter Flo / Takeoff) keep their stable identifiers (`sales_flo_leads`, `setter_flo_conversations`) — renaming live infra is pure churn. New installs use the standardized names; the shapes are identical.

## Core tables

### `leads` (intake + pipeline state) — source of truth for a lead
`lead_id` (pk), `source` (form/imessage/ig/tiktok/sms/webinar/cold), `name`, `email` (unique), `phone` (unique, E.164), `company`, `role`, `revenue`, `budget`, `offer_interest`, `pain_points[]`, `urgency`, `qualification_status` (open/engaged/qualified/converted/closed), `lead_score`, `stage`, `tags[]`, `form_context` (jsonb), `opener`, `raw` (jsonb), `created_at`, `updated_at`.

### `conversations` (per-lead state + transcript) — indexed by lead + phone
`lead_id`, `phone`, `name`, `stage`, `inbound_count`, `outbound_count`, `last_activity`, `converted`/`booked` (**sticky — never downgrade**), `event_id`, `start_iso`, `meet_link`, `reminder_flags` (jsonb), `opted_out`, `followup_attempts`, `next_followup_at`, `transcript`.

### `lead_intel` (AI-enriched profile)
`lead_id`, `profile_summary`, `segment`, `persona`, `company`, `role_guess`, `email_type`, `fit_score`, `intent_score`, `urgency_score`, `pain_hypotheses[]`, `buying_signals[]`, `objection_risks[]`, `recommended_angle`, `talking_points[]`, `icebreaker`, `next_best_action`, `confidence`, `sources[]`, `input_digest` (re-profile on change).

### `events` (behavioral log + scoring)
`lead_id`, `event_type` (inbound/outbound/form_submit/book/sell/remind/escalate/close/no_show), `timestamp`, `stage`, `metadata` (jsonb). Idempotent via an idempotency key.

### `conversations_log` / multi-channel inbox
`lead_id`, `channel` (imessage/sms/ig/tiktok/email/web/voice), `direction`, `sender`, `content`, `sequence_name` (`ai-setter:<channel>`), `sent_at`, `metadata`. Powers the unified inbox in the Face.

### `acquisition_sources` (attribution + performance)
`source_label`, `period_date`, `total_count`, `engaged_count`, `converted_count`, `closed_count`, `cost_per_source`. First-touch + multi-touch attribution per channel/campaign.

## Pipeline

```
inbound (any channel) → relay → leads (upsert on email/phone dedup) + events + conversations_log
                                      │
                          lead-intel (enrichment, idempotent on input_digest)
                                      │
                          lead-pipeline (10 min) → Twenty CRM mirror
                                      │
                          scoreboard / optimizer read leads + conversations + events
```

## Twenty CRM mirror (the Face's CRM)
Read-model only. `lead-pipeline.py` mirrors `leads` → Twenty (Person + Opportunity + Note), stage-mapped (NEW/SCREENING/MEETING/PROPOSAL/CUSTOMER). Twenty runs in docker on the pod; API key in the pod `.env` only. Supabase stays the truth; Twenty is where the operator works.

## Auth & secrets
- Supabase **service-role** key for agent writes (server-side only); **anon** key for read-only dashboards. In the profile `.env`, mode 0600, never in git/docs/logs.
- GHL PIT, Retell key, Photon/Twilio/Gmail creds — same rule. The repo ships **placeholders/env names only**.

## Doctrine
- One system of record (Supabase). No competing stores.
- Idempotent writes (dedup by email/phone + idempotency keys).
- Per-client database/namespace — no cross-client bleed. Client can export their Supabase anytime (portability).
