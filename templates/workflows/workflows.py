from __future__ import annotations

from hashlib import sha1
from typing import Iterable

from agent_flo.sales_flo.models import CallIntelligence, FollowUpTask, FormIntake, Lead, SalesCall, now_ts

HIGH_VALUE_TERMS = ("enterprise", "partnership", "investor", "acquisition", "board", "media", "legal", "custom", "pricing")
BUYING_SIGNAL_TERMS = ("book", "ready", "start", "urgent", "this week", "budget", "contract", "like the offer")
TRUST_TERMS = ("trust", "proof", "case study", "guarantee", "scam", "reputation")
SUPPRESSION_TAGS = ("booked", "customer", "client", "existing-client", "human-owned", "ai-paused", "do-not-contact", "opted-out", "unsubscribe", "refund", "billing", "support")
CLOSED_STAGES = {"booked", "showed", "closed_won"}



def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}-" + sha1("|".join(parts).encode()).hexdigest()[:12]


def should_suppress_sales_nurture(lead: Lead) -> bool:
    tag_text = " ".join(lead.tags).lower()
    if lead.stage in CLOSED_STAGES:
        return True
    return any(tag in tag_text for tag in SUPPRESSION_TAGS)


def create_lead_from_form(intake: FormIntake) -> Lead:
    lead = intake.to_lead()
    return qualify_lead(lead)


def build_lead_memory(lead: Lead) -> str:
    context = lead.form_context or {}
    raw_answers = context.get("raw_answers") or {}
    lines = [
        f"# Lead: {lead.name or lead.id}",
        "",
        f"Source: {lead.source}",
        f"Public persona: {lead.public_persona_name}",
        f"Stage: {lead.stage}",
        f"Qualification: {lead.qualification_status} ({lead.lead_score:.0f})",
        f"Company: {lead.company or 'unknown'}",
        f"Role: {lead.role or 'unknown'}",
        f"Offer interest: {lead.offer_interest or 'unknown'}",
        f"Pain points: {', '.join(lead.pain_points) if lead.pain_points else 'unknown'}",
        f"Business context: {context.get('business_context') or 'unknown'}",
        f"Referral context: {context.get('referral_context') or 'none'}",
        f"Event/webinar context: {context.get('event_context') or 'none'}",
        "",
        "## Raw form answers",
    ]
    if raw_answers:
        lines.extend(f"- {k}: {v}" for k, v in raw_answers.items())
    else:
        lines.append("- none")
    lines.extend(["", "## Conversation notes"])
    lines.extend(f"- {note}" for note in lead.notes) if lead.notes else lines.append("- none yet")
    return "\n".join(lines) + "\n"


def draft_inbound_opener(lead: Lead, *, demo_mode: bool = False) -> str:
    if should_suppress_sales_nurture(lead):
        return "Suppressed: this lead is already booked/customer/human-owned/opted out."
    name = lead.name or "there"
    pain = lead.pain_points[0] if lead.pain_points else None
    context = lead.form_context or {}
    event = context.get("event_context")
    if event and pain:
        return f"{name}, it's Flo. Saw you came in from {event}. You flagged {pain}, how are you handling that right now?"
    if event:
        return f"{name}, it's Flo. Saw you came in from {event}. What's the biggest thing slowing your growth down right now?"
    if pain:
        return f"{name}, it's Flo. You just filled out our form, you said {pain} is the biggest thing slowing you down. How are you handling that right now?"
    return f"{name}, it's Flo. You just filled out our form. What's the biggest thing slowing your growth down right now?"


def classify_intent(text: str) -> str:
    t = text.lower()
    if any(term in t for term in ("book", "schedule", "calendar", "call")):
        return "booking_request"
    if any(term in t for term in ("price", "cost", "budget", "pay")):
        return "pricing_question"
    if any(term in t for term in ("case study", "proof", "results")):
        return "proof_request"
    if any(term in t for term in ("not interested", "unsubscribe", "stop")):
        return "disqualified"
    return "needs_more_info"


def qualify_lead(lead: Lead) -> Lead:
    score = 0.0
    if lead.email or lead.phone:
        score += 10
    if lead.offer_interest:
        score += 15
    if lead.pain_points:
        score += min(20, len(lead.pain_points) * 10)
    if lead.urgency == "high":
        score += 20
    elif lead.urgency == "medium":
        score += 10
    if lead.budget and lead.budget >= 10000:
        score += 20
    elif lead.budget and lead.budget >= 3000:
        score += 10
    if lead.revenue and lead.revenue >= 250000:
        score += 15
    if lead.role and any(term in lead.role.lower() for term in ("founder", "owner", "ceo", "director")):
        score += 10

    if score >= 75:
        status = "qualified"; stage = "qualified"
    elif score >= 45:
        status = "manual_review"; stage = "engaged"
    elif score >= 25:
        status = "needs_more_info"; stage = "engaged"
    else:
        status = "unqualified"; stage = "nurture"
    return lead.with_updates(lead_score=min(score, 100), qualification_status=status, stage=stage)


def classify_disposition(text: str) -> str:
    t = text.lower()
    if "spouse" in t or "wife" in t or "husband" in t or "partner" in t:
        return "spousal_objection"
    if "afford" in t or "expensive" in t or "money" in t or "budget" in t:
        return "financially_unqualified"
    if "timing" in t or "later" in t or "busy" in t:
        return "timing_issue"
    if any(term in t for term in TRUST_TERMS):
        return "trust_deficit"
    if "not clear" in t or "confused" in t or "questions" in t:
        return "too_many_unanswered_questions"
    if "no show" in t or "missed" in t:
        return "no_show"
    if "closed" in t or "paid" in t or "won" in t:
        return "closed_won"
    return "other"


def should_escalate_to_supervisor(lead: Lead, context: str, confidence: float = 0.9) -> bool:
    text = " ".join(filter(None, [lead.company or "", lead.role or "", lead.offer_interest or "", context])).lower()
    if confidence < 0.65:
        return True
    if lead.revenue and lead.revenue >= 1_000_000:
        return True
    return any(term in text for term in HIGH_VALUE_TERMS)


def score_call(lead: Lead, call: SalesCall) -> CallIntelligence:
    transcript = call.transcript_text or ""
    t = transcript.lower()
    quality = qualify_lead(lead).lead_score
    if any(term in t for term in BUYING_SIGNAL_TERMS):
        quality = min(100, quality + 15)
    objections = tuple(term for term in ("custom", "pricing", "legal", "trust", "timing") if term in t)
    buying_signals = tuple(term for term in BUYING_SIGNAL_TERMS if term in t)
    disposition = classify_disposition(transcript if transcript else call.outcome)
    escalate = should_escalate_to_supervisor(lead, transcript)
    reason = None
    if escalate:
        if objections:
            reason = "High-value or sensitive conversation with " + ", ".join(objections) + " concern."
        else:
            reason = "High-value or strategic opportunity requires supervisor review."
    next_action = "Draft personalized follow-up and route for approval."
    if call.outcome == "no_show" or disposition == "no_show":
        next_action = "Create rebooking sequence."
    elif call.outcome == "closed_won":
        next_action = "Create onboarding handoff."
    return CallIntelligence(
        id=_stable_id("intel", call.id, lead.id),
        call_id=call.id,
        lead_id=lead.id,
        lead_quality_score=quality,
        closer_score=75 if transcript else 0,
        call_score=min(100, (quality + (75 if transcript else 0)) / 2),
        buying_signals=buying_signals,
        objections=objections,
        disposition=disposition,
        summary="Call processed from transcript fixture." if transcript else "No transcript available.",
        what_happened=transcript[:240] if transcript else "Call outcome recorded without transcript.",
        why_not_closed=None if call.outcome == "closed_won" else disposition,
        recommended_next_action=next_action,
        followup_angle="proof and clarity" if disposition in {"trust_deficit", "too_many_unanswered_questions"} else "next best step",
        content_needed=("animation_brief",) if disposition in {"timing_issue", "trust_deficit"} else (),
        ava_escalation_required=escalate,
        ava_escalation_reason=reason,
    )


def create_followup_task(lead_id: str, disposition: str, channel: str = "email", call_id: str | None = None) -> FollowUpTask:
    messages = {
        "no_show": "Looks like we missed each other. Want me to send a fresh rebook link for a better time?",
        "spousal_objection": "I drafted a concise proof-based recap you can share before deciding on next steps.",
        "financially_unqualified": "I drafted a nurture follow-up with a lower-friction next step and useful context.",
        "timing_issue": "I drafted a rebook/follow-up angle around the cost of waiting and a lighter next step.",
        "trust_deficit": "I drafted a proof-first follow-up with case-study/context placeholders.",
    }
    ftype = "no_show" if disposition == "no_show" else "post_call"
    asset_type = "animation_brief" if disposition in {"timing_issue", "trust_deficit"} else "text"
    asset_brief = None
    if asset_type == "animation_brief":
        asset_brief = "30-45 second explainer that reframes the objection and invites a low-pressure next step."
    return FollowUpTask(
        id=_stable_id("followup", lead_id, call_id or "none", disposition, channel),
        lead_id=lead_id,
        call_id=call_id,
        type=ftype,
        channel=channel,  # type: ignore[arg-type]
        message=messages.get(disposition, "I drafted a concise personalized follow-up for approval."),
        asset_type=asset_type,  # type: ignore[arg-type]
        asset_brief=asset_brief,
        status="draft",
        requires_approval=True,
    )


def generate_daily_report(*, leads: Iterable[Lead], calls: Iterable[SalesCall], followups: Iterable[FollowUpTask]) -> dict[str, object]:
    leads = tuple(leads); calls = tuple(calls); followups = tuple(followups)
    return {
        "generated_at": now_ts(),
        "new_leads": len(leads),
        "qualified_leads": sum(1 for lead in leads if lead.qualification_status == "qualified"),
        "manual_review_leads": sum(1 for lead in leads if lead.qualification_status == "manual_review"),
        "calls_booked": sum(1 for lead in leads if lead.stage == "booked"),
        "calls_completed": sum(1 for call in calls if call.call_status == "completed"),
        "no_shows": sum(1 for call in calls if call.call_status == "no_show" or call.outcome == "no_show"),
        "closed_won": sum(1 for call in calls if call.outcome == "closed_won"),
        "closed_lost": sum(1 for call in calls if call.outcome == "closed_lost"),
        "cash_collected": sum(call.cash_collected or 0 for call in calls),
        "draft_followups": sum(1 for task in followups if task.status == "draft"),
        "priority_actions": ["Review manual-review leads", "Approve draft follow-ups", "Recover no-shows"],
    }
