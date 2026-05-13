"""
app/dao/rag_chunk_dao.py
=========================
RagChunkDAO — async DAO with pgvector similarity search.
Extends BaseDAO with domain-specific query methods.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.base import BaseDAO
from app.ingest.models.rag_chunk_model import RagChunk
from app.ingest.models.source_doc_model import SourceDocument
from app.database import async_session_maker


@dataclass
class SimilarChunk:
    """Return type for find_similar — chunk data + similarity score."""
    chunk_id:      str
    text:          str
    source_title:  str
    source_chapter: str
    source_slug:   str
    language:      str
    token_count:   int
    page_start:    int
    page_end:      int
    distance:      float       # cosine distance (0=identical, 1=orthogonal, 2=opposite)

    @property
    def similarity(self) -> float:
        """Cosine similarity (1 - distance). Higher = more similar."""
        return round(1.0 - self.distance, 4)


class RagChunkDAO(BaseDAO):
    model = RagChunk

    # ── Core similarity search ─────────────────────────────────────────────

    @classmethod
    async def find_similar(
        cls,
        query_vector: list[float],
        *,
        limit: int = 5,
        language: str | None = None,
        source_slug: str | None = None,
        source_document_id: int | None = None,
        min_token_count: int = 50,       # skip tiny reference-list chunks
        max_distance: float = 0.8,       # filter out very dissimilar results
    ) -> list[SimilarChunk]:
        """
        Returns chunks sorted by semantic similarity to the query vector.
        PITFALL: If embedding column is NULL for many rows, this is slow.
        """
        async with async_session_maker() as session:
            # Build WHERE clauses
            filters: list[str] = [
                "rc.embedding IS NOT NULL",
                f"rc.token_count >= {min_token_count}",
                f"(rc.embedding <=> :qv) <= {max_distance}",
            ]
            if language:
                filters.append("rc.language = :language")
            if source_slug:
                filters.append("sd.source_slug = :source_slug")
            if source_document_id:
                filters.append("rc.source_document_id = :source_document_id")

            where = " AND ".join(filters)

            sql = text(f"""
                SELECT
                    rc.chunk_id,
                    rc.text,
                    rc.source_title,
                    rc.source_chapter,
                    rc.language,
                    rc.token_count,
                    rc.page_start,
                    rc.page_end,
                    sd.source_slug,
                    (rc.embedding <=> :qv) AS distance
                FROM ragchunks rc
                JOIN sourcedocuments sd ON sd.id = rc.source_document_id
                WHERE {where}
                ORDER BY rc.embedding <=> :qv
                LIMIT :limit
            """)

            params: dict[str, Any] = {
                "qv":    str(query_vector),
                "limit": limit,
            }
            if language:
                params["language"] = language
            if source_slug:
                params["source_slug"] = source_slug
            if source_document_id:
                params["source_document_id"] = source_document_id

            rows = (await session.execute(sql, params)).fetchall()

        return [
            SimilarChunk(
                chunk_id      = r.chunk_id,
                text          = r.text,
                source_title  = r.source_title,
                source_chapter= r.source_chapter,
                source_slug   = r.source_slug,
                language      = r.language,
                token_count   = r.token_count,
                page_start    = r.page_start,
                page_end      = r.page_end,
                distance      = float(r.distance),
            )
            for r in rows
        ]


    @classmethod
    async def find_unembedded(cls, limit: int = 100) -> list[RagChunk]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(RagChunk)
                .where(RagChunk.embedding.is_(None))
                .limit(limit)
            )
            return result.scalars().all()

    @classmethod
    async def update_embedding(cls, chunk_id: str, vector: list[float]) -> None:
        async with async_session_maker() as session:
            chunk = (await session.execute(
                select(RagChunk).where(RagChunk.chunk_id == chunk_id)
            )).scalar_one_or_none()
            if chunk:
                chunk.embedding = vector
                await session.commit()

    @classmethod
    async def count_embedded(cls) -> dict:
        async with async_session_maker() as session:
            rows = (await session.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS embedded,
                    COUNT(*) FILTER (WHERE embedding IS NULL)     AS pending,
                    COUNT(*) AS total
                FROM ragchunks
            """))).fetchone()
        return {"embedded": rows.embedded, "pending": rows.pending, "total": rows.total}