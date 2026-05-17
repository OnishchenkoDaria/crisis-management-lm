from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.database import async_session_maker
from app.utils.auth import decode_access_token
from app.users.models import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    # Decodes the Bearer JWT and returns the authenticated User.
    #Raises HTTP 401 if token is missing, invalid, or expired.
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    async with async_session_maker() as session:
        user = (await session.execute(
            select(User).where(User.id == int(user_id))
        )).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return current_user


async def require_chat_owner(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "chat-owner"):
        raise HTTPException(403, "Chat owner access required")
    return current_user