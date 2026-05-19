from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.database import async_session_maker
from app.users.dao import UserDAO
from app.utils.auth import decode_access_token
from app.users.models import User

from fastapi import Request, HTTPException, Depends
from jose import jwt, JWTError

_bearer = HTTPBearer(auto_error=False)

from app.config import SECRET_KEY, ALGORITHM


async def get_current_user(request: Request) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(401, "Not authenticated")

    try:
        payload = decode_access_token(token)    # ← PyJWT, handles iss/aud/exp
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid token")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(401, "Invalid token")

    user = await UserDAO.find_one_or_none_by_filter(id=int(user_id))
    if not user:
        raise HTTPException(401, "User not found")
    return user

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return current_user

async def require_chat_owner(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "chat_owner"):
        raise HTTPException(403, "Chat owner access required")
    return current_user