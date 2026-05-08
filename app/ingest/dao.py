from __future__ import annotations

import logging

from sqlalchemy import select

from app.database import async_session_maker
from app.dao.base import BaseDAO
from app.ingest.models.scenario_model import Scenario
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.ingest.models.source_doc_model import SourceDocument

log = logging.getLogger(__name__)

class SourceDocumentDAO(BaseDAO):
    model = SourceDocument

    @classmethod
    async def get_or_create(cls, *, source_slug: str, title: str,
                            file_name: str, language: str = "mixed",
                            doc_type: str = "manual", total_chunks: int = 0,
                            meta: dict | None = None) -> SourceDocument:
        """Return existing SourceDocument or create a new one."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(SourceDocument).filter_by(source_slug=source_slug)
            )
            doc = result.scalar_one_or_none()
            if doc:
                return doc

            doc = SourceDocument(
                source_slug=source_slug,
                title=title,
                file_name=file_name,
                language=language,
                doc_type=doc_type,
                total_chunks=total_chunks,
                meta=meta or {},
            )
            session.add(doc)
            await session.commit()
            await session.refresh(doc)
            log.info("Created SourceDocument: %s (id=%d)", source_slug, doc.id)
            return doc


class ScenarioDAO(BaseDAO):
    model = Scenario

    @classmethod
    async def bulk_add_many(cls, records: list[dict]) -> int:
        """
        Insert many scenarios, skipping duplicates (by external_id).
        Returns count of actually inserted rows.
        """
        if not records:
            return 0
        async with async_session_maker() as session:
            stmt = (
                pg_insert(Scenario)
                .values(records)
                .on_conflict_do_nothing(index_elements=["external_id"])
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    @classmethod
    async def find_by_source_slug(cls, source_slug: str) -> list[Scenario]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Scenario).filter_by(source_slug=source_slug)
            )
            return result.scalars().all()

    @classmethod
    async def find_by_crisis_type(cls, crisis_type: str) -> list[Scenario]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Scenario).filter_by(crisis_type=crisis_type)
            )
            return result.scalars().all()