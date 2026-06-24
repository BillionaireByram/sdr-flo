# Sales-brain workflows (reference implementation)

Clean, typed, unit-tested Python reference for the SDR Flo sales brain, folded in from the `agent-flo` codebase (`BillionaireByram/agent-flo`, `src/agent_flo/sales_flo/`). This is the **logic layer** that complements the relay (transport), the SOUL/skill (persona + stage machine), and the intelligence layer (self-optimization).

> **Canonical relationship:** `sdr-flo` (this repo) is the **canonical framework**. `agent-flo/sales_flo` is a **reference implementation** of these workflows. When they differ, sdr-flo's doctrine wins; agent-flo should conform to it. These files are vendored here so the framework is self-contained.

## Files
- `models.py` — the **typed data model**: `Lead`, `FormIntake`, `SalesCall`, `CallIntelligence`, `FollowUpTask`, with `Literal` taxonomies for source, qualification status, stage, urgency, disposition, follow-up type/channel/status. Use this as the canonical shape for the spine ([../../docs/06-backend-data.md](../../docs/06-backend-data.md)).
- `workflows.py` — the pure functions of the sales brain:
  - `create_lead_from_form`, `draft_inbound_opener` (context-aware opener using source/pain), `classify_intent` (booking / pricing / proof / disqualified / needs_more_info)
  - `qualify_lead` (transparent fit/intent/urgency/budget scoring), `should_suppress_sales_nurture` (sticky: booked/customer/human-owned/opted-out never get sold to)
  - `score_call` → `CallIntelligence`, `classify_disposition`, `create_followup_task`, `should_escalate_to_supervisor`, `generate_daily_report`
- `integrations.py` — thin integration seam (GHL etc.). The relay's channel adapters ([../../docs/02-channels.md](../../docs/02-channels.md)) are the broader version.
- `inbound_reply.md` — the inbound-reply prompt.

## The disposition taxonomy (valuable IP — keep)
Post-call/lost-reason classification, reused across every client for the intelligence loop and reporting:
`financially_unqualified · uncertain_about_offer · too_many_unanswered_questions · spousal_objection · macro_event_blame · timing_issue · trust_deficit · no_show · closed_won · other`

## The lead stages
`new · engaged · qualified · booked · showed · closed_won · closed_lost · no_show · nurture`

## How it fits
- The **relay** receives a message → the **SOUL/skill** runs the stage machine → these **workflows** structure the lead, score, classify, suppress, and (post-call) produce intelligence + the daily report → the **intelligence layer** turns the dispositions + scoreboard into prompt improvements.
- Channel-wise, agent-flo's original is thin (email/GHL/webinar); the full multi-channel transport lives in the relay + channels doc. Use these workflows for the **brain logic**, the relay for **transport**.
