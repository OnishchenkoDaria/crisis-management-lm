from __future__ import annotations

import logging

from sqlalchemy import select, func

from app.database import async_session_maker
from app.dao.base import BaseDAO
from app.ingest.models.decision_node_model import DecisionNode
from app.ingest.models.qa_model import QAPair
from app.ingest.models.rag_chunk_model import RagChunk
from app.ingest.models.scenario_model import Scenario
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.ingest.models.source_doc_model import SourceDocument
from app.ingest.models.tactics import Tactic
from app.ingest.models.training_sample_model import TrainingSample

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a Decision Support System for crisis communications. "
    "You are advising a rookie Communications Specialist who is under pressure. "
    "Be direct, tactical, and specific. Warn about the most common rookie mistake."
)

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


class RagChunkDAO(BaseDAO):
    model = RagChunk

    @classmethod
    async def bulk_add_many(cls, records: list[dict]) -> int:
        if not records:
            return 0
        async with async_session_maker() as session:
            stmt = (
                pg_insert(RagChunk)
                .values(records)
                .on_conflict_do_nothing(index_elements=["chunk_id"])
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    @classmethod
    async def find_by_source_slug(cls, source_slug: str) -> list[RagChunk]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(RagChunk)
                .join(SourceDocument)
                .filter(SourceDocument.source_slug == source_slug)
            )
            return result.scalars().all()

    @classmethod
    async def find_unembedded(cls, limit: int = 100) -> list[RagChunk]:
        """Return chunks not yet embedded — for the embedding step."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(RagChunk)
                .where(RagChunk.embedding.is_(None))
                .limit(limit)
            )
            return result.scalars().all()

    @classmethod
    async def update_embedding(cls, chunk_id: str, vector: list[float]) -> None:
        """Store the embedding vector for one chunk."""
        async with async_session_maker() as session:
            await session.execute(
                RagChunk.__table__.update()
                .where(RagChunk.chunk_id == chunk_id)
                .values(embedding=vector)
            )
            await session.commit()

    @classmethod
    async def find_similar(cls, query_vector: list[float], limit: int = 5,
                           language: str | None = None) -> list[RagChunk]:
        """
        Vector similarity search using pgvector cosine distance.
        Requires pgvector extension and Vector column type.

        Usage:
            from openai import AsyncOpenAI
            client = AsyncOpenAI()
            resp = await client.embeddings.create(input=query, model="text-embedding-3-small")
            vector = resp.data[0].embedding
            chunks = await RagChunkDAO.find_similar(vector, limit=5)
        """
        async with async_session_maker() as session:
            # pgvector cosine distance operator: <=>
            # Lower = more similar
            distance_expr = RagChunk.embedding.op("<=>")(query_vector)

            q = (
                select(RagChunk)
                .where(RagChunk.embedding.isnot(None))
                .order_by(distance_expr)
                .limit(limit)
            )
            if language:
                q = q.where(RagChunk.language == language)

            result = await session.execute(q)
            return result.scalars().all()


class TrainingSampleDAO(BaseDAO):
    model = TrainingSample

    @classmethod
    async def build_from_new_qa_pairs(cls) -> int:
        """
        Convert all QAPairs that don't have a TrainingSample yet.
        Called once after bulk import is complete.
        """
        new_pairs = await QAPairDAO.find_without_training_sample()
        if not new_pairs:
            return 0

        async with async_session_maker() as session:
            samples = [
                TrainingSample(
                    source_qa_id=qa.id,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": qa.question},
                        {"role": "assistant", "content": qa.answer},
                    ],
                    format="messages",
                )
                for qa in new_pairs
            ]
            session.add_all(samples)
            await session.commit()
            return len(samples)