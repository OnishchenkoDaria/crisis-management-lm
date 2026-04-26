from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, JSON, Boolean
from app.database import Base, str_uniq, int_pk, str_not_null


class Scenario(Base):
    external_id: Mapped[str_uniq]  # "chemical-spill-media-panic-001"

    title: Mapped[str_not_null]
    crisis_type: Mapped[str_not_null]
    severity: Mapped[str_not_null]
    phase: Mapped[str_not_null]
    context: Mapped[str] = mapped_column(Text, nullable=False)
    stakeholders: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    time_pressure: Mapped[str_not_null]
    initial_statement_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    decision_nodes: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    relevant_tactics: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    source: Mapped[str_not_null]
    difficulty_for_rookie: Mapped[str_not_null]

