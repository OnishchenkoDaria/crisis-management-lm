from fastapi import APIRouter
from sqlalchemy import select
from app.database import async_session_maker
from app.users.dao import UserDAO

router = APIRouter(
    prefix="/users",
    tags=["Processing users' data"],
)

@router.get("/", summary="Get all users")
async def get_users():
    return await UserDAO.find_all_users()