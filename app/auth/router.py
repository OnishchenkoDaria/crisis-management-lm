from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.utils import get_current_user
from app.refresh.dao import RefreshSessionDAO
from app.utils.auth import create_access_token, hash_password, verify_password
from app.users.dao import UserDAO
from app.users.models import User
from app.users.schemas import SchemaUser, SchemaUserAdd
from app.auth.schemas import SchemaLogin, SchemaRefreshRequest, SchemaTokenPair

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", response_model=SchemaUser, status_code=status.HTTP_201_CREATED)
async def register(data: SchemaUserAdd) -> SchemaUser:
    existing = await UserDAO.find_one_or_none_by_filter(email=data.email)
    if existing:
        raise HTTPException(400, "Email already registered")

    user = await UserDAO.add(
        name = data.name,
        email = data.email,
        hashed_password = hash_password(data.password),
    )
    return SchemaUser.model_validate(user)


@router.post("/login", response_model=SchemaTokenPair)
async def login(data: SchemaLogin, request: Request) -> SchemaTokenPair:
    user = await UserDAO.find_one_or_none_by_filter(email=data.email)
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")

    access_token           = create_access_token({"sub": str(user.id)})
    raw_refresh, _session  = await RefreshSessionDAO.create(user.id, request)

    return SchemaTokenPair(
        access_token  = access_token,
        refresh_token = raw_refresh,
    )


@router.post("/refresh", response_model=SchemaTokenPair)
async def refresh(data: SchemaRefreshRequest, request: Request) -> SchemaTokenPair:
    result = await RefreshSessionDAO.rotate(data.refresh_token, request)
    if not result:
        raise HTTPException(401, "Refresh token invalid or expired")

    raw_refresh, session = result
    access_token = create_access_token({"sub": str(session.user_id)})

    return SchemaTokenPair(
        access_token  = access_token,
        refresh_token = raw_refresh,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: SchemaRefreshRequest) -> None:
    await RefreshSessionDAO.revoke(data.refresh_token)


@router.get("/me", response_model=SchemaUser)
async def me(user: User = Depends(get_current_user)) -> SchemaUser:
    return SchemaUser.model_validate(user)