from sqlalchemy import select

from app.dao.base import BaseDAO
from app.database import async_session_maker
from app.roadmaps.models import Roadmap


class RoadmapDAO(BaseDAO):
    model = Roadmap

    @classmethod
    async def find_one_or_none_by_id_str(cls, roadmap_id: str):
        return await cls.find_one_or_none_by_filter(id=roadmap_id)

    @classmethod
    async def find_latest_by_analysis_id(cls, analysis_id: str):
        async with async_session_maker() as session:
            result = await session.execute(
                select(Roadmap)
                .where(Roadmap.analysis_id == analysis_id)
                .order_by(Roadmap.id.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()