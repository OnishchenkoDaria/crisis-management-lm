from app.database import async_session_maker
from app.refresh.models import RefreshSession
from fastapi import Request
from sqlalchemy import select
import uuid
from datetime import datetime, timedelta, timezone

REFRESH_TOKEN_DAYS = 30

class RefreshSessionDAO:
    model = RefreshSession

    @staticmethod
    async def create(user_id: int, request: Request) -> tuple[str, RefreshSession]:
        #Create a new refresh session. Returns (raw_token, session_row)
        raw_token = str(uuid.uuid4())
        expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)

        session_row = RefreshSession(
            user_id=user_id,
            expires_at=expires,
            user_agent=request.headers.get("user-agent", "")[:256],
            ip_address=request.client.host if request.client else None,
        )
        session_row.set_token(raw_token)

        async with async_session_maker() as db:
            db.add(session_row)
            await db.commit()
            await db.refresh(session_row)

        return raw_token, session_row

    @staticmethod
    async def rotate(raw_token: str, request: Request) -> tuple[str, RefreshSession] | None:
        # Verify token, revoke old session, create new one (token rotation).
        token_hash = RefreshSession.hash_token(raw_token)

        async with async_session_maker() as db:
            old = (await db.execute(
                select(RefreshSession).where(RefreshSession.token_hash == token_hash)
            )).scalar_one_or_none()

            if not old or old.is_revoked or old.is_expired:
                return None

            old.revoke()
            await db.commit()
        # Returns (new_raw_token, new_session) or None if token is invalid/expired
        return await RefreshSessionDAO.create(old.user_id, request)

    @staticmethod
    async def revoke(raw_token: str) -> bool:
        # Revoke a specific refresh token (logout)
        token_hash = RefreshSession.hash_token(raw_token)
        async with async_session_maker() as db:
            session = (await db.execute(
                select(RefreshSession).where(RefreshSession.token_hash == token_hash)
            )).scalar_one_or_none()
            if not session:
                return False
            session.revoke()
            await db.commit()
        return True