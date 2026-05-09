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


def _title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()



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


class IngestDAO:
    """
    Single entry point for the pipeline to persist a completed chunk.
    Called from storage.save_chunk_result() after writing _completed marker.

    Example (in storage.py):
        import asyncio
        from app.ingest.dao.ingest_dao import IngestDAO
        asyncio.run(IngestDAO.save_chunk_result(result, manifest_entry, source_doc_id))
    """

    @classmethod
    async def save_chunk_result(
            cls,
            result,  # ChunkExtractionResult from ai_extractor
            manifest_entry: dict,  # matching row from chunk_manifest.json
            source_doc_id: int,  # SourceDocument.id already in DB
    ) -> dict[str, int]:
        """
        Persist all 4 extraction types + RAG chunk in a single transaction.
        Returns count of inserted records per type.
        """
        chunk_id = result.chunk_id
        source_slug = result.source_slug
        counts: dict[str, int] = {}

        # Scenarios
        scenario_rows = [
            dict(
                external_id=r.get("scenario_id", ""),
                title=_title_from_slug(r.get("scenario_id", "")),
                crisis_type=r.get("crisis_type", "operational"),
                severity=r.get("severity", "medium"),
                phase=r.get("phase", "acute"),
                context=r.get("context", ""),
                stakeholders=r.get("key_stakeholders", []),
                source_slug=source_slug,
                source_chunk_id=chunk_id,
                chapter_title=manifest_entry.get("chapter_title"),
                raw=r,
            )
            for r in result.scenarios
            if r.get("scenario_id")
        ]
        counts["scenarios"] = await ScenarioDAO.bulk_add_many(scenario_rows)

        #Decision nodes
        dn_rows = [
            dict(
                decision_id=r.get("decision_id", ""),
                source_scenario_id=r.get("source_scenario_id"),
                situation=r.get("situation"),
                options=r.get("options", []),
                recommended_action_id=r.get("recommended_action_id"),
                common_rookie_mistake=r.get("common_rookie_mistake"),
                consequence_if_wrong=r.get("consequence_if_wrong"),
                rationale=r.get("rationale"),
                source_slug=source_slug,
                source_chunk_id=chunk_id,
                raw=r,
            )
            for r in result.decision_nodes
            if r.get("decision_id")
        ]
        counts["decision_nodes"] = await DecisionNodeDAO.bulk_add_many(dn_rows)

        #Tactics
        tactic_rows = [
            dict(
                name=r.get("name", r.get("slug", "")),
                slug=r.get("slug", ""),
                description=r.get("description", ""),
                when_to_apply=r.get("when_to_apply"),
                example=r.get("example"),
                anti_pattern=r.get("anti_pattern"),
                crisis_types=r.get("crisis_types", []),
                source_slug=source_slug,
                source_chunk_id=chunk_id,
                raw=r,
            )
            for r in result.tactics
            if r.get("slug")
        ]
        counts["tactics"] = await TacticDAO.bulk_add_many(tactic_rows)

        #Q&A pairs
        qa_rows = [
            dict(
                question=r.get("question", ""),
                answer=r.get("answer", ""),
                difficulty=r.get("difficulty", "basic"),
                scenario_tags=r.get("scenario_tags", []),
                source_scenario_id=r.get("source_scenario_id", ""),
                common_mistake=r.get("common_mistake", ""),
                # external_id auto-generated in bulk_add_many
            )
            for r in result.qa_pairs
            if r.get("question")
        ]
        counts["qa_pairs"] = await QAPairDAO.bulk_add_many(qa_rows)

        # RAG chunk (from manifest, not AI output)
        if manifest_entry:
            rag_rows = [dict(
                chunk_id=chunk_id,
                source_document_id=source_doc_id,
                text=manifest_entry.get("text", ""),
                source_title=manifest_entry.get("source_slug", source_slug),
                source_chapter=manifest_entry.get("chapter_title", ""),
                chapter_index=manifest_entry.get("chapter_index", 0),
                chunk_index=manifest_entry.get("chunk_index", 0),
                token_count=manifest_entry.get("token_count", 0),
                page_start=manifest_entry.get("page_start", 0),
                page_end=manifest_entry.get("page_end", 0),
                language=manifest_entry.get("language", "mixed"),
                topics=[],
                scenario_relevance=[],
                embedding=None,
            )]
            counts["rag_chunks"] = await RagChunkDAO.bulk_add_many(rag_rows)

        log.info(
            "DB saved chunk [%s]: %s",
            chunk_id,
            " | ".join(f"{k}={v}" for k, v in counts.items() if v > 0),
        )
        return counts

    @classmethod
    async def finalize_book(cls) -> int:
        """
        Call once after all chunks of a book are processed.
        Converts new QAPairs → TrainingSamples.
        """
        n = await TrainingSampleDAO.build_from_new_qa_pairs()
        log.info("Built %d new TrainingSamples", n)
        return n

    @classmethod
    async def promote_all_books(cls, extracted_dir) -> dict:
        """
        Scan extracted_dir for all books with _completed chunks and push to DB.
        Called by: python -m app.run --promote-only
        """
        from pathlib import Path
        extracted_dir = Path(extracted_dir)
        total: dict[str, int] = {}

        if not extracted_dir.exists():
            log.warning("extracted_dir not found: %s", extracted_dir)
            return total

        for book_dir in sorted(extracted_dir.iterdir()):
            if not book_dir.is_dir():
                continue

            source_slug = book_dir.name
            chunks_dir = book_dir / "chunks"
            if not chunks_dir.exists():
                continue

            log.info("Promoting: %s", source_slug)

            # Load metadata for SourceDocument
            meta_path = book_dir / "metadata.json"
            if not meta_path.exists():
                log.warning("  Skipping %s — no metadata.json", source_slug)
                continue

            import json
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            doc = await SourceDocumentDAO.get_or_create(
                source_slug=source_slug,
                title=meta.get("title", source_slug),
                file_name=meta.get("file_name", ""),
                language=meta.get("language", "mixed"),
                doc_type=meta.get("doc_type", "manual"),
                total_chunks=meta.get("total_chunks", 0),
                meta=meta,
            )
            source_doc_id = doc.id

            # Load chunk manifest once per book
            manifest: dict[str, dict] = {}
            manifest_path = book_dir / "chunk_manifest.json"
            if manifest_path.exists():
                for entry in json.loads(manifest_path.read_text(encoding="utf-8")):
                    manifest[entry["chunk_id"]] = entry

            # Walk completed chunks
            for chunk_dir in sorted(chunks_dir.iterdir()):
                if not chunk_dir.is_dir():
                    continue
                if not (chunk_dir / "_completed").exists():
                    continue

                chunk_id = chunk_dir.name

                # Build a minimal result from saved JSON files
                def _load(fname):
                    f = chunk_dir / fname
                    if not f.exists():
                        return []
                    try:
                        return json.loads(f.read_text(encoding="utf-8"))
                    except Exception:
                        return []

                class _Result:
                    pass

                r = _Result()
                r.chunk_id = chunk_id
                r.source_slug = source_slug
                r.chapter_title = manifest.get(chunk_id, {}).get("chapter_title", "")
                r.chapter_index = manifest.get(chunk_id, {}).get("chapter_index", 0)
                r.chunk_index = manifest.get(chunk_id, {}).get("chunk_index", 0)
                r.language = manifest.get(chunk_id, {}).get("language", "mixed")
                r.doc_type = manifest.get(chunk_id, {}).get("doc_type", "manual")
                r.had_api_errors = False
                r.scenarios = _load("scenarios.json")
                r.decision_nodes = _load("decision_nodes.json")
                r.tactics = _load("tactics.json")
                r.qa_pairs = _load("qa_pairs.json")

                try:
                    counts = await cls.save_chunk_result(
                        r, manifest.get(chunk_id, {}), source_doc_id
                    )
                    for k, v in counts.items():
                        total[k] = total.get(k, 0) + v
                except Exception as e:
                    log.error("  DB error on %s: %s", chunk_id, e)

        # Build TrainingSamples from all new QAPairs
        n = await TrainingSampleDAO.build_from_new_qa_pairs()
        total["training_samples"] = total.get("training_samples", 0) + n
        log.info("promote_all_books done: %s", total)
        return total