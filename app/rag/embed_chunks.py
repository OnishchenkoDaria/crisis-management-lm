"""
Batch embedding script — generates embeddings for all ragchunks
where embedding IS NULL, then stores the vector in the DB.

Usage:
  python -m app.rag.embed_chunks            # embed all pending chunks
  python -m app.rag.embed_chunks --limit 50 # embed first 50 only (test run)

IMPORTANT — before running this script:
  1. Ensure EMBEDDING_DIM matches your model (see embedding_provider.py).
  2. Never mix embeddings from different models — if you change models,
     set all existing embeddings to NULL first:
       UPDATE ragchunks SET embedding = NULL;
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select, update

from app.database import async_session_maker
from app.ingest.models.rag_chunk_model import RagChunk
from app.rag.embedding_provider import embed_texts, BATCH_SIZE, DIM

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


async def embed_pending_chunks(limit: int | None = None) -> int:
    """
    Find all ragchunks with embedding IS NULL, generate embeddings in batches,
    and store them. Returns the count of newly embedded chunks.
    """
    async with async_session_maker() as session:
        # Count pending
        q = select(RagChunk).where(RagChunk.embedding.is_(None))
        if limit:
            q = q.limit(limit)
        result  = await session.execute(q)
        pending = result.scalars().all()

    total = len(pending)
    if total == 0:
        log.info("All chunks already embedded.")
        return 0

    log.info("Found %d chunks to embed (dim=%d)", total, DIM)
    embedded = 0

    for i in range(0, total, BATCH_SIZE):
        batch = pending[i : i + BATCH_SIZE]
        texts = [c.text for c in batch]

        try:
            vectors = await embed_texts(texts)
        except ValueError as e:
            log.error("Dimension mismatch — stopping.\n%s", e)
            break
        except Exception as e:
            log.error("Embedding error on batch %d: %s", i, e)
            continue

        # Write vectors back to DB
        async with async_session_maker() as session:
            for chunk, vector in zip(batch, vectors):
                await session.execute(
                    update(RagChunk)
                    .where(RagChunk.id == chunk.id)
                    .values(embedding=vector)
                )
            await session.commit()

        embedded += len(batch)
        log.info(
            "  Embedded %d/%d  (chunks %d–%d)",
            embedded, total, i + 1, i + len(batch),
        )

    log.info("Done. %d/%d chunks embedded.", embedded, total)
    return embedded


async def count_embedding_status() -> dict:
    async with async_session_maker() as session:
        total_q   = select(RagChunk)
        pending_q = select(RagChunk).where(RagChunk.embedding.is_(None))

        total   = len((await session.execute(total_q)).scalars().all())
        pending = len((await session.execute(pending_q)).scalars().all())

    return {"total": total, "embedded": total - pending, "pending": pending}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed RAG chunks")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of chunks to embed (default: all)")
    parser.add_argument("--status", action="store_true",
                        help="Print embedding coverage and exit")
    args = parser.parse_args()

    if args.status:
        status = asyncio.run(count_embedding_status())
        print(f"\n── Embedding status ──────────────────────")
        print(f"  Total chunks:    {status['total']}")
        print(f"  Embedded:        {status['embedded']}")
        print(f"  Pending:         {status['pending']}")
        print()
    else:
        asyncio.run(embed_pending_chunks(limit=args.limit))