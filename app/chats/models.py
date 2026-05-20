from __future__ import annotations
from sqlalchemy import ForeignKey, String, Integer, Enum
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, int_pk


class Chat(Base):

    id: Mapped[int_pk]
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey(
            "workspaces.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New Chat")
    status: Mapped[str] = mapped_column(
        Enum('empty', 'in_progress', 'generating', 'finished', name='chat_status_enum', create_type=False),
        nullable=False, default="empty",
    )
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __str__(self):
        return f"Chat(id={self.id}, workspace={self.workspace_id}, status={self.status!r})"

    def __repr__(self):
        return str(self)

    def to_dict(self):
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "status": self.status,
            "message_count": self.message_count,
        }

import secrets
from sqlalchemy import Boolean, ForeignKey, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, int_pk
from datetime import datetime

class ChatShareLink(Base):
    __tablename__ = "chat_share_links"

    id:         Mapped[int_pk]
    chat_id:    Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    token:      Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True,
        default=lambda: secrets.token_urlsafe(32)
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active:  Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        from datetime import timezone
        return self.expires_at <= datetime.now(timezone.utc)

    @property
    def is_valid(self) -> bool:
        return self.is_active and not self.is_expired