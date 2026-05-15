from datetime import datetime
from typing import Dict, Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey, Enum, DateTime, Integer
from app.database import Base, int_pk, str_not_null, str_null_true
from app.roadmaps.schema import PhaseEnum, ItemTypeEnum, PriorityEnum, StatusEnum, CreatedByEnum
from app.analysis.models import CaseAnalysis

class Roadmap(Base):
    id: Mapped[int_pk]
    analysis_id: Mapped[str] = mapped_column(ForeignKey("case_analysis.id"), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)

    crisis_type: Mapped[str_not_null]
    confidence: Mapped[str_not_null]
    roadmap_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)

    def __str__(self):
        return (f"Roadmap(id={self.id}, "
                f"crisis={self.crisis_type})"
                )