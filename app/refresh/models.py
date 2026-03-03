import hashlib
import hmac
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy import ForeignKey, DateTime, Integer, String
from app.database import Base, int_pk, str_not_null

load_dotenv()

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class RefreshSession(Base):
    id: Mapped[int_pk]
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        raw_token = str(raw_token.strip())
        if not raw_token:
            return ValueError("Refresh token empty")

        pepper = os.getenv("REFRESH_TOKEN_PEPPER")
        if pepper:
            return hmac.new(pepper.encode("utf-8"), raw_token.encode("utf-8"), hashlib.sha256).hexdigest()
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def set_token(self, raw_token: str) -> None:
        self.token_hash = self.hash_token(raw_token)

    def verify(self, raw_token: str) -> bool:
        expected_hash = self.hash_token(raw_token)
        return hmac.compare_digest(self.token_hash, expected_hash)

    def revoke(self) -> None:
        self.revoked_at = utcnow()

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= utcnow()

    # --- automatic hashing on assignment (decorator) ---
    @validates("token_hash")
    def _auto_hash_token_hash(self, key: str, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise ValueError("token_hash cannot be empty.")

        # if it already looks like a 64-char hex sha256 digest, assume it is hashed
        is_sha256_hex = len(v) == 64 and all(c in "0123456789abcdef" for c in v.lower())
        return v if is_sha256_hex else self._hash_token(v)

    # present objects as string data
    def __str__(self):
        return (
            f"Refresh(id={self.id}, "
            f"user={self.user_id}, "
            f"token_hash={self.token_hash}"
        )

    def __repr__(self):
        return str(self)
