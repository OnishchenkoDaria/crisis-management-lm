from app.database import Base, str_uniq, int_pk, str_not_null, str_null_true
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from typing import Any


class DecisionNode(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    decision_id: Mapped[str] = mapped_column(String(220), index=True, nullable=False)
    source_scenario_id: Mapped[str | None] = mapped_column(String(220), index=True)
    situation: Mapped[str_null_true]
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    recommended_action_id: Mapped[str | None] = mapped_column(String(80))
    common_rookie_mistake: Mapped[str_null_true]
    consequence_if_wrong: Mapped[str_null_true]
    rationale: Mapped[str_null_true]

    source_slug: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    source_chunk_id: Mapped[str] = mapped_column(String(240), index=True, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)