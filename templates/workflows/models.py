from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal

Timestamp = str
LeadSource = Literal["email", "dm", "sms", "call", "manual", "ad", "referral", "unknown"]
QualificationStatus = Literal["qualified", "unqualified", "needs_more_info", "manual_review"]
LeadStage = Literal["new", "engaged", "qualified", "booked", "showed", "closed_won", "closed_lost", "no_show", "nurture"]
Urgency = Literal["low", "medium", "high", "unknown"]
CallStatus = Literal["scheduled", "completed", "no_show", "cancelled", "rescheduled"]
CallOutcome = Literal["closed_won", "closed_lost", "follow_up", "no_show", "dq", "unknown"]
Disposition = Literal[
    "financially_unqualified",
    "uncertain_about_offer",
    "too_many_unanswered_questions",
    "spousal_objection",
    "macro_event_blame",
    "timing_issue",
    "trust_deficit",
    "no_show",
    "closed_won",
    "other",
]
FollowupType = Literal["pre_call", "post_call", "no_show", "rebook", "nurture", "manual_review"]
FollowupChannel = Literal["email", "sms", "dm", "call", "loom", "telegram", "slack", "manual"]
FollowupStatus = Literal["draft", "approved", "sent", "failed", "cancelled"]


def now_ts() -> Timestamp:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")



@dataclass(frozen=True)
class FormIntake:
    id: str
    source: LeadSource = "ad"
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    role: str | None = None
    revenue: float | None = None
    budget: float | None = None
    offer_interest: str | None = None
    pain_points: tuple[str, ...] = ()
    urgency: Urgency = "unknown"
    business_context: str | None = None
    referral_context: str | None = None
    event_context: str | None = None
    raw_answers: dict[str, str] = field(default_factory=dict)
    consent_to_text: bool = False
    created_at: Timestamp = field(default_factory=now_ts)

    def to_lead(self) -> "Lead":
        return Lead(
            id=self.id,
            source=self.source,
            name=self.name,
            email=self.email,
            phone=self.phone,
            company=self.company,
            role=self.role,
            revenue=self.revenue,
            budget=self.budget,
            offer_interest=self.offer_interest,
            pain_points=self.pain_points,
            urgency=self.urgency,
            consent_to_text=self.consent_to_text,
            form_context={
                "business_context": self.business_context or "",
                "referral_context": self.referral_context or "",
                "event_context": self.event_context or "",
                "raw_answers": self.raw_answers,
            },
        )

@dataclass(frozen=True)
class Lead:
    id: str
    source: LeadSource = "unknown"
    channel_id: str | None = None
    contact_id: str | None = None
    crm_contact_id: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    role: str | None = None
    revenue: float | None = None
    budget: float | None = None
    offer_interest: str | None = None
    pain_points: tuple[str, ...] = ()
    urgency: Urgency = "unknown"
    qualification_status: QualificationStatus = "needs_more_info"
    lead_score: float = 0
    stage: LeadStage = "new"
    owner_agent: str = "sales_flo"
    public_persona_name: str = "Flo"
    consent_to_text: bool = False
    form_context: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    last_touch_at: Timestamp | None = None
    next_action_at: Timestamp | None = None
    created_at: Timestamp = field(default_factory=now_ts)
    updated_at: Timestamp = field(default_factory=now_ts)

    def with_updates(self, **kwargs: Any) -> "Lead":
        return replace(self, updated_at=now_ts(), **kwargs)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["pain_points"] = list(self.pain_points)
        data["tags"] = list(self.tags)
        data["notes"] = list(self.notes)
        return data


@dataclass(frozen=True)
class SalesCall:
    id: str
    lead_id: str
    calendar_event_id: str | None = None
    recording_url: str | None = None
    transcript_url: str | None = None
    transcript_text: str | None = None
    closer_name: str | None = None
    call_started_at: Timestamp | None = None
    call_ended_at: Timestamp | None = None
    duration_minutes: float | None = None
    call_status: CallStatus = "scheduled"
    outcome: CallOutcome = "unknown"
    deal_value: float | None = None
    cash_collected: float | None = None
    payment_plan: bool | None = None
    created_at: Timestamp = field(default_factory=now_ts)
    updated_at: Timestamp = field(default_factory=now_ts)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CallIntelligence:
    id: str
    call_id: str
    lead_id: str
    lead_quality_score: float
    closer_score: float
    call_score: float
    buying_signals: tuple[str, ...]
    objections: tuple[str, ...]
    disposition: Disposition
    summary: str
    what_happened: str
    why_not_closed: str | None
    recommended_next_action: str
    followup_angle: str
    content_needed: tuple[str, ...]
    ava_escalation_required: bool
    ava_escalation_reason: str | None
    created_at: Timestamp = field(default_factory=now_ts)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["buying_signals"] = list(self.buying_signals)
        data["objections"] = list(self.objections)
        data["content_needed"] = list(self.content_needed)
        return data


@dataclass(frozen=True)
class FollowUpTask:
    id: str
    lead_id: str
    call_id: str | None = None
    type: FollowupType = "manual_review"
    channel: FollowupChannel = "manual"
    message: str = ""
    asset_type: Literal["text", "voice", "loom_prompt", "animation_brief", "video_script", "none"] = "text"
    asset_brief: str | None = None
    status: FollowupStatus = "draft"
    requires_approval: bool = True
    scheduled_for: Timestamp | None = None
    sent_at: Timestamp | None = None
    created_at: Timestamp = field(default_factory=now_ts)
    updated_at: Timestamp = field(default_factory=now_ts)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
