from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey, DateTime, Integer, String
from app.database import Base, int_pk, str_not_null

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class RefreshSession(Base):
    id: Mapped[int_pk]
    user: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
