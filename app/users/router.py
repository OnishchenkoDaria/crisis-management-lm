from fastapi import APIRouter
from sqlalchemy import select
from app.database import async_session_maker
from app.users.models import User

router = APIRouter(
    prefix="/users",
    tags=["Processing users' data"],
)

@router.get("/", summary="Get all users")
async def get_users():
    async with async_session_maker() as session:
        query = select(User)
        result = await session.execute(query)
        users = result.scalars().all()
        return users