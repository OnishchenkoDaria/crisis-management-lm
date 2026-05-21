from __future__ import annotations
from sqlalchemy import ForeignKey, String, Text, Enum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, int_pk


class Message(Base):
    id:      Mapped[int_pk]
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    role:    Mapped[str] = mapped_column(
        Enum('assistant', 'user', name='messages_role_enum', create_type=False),
        nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # User messages: stores the full SituationInput dict
    # Assistant messages: stores the full AnalysisResponse dict
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analysis_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self):
        return f"Message(id={self.id}, chat={self.chat_id}, role={self.role!r})"