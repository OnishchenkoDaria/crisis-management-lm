from fastapi import APIRouter
from app.users.dao import UserDAO

router = APIRouter(
    prefix="/users",
    tags=["Processing users' data"],
)

@router.get("/", summary="Get all users")
async def get_users():
    return await UserDAO.find_all()