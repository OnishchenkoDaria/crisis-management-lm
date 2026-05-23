import uuid

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Enum, Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base, int_pk, str_not_null
from typing import Any, Dict, Optional

# case_id (unique fk)
# crisis_type (enum)
# stage (enum)
# attribution (enum)
# evidence_confidence (enum)
# risk_score (int)
# factors_json (jsonb) (top contributing factors)
# retrieved_refs_json (jsonb) (ids knowledge cards/cases)

class CaseAnalysis(Base):
    __tablename__ = 'case_analysis'

    id: Mapped[int_pk]
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True)
    crisis_type: Mapped[str] = mapped_column(
        Enum(
            'reputational_crisis',
            'information_disinformation_crisis',
            'operational_failure_crisis',
            'values_ethics_crisis',
            'leadership_personal_crisis',
            'physical_or_cyber_security_crisis',
            name='communications_crisis_type_enum',
            create_type=False
        ), nullable=False
    )
    stage: Mapped[str] = mapped_column(
        Enum(
            'signal_detection',
            'trigger_event',
            'acute_crisis',
            'stabilization',
            'recovery',
            'post_crisis_learning',
            name='communications_crisis_stage_enum',
            create_type=False
        )
    )
    attribution: Mapped[str] = mapped_column(
        Enum(
            'external_attack',
            'external_unintentional',
            'internal_unintentional',
            'internal_negligence',
            'internal_misconduct',
            'systemic_failure',
            'mixed_attribution',
            'unknown',
            name='communications_crisis_attribution_enum',
            create_type=False
        )
    )
    evidence_confidence: Mapped[str] = mapped_column(
        Enum(
            'very_low',
            'low',
            'medium',
            'high',
            'very_high',
            'confirmed',
            name='communications_crisis_evidence_confidence_enum',
            create_type=False
        )
    )
    risk_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    factors_json: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    retrieved_refs_json: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"type={self.crisis_type!r},"
                f"crisis stage={self.stage!r}),"
                f"risk score={self.risk_score!r},")

    def __repr__(self):
        return str(self)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    situation_input: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    detected_type: Mapped[str_not_null]
    urgency: Mapped[str_not_null]
    confidence: Mapped[str_not_null]
    response_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    refinement_json: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    can_generate_roadmap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    def __str__(self):
        return (f"Analysis(id={self.id}, "
                f"type={self.detected_type}, "
                f"confidence={self.confidence})"
                )