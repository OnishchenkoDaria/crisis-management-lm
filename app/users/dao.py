from sqlalchemy import select
from app.users.models import User
from app.database import async_session_maker


class UserDAO:
    @classmethod
    async def find_all_users(cls):
        async with async_session_maker() as session:
            query = select(User)
            users = await session.execute(query)
            return users.scalars().all()