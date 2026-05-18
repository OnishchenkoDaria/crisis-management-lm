from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi import APIRouter, Request, Response, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.auth.utils import get_current_user
from app.refresh.dao import RefreshSessionDAO
from app.utils.auth import create_access_token, hash_password, verify_password
from app.users.dao import UserDAO
from app.users.models import User
from app.users.schemas import SchemaUser, SchemaUserAdd
from app.auth.schemas import SchemaLogin, SchemaRefreshRequest, SchemaTokenPair

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", response_model=SchemaUser, status_code=status.HTTP_201_CREATED)
async def register(data: SchemaUserAdd, request: Request, response: Response) -> SchemaUser:
    existing = await UserDAO.find_one_or_none_by_filter(email=data.email)
    if existing:
        raise HTTPException(400, "Email already registered")

    user = await UserDAO.add(
        name=data.name,
        email=data.email,
        hashed_password=hash_password(data.password),
        role="chat_owner",
    )

    access_token = create_access_token({"sub": str(user.id)})
    raw_refresh, _session = await RefreshSessionDAO.create(user.id, request)

    response.set_cookie("access_token",  access_token, httponly=True,
                        secure=True, samesite="lax", max_age=60*15)
    response.set_cookie("refresh_token", raw_refresh,  httponly=True,
                        secure=True, samesite="lax", max_age=60*60*24*30,
                        path="/api/auth/refresh")

    return SchemaUser.model_validate(user)


@router.post("/login")
async def login(data: SchemaLogin, request: Request, response: Response):
    user = await UserDAO.find_one_or_none_by_filter(email=data.email)
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")

    access_token = create_access_token({"sub": str(user.id)})
    raw_refresh, _session = await RefreshSessionDAO.create(user.id, request)

    response.set_cookie("access_token", access_token, httponly=True,
                        secure=True, samesite="lax", max_age=60*15)
    response.set_cookie("refresh_token", raw_refresh,  httponly=True,
                        secure=True, samesite="lax", max_age=60*60*24*30,
                        path="/api/auth/refresh")
    return {"ok": True}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    raw_refresh = request.cookies.get("refresh_token")
    if not raw_refresh:
        raise HTTPException(401, "No refresh token")

    result = await RefreshSessionDAO.rotate(raw_refresh, request)
    if not result:
        raise HTTPException(401, "Refresh token invalid or expired")

    new_raw_refresh, session = result
    access_token = create_access_token({"sub": str(session.user_id)})

    response.set_cookie("access_token", access_token, httponly=True,
                        secure=True, samesite="lax", max_age=60*15)
    response.set_cookie("refresh_token", new_raw_refresh,  httponly=True,
                        secure=True, samesite="lax", max_age=60*60*24*30,
                        path="/api/auth/refresh")
    return {"ok": True}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response):
    raw_refresh = request.cookies.get("refresh_token")
    if raw_refresh:
        await RefreshSessionDAO.revoke(raw_refresh)

    response.delete_cookie("access_token",  path="/")
    response.delete_cookie("refresh_token", path="/api/auth/refresh")


@router.get("/me", response_model=SchemaUser)
async def me(user: User = Depends(get_current_user)) -> SchemaUser:
    return SchemaUser.model_validate(user)