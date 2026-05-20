from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.utils import get_current_user, require_admin
from app.utils.auth import hash_password
from app.users.dao import UserDAO
from app.users.models import User
from app.users.rb import RBUser
from app.users.schemas import SchemaUser, SchemaUserNameUpd, SchemaUserPasswordUpd

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("/", summary="List users — admin only")
async def get_users(
        request_body: RBUser = Depends(),
        _: User = Depends(require_admin),  # must be logged in
) -> list[SchemaUser]:
    rows = await UserDAO.find_all(**request_body.to_dict())
    return [SchemaUser.model_validate(r) for r in rows]


@router.get("/me", summary="Current user profile")
async def get_me(user: User = Depends(get_current_user)) -> SchemaUser:
    return SchemaUser.model_validate(user)


@router.get("/{user_id}", summary="Get user by id")
async def get_user_by_id(
        user_id: int,
        _: User = Depends(get_current_user),
) -> SchemaUser | dict:
    result = await UserDAO.find_one_or_none_by_id(user_id)
    if result is None:
        return {"message": f"No user with id={user_id}"}
    return SchemaUser.model_validate(result)


@router.put("/update_name/", summary="Update own display name")
async def update_name(
        data: SchemaUserNameUpd,
        current_user: User = Depends(get_current_user),
) -> dict:
    # Users can only update their own name
    if current_user.email != data.email:
        raise HTTPException(403, "Can only update your own profile")

    changed = await UserDAO.update({"email": data.email}, name=data.name)
    if changed:
        return {"message": "Username updated", "name": data.name}
    return {"message": "No changes made"}


@router.patch("/update_name/", summary="Update own display name")
async def update_name(
    data: SchemaUserNameUpd,
    current_user: User = Depends(get_current_user),
) -> dict:
    await UserDAO.update(
        {"id": current_user.id},
        name=data.name,
    )
    return {"message": "Name updated"}


@router.delete("/delete/{user_id}", summary="Delete user")
async def delete_user(
        user_id: int,
        current_user: User = Depends(require_admin),
) -> dict:
    # Users can only delete their own account
    if current_user.id != user_id:
        raise HTTPException(403, "Can only delete your own account")

    changed = await UserDAO.delete(id=user_id)
    if changed:
        return {"message": f"User {user_id} deleted"}
    return {"message": f"User {user_id} not found"}