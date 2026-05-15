from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, int_pk, str_not_null, str_null_true


class Workspace(Base):
    id: Mapped[int_pk]
    user_id: Mapped[int]  = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name:    Mapped[str]  = mapped_column(String(200), nullable=False)
    description: Mapped[str_null_true]

    # Workspace-level generation lock (managed by ChatDAO / lock.py)
    generating_chat_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
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