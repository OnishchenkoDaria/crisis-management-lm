from typing import Dict, Any

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, JSON
from app.database import Base, str_uniq, int_pk, str_not_null


class Scenario(Base):
    id: Mapped[int_pk]
    title: Mapped[str_not_null]
    crisis_type: Mapped[str_not_null]
    severity: Mapped[str_not_null]
    phase: Mapped[str_not_null]
    context: Mapped[str] = mapped_column(Text, nullable=False)
    stakeholders: Mapped[Dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=list, server_default="{}"
    )
    time_pressure: Mapped[str_not_null]
    initial_statement_required: mapped_column(bool)
    decision_nodes: Mapped[Dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=list, server_default="{}"
    )
    relevant_tactics: Mapped[Dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=list, server_default="{}"
    )
    source: Mapped[str]
    difficulty_for_rookie: Mapped[str]

