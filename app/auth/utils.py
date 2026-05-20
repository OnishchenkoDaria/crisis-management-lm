from __future__ import annotations

from typing import Literal

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.chats.dao import ShareLinkDAO, ChatDAO
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
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid token")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(401, "Invalid token")

    user = await UserDAO.find_one_or_none_by_filter(id=int(user_id))
    if not user:
        raise HTTPException(401, "User not found")
    return user

async def get_optional_user(request: Request) -> User | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        return await UserDAO.find_one_or_none_by_filter(id=int(user_id))
    except (jwt.InvalidTokenError, ValueError):
        return None

async def get_chat_permission(
    chat_id: int,
    current_user: User | None,
    token: str | None = None,
) -> Literal["owner", "reader", "none"]:

    chat = await ChatDAO.find_one_or_none_by_filter(id=chat_id)
    if not chat:
        return "none"

    if current_user and chat.user_id == current_user.id:
        return "owner"

    if token:
        link = await ShareLinkDAO.find_valid(chat_id=chat_id, token=token)
        if link:
            return "reader"

    return "none"

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return current_user

async def require_chat_owner(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "chat_owner"):
        raise HTTPException(403, "Chat owner access required")
    return current_user