from app.analysis.models import Analysis
from app.dao.base import BaseDAO


class AnalysisDAO(BaseDAO):
    model = Analysis

    @classmethod
    async def find_one_or_none_by_id_str(cls, analysis_id: str):
        return await cls.find_one_or_none_by_filter(id=analysis_id)