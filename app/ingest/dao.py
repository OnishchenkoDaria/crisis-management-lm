from __future__ import annotations

import logging

from sqlalchemy import select, func

from app.database import async_session_maker
from app.dao.base import BaseDAO
from app.ingest.models.decision_node_model import DecisionNode
from app.ingest.models.qa_model import QAPair
from app.ingest.models.scenario_model import Scenario
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.ingest.models.source_doc_model import SourceDocument
from app.ingest.models.tactics import Tactic
from app.ingest.models.training_sample_model import TrainingSample

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


class DecisionNodeDAO(BaseDAO):
    model = DecisionNode

    @classmethod
    async def bulk_add_many(cls, records: list[dict]) -> int:
        if not records:
            return 0
        async with async_session_maker() as session:
            stmt = (
                pg_insert(DecisionNode)
                .values(records)
                # decision_id is not globally unique (same rule can appear in multiple chunks)
                # deduplicate by (decision_id, source_chunk_id)
                .on_conflict_do_nothing()
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    @classmethod
    async def find_by_scenario_id(cls, source_scenario_id: str) -> list[DecisionNode]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(DecisionNode).filter_by(source_scenario_id=source_scenario_id)
            )
            return result.scalars().all()


class TacticDAO(BaseDAO):
    model = Tactic

    @classmethod
    async def bulk_add_many(cls, records: list[dict]) -> int:
        if not records:
            return 0
        async with async_session_maker() as session:
            stmt = (
                pg_insert(Tactic)
                .values(records)
                .on_conflict_do_nothing()
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    @classmethod
    async def find_by_crisis_type(cls, crisis_type: str) -> list[Tactic]:
        """Find tactics applicable to a specific crisis type (JSONB array contains)."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Tactic).where(
                    Tactic.crisis_types.contains([crisis_type])
                )
            )
            return result.scalars().all()

    @classmethod
    async def find_by_slug(cls, slug: str) -> Tactic | None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Tactic).filter_by(slug=slug)
            )
            return result.scalar_one_or_none()


class QAPairDAO(BaseDAO):
    model = QAPair

    @classmethod
    async def next_external_id(cls) -> str:
        """Generate next sequential external_id like 'qa-000042'."""
        async with async_session_maker() as session:
            result = await session.execute(select(func.count()).select_from(QAPair))
            count = result.scalar_one() or 0
            return f"qa-{count + 1:06d}"

    @classmethod
    async def bulk_add_many(cls, records: list[dict]) -> int:
        """Insert Q&A pairs, auto-generating external_ids."""
        if not records:
            return 0
        async with async_session_maker() as session:
            # Get current count once for id generation
            result = await session.execute(select(func.count()).select_from(QAPair))
            counter = (result.scalar_one() or 0) + 1

            inserted = 0
            for rec in records:
                if not rec.get("external_id"):
                    rec = {**rec, "external_id": f"qa-{counter:06d}"}
                    counter += 1
                session.add(QAPair(**rec))
                inserted += 1

            await session.commit()
            return inserted

    @classmethod
    async def find_by_difficulty(cls, difficulty: str) -> list[QAPair]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(QAPair).filter_by(difficulty=difficulty)
            )
            return result.scalars().all()

    @classmethod
    async def find_by_scenario_id(cls, source_scenario_id: str) -> list[QAPair]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(QAPair).filter_by(source_scenario_id=source_scenario_id)
            )
            return result.scalars().all()

    @classmethod
    async def find_without_training_sample(cls) -> list[QAPair]:
        """Return QAPairs not yet converted to TrainingSamples."""
        async with async_session_maker() as session:
            used_ids = select(TrainingSample.source_qa_id).where(
                TrainingSample.source_qa_id.isnot(None)
            )
            result = await session.execute(
                select(QAPair).where(~QAPair.id.in_(used_ids))
            )
            return result.scalars().all()