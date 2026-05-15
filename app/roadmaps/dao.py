from app.dao.base import BaseDAO
from app.roadmaps.models import Roadmap


class RoadmapDAO(BaseDAO):
    model = Roadmap

    @classmethod
    async def find_one_or_none_by_id_str(cls, roadmap_id: str):
        return await cls.find_one_or_none_by_filter(id=roadmap_id)