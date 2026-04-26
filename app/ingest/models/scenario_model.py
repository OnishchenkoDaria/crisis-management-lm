from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, JSON, Boolean, Integer, String
from app.database import Base, str_uniq, int_pk, str_not_null


class Scenario(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
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
    initial_statement_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decision_nodes: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    relevant_tactics: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    source_slug: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    source_chunk_id: Mapped[str] = mapped_column(String(240), index=True, nullable=False)
    chapter_title: Mapped[str | None] = mapped_column(String(500))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    difficulty_for_rookie: Mapped[str_not_null]

    # present objects as string data
    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"external_id={self.external_id}, "
                f"title={self.title!r},"
                f"crisis_type={self.crisis_type!r})"
                f"severity={self.severity!r})")

    def __repr__(self):
        return str(self)

    # transform received data into dictionary
    def to_dict(self):
        return {
            "id": self.id,
            "external_id": self.external_id,
            "title": self.title,
            "crisis_type": self.crisis_type,
            "severity": self.severity,
        }