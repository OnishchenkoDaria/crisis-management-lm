from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, field_validator

class CrisisType(str, Enum):
    media          = "media"
    reputational   = "reputational"
    operational    = "operational"
    safety         = "safety"
    political      = "political"
    internal       = "internal"
    natural        = "natural_disaster"

class UrgencyLevel(str, Enum):
    critical = "critical"  # response needed < 30 min
    high  = "high"  # response needed < 2 hours
    medium = "medium"   # response needed < 24 hours
    low = "low"   # monitoring only

class CrisisPhase(str, Enum):
    pre_crisis  = "pre_crisis"
    acute = "acute"
    containment = "containment"
    recovery  = "recovery"
    post_crisis = "post_crisis"

class ActionPriority(str, Enum):
    immediate = "immediate"
    high = "high"
    medium = "medium"
    low = "low"

class ActionStatus(str, Enum):
    pending     = "pending"
    in_progress = "in_progress"
    done        = "done"
    skipped     = "skipped"


#Structured form the user fills in Step 1.

class SituationInput(BaseModel):
    # Core (required)
    situation_description: str = Field(
        ..., min_length=20, max_length=3000,
        description="What happened? Describe the crisis situation.",
        example="A former employee posted claims of workplace harassment on social media. "
                "The post has 2000 shares in 3 hours and journalists are calling."
    )

    # Classification (optional — auto-detected from description if omitted)
    crisis_type: CrisisType   | None = None
    urgency_level: UrgencyLevel | None = None
    phase: CrisisPhase  | None = None

    # Context (optional — enriches analysis)
    affected_stakeholders:  list[str] = Field(
        default_factory=list,
        example=["employees", "media", "investors", "customers"]
    )
    communication_channels: list[str] = Field(
        default_factory=list,
        example=["social_media", "press_release", "internal_email"]
    )
    current_public_reaction: str | None = Field(
        None,
        max_length=500
    )
    already_published: str | None = Field(
        None,
        max_length=1000,
        description="Any statements already published by the organisation."
    )
    internal_constraints: str | None = Field(
        None,
        max_length=500,
        description="Legal holds, ongoing investigations, NDA constraints, etc."
    )
    desired_tone: str | None = Field(
        None,
        max_length=200,
        example="empathetic but firm"
    )
    legal_risks: list[str] = Field(default_factory=list)

    @field_validator("situation_description")
    @classmethod
    def no_prompt_injection(cls, v: str) -> str:
        """Basic prompt-injection guard — block common LLM override patterns."""
        blocked = [
            "ignore previous instructions",
            "disregard your system prompt",
            "you are now",
            "act as",
            "forget everything",
        ]
        lower = v.lower()
        for phrase in blocked:
            if phrase in lower:
                raise ValueError(
                    "Input contains disallowed patterns. "
                    "Please describe your crisis situation factually."
                )
        return v


class SourceRef(BaseModel):
    title: str
    chapter: str
    similarity: float

class TacticRef(BaseModel):
    name: str
    description: str
    anti_pattern: str | None = None

class AnalysisResponse(BaseModel):
    analysis_id: str
    workspace_id: int
    status: Literal["draft", "refined", "ready"]

    # Classification
    crisis_summary: str
    detected_crisis_type: CrisisType
    urgency_level:  UrgencyLevel
    phase:  CrisisPhase
    confidence: Literal["high", "medium", "low"]

    # Content
    key_risks: list[str]
    stakeholders: list[str]
    recommended_strategy: str
    relevant_tactics: list[TacticRef]
    suggested_initial_message: str
    missing_information: list[str]   # what the system couldn't determine
    next_questions:  list[str]   # clarifying questions for the user

    # Sources
    retrieved_sources: list[SourceRef]

    # Control flag
    can_generate_roadmap: bool   # True when confidence >= medium and no critical missing info


class RefinementRequest(BaseModel):
    user_comment: str | None = Field(
        None,
        max_length=2000,
        description="Free-text comment, correction, or additional context."
    )
    fields_to_update:   dict[str, str] = Field(
        default_factory=dict,
        description="Specific field overrides, e.g. {'crisis_type': 'operational'}"
    )
    additional_context: str | None = Field(
        None,
        max_length=1000
    )
    changed_constraints: list[str] = Field(default_factory=list)

    @field_validator("user_comment")
    @classmethod
    def sanitize_comment(cls, v: str | None) -> str | None:
        if v is None:
            return v
        blocked = ["ignore previous", "disregard", "forget everything", "act as"]
        lower = v.lower()
        for phrase in blocked:
            if phrase in lower:
                raise ValueError("Comment contains disallowed patterns.")
        return v


class ActionItem(BaseModel):
    id: str
    phase: str   # "T0–30min" | "30min–2h" | "2h–24h" | "1–7days" | "monitoring"
    title: str
    description: str
    priority: ActionPriority
    owner_role: str          # "Communications Lead" | "Legal" | "CEO" | "HR" etc.
    channel: str | None   # "press_release" | "social_media" | "internal_email" etc.
    status: ActionStatus = ActionStatus.pending
    due_hint: str  # "Within 30 minutes of incident" (human-readable)
    rationale: str
    risk_if_skipped: str
    source_refs: list[str]    # chunk_ids or document titles


class RoadmapPhase(BaseModel):
    id: str   # "t0_30min"
    label: str    # "T0 – 30 minutes"
    description: str   # What this phase focuses on
    action_items: list[ActionItem]


class MonitoringItem(BaseModel):
    metric: str  # "Social media sentiment"
    frequency: str   # "Every 15 minutes for first 2 hours"
    owner: str
    threshold: str   # "If negative mentions > 500, escalate"


class EscalationRule(BaseModel):
    trigger: str
    action: str
    owner_role: str


class RoadmapResponse(BaseModel):
    roadmap_id:  str
    analysis_id: str
    workspace_id: int
    crisis_type: CrisisType

    executive_summary:    str
    phases:               list[RoadmapPhase]
    communication_messages: list[dict]   # {channel, message, timing, tone}
    monitoring_plan:      list[MonitoringItem]
    escalation_rules:     list[EscalationRule]
    risks:                list[str]
    sources:              list[SourceRef]
    confidence:           Literal["high", "medium", "low"]
    next_steps:           list[str]


class ActionItemUpdate(BaseModel):
    status:  ActionStatus
    note:    str | None = Field(None, max_length=500)