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