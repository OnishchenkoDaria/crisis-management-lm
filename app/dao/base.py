from sqlalchemy.future import select
from app.database import async_session_maker
from app.users.models import User


class BaseDAO:
    @classmethod
    async def find_all_students(cls):
        async with async_session_maker() as session:
            query = select(User)
            users = await session.execute(query)
            return users.scalars().all()
