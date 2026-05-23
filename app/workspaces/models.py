from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, int_pk, str_not_null, str_null_true


class Workspace(Base):
    id: Mapped[int_pk]
    user_id: Mapped[int]  = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name:    Mapped[str]  = mapped_column(String(200), nullable=False)
    description: Mapped[str_null_true]

    # TOV fields — stored as JSONB arrays
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="ua")
    do_rules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    dont_rules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preferred_terms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    forbidden_phrases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    example_messages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # TOV sliders
    tov_formality: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    tov_empathy: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    tov_assertiveness: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    tov_transparency: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    # Generation lock
    generating_chat_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    generating_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


    def __str__(self):
        return f"Workspace(id={self.id}, user={self.user_id}, name={self.name!r})"

    def __repr__(self):
        return str(self)

    def to_dict(self):
        return {
            "id":          self.id,
            "user_id":     self.user_id,
            "name":        self.name,
            "description": self.description,
        }