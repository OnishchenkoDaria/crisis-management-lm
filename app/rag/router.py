from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.rag.schemas import (
    RagQueryRequest, RagQueryResponse, EmbeddingStatusResponse
)
from app.rag.rag_service import handle_query
from app.rag.rag_chunk_dao import RagChunkDAO
from app.rag.embed_chunks import embed_pending_chunks

router = APIRouter()


@router.post(
    "/query",
    response_model=RagQueryResponse,
    summary="Crisis communications DSS query",
    description=(
        "Send a crisis situation description and receive structured "
        "tactical guidance grounded in uploaded source documents."
    ),
)
async def dss_query(req: RagQueryRequest) -> RagQueryResponse:
    """
    Main RAG endpoint.

    "query": "Journalists arrived at the facility. We have no confirmed data yet.",
    "crisis_type": "media",
    "phase": "acute"

    """
    try:
        return await handle_query(req)
    except ValueError as e:
        # Embedding dimension mismatch or missing model
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"RAG pipeline error: {str(e)}"
        )


@router.get(
    "/embedding-status",
    response_model=EmbeddingStatusResponse,
    summary="Embedding coverage status",
)
async def embedding_status() -> EmbeddingStatusResponse:
    """Returns how many ragchunks have embeddings vs are still pending."""
    stats = await RagChunkDAO.count_embedded()
    total = stats["total"] or 1  # avoid division by zero
    return EmbeddingStatusResponse(
        total    = stats["total"],
        embedded = stats["embedded"],
        pending  = stats["pending"],
        coverage = round(stats["embedded"] / total, 3),
    )


@router.post(
    "/embed",
    summary="Trigger embedding for pending chunks",
    description=(
        "Starts a background job to embed all ragchunks where "
        "embedding IS NULL. Returns immediately; embedding runs in background."
    ),
)
async def trigger_embedding(
    background_tasks: BackgroundTasks,
    limit: int | None = None,
) -> dict:
    """
    Triggers embed_pending_chunks() as a background task.
    Check /embedding-status for progress.
    """
    background_tasks.add_task(embed_pending_chunks, limit)
    return {
        "status":  "started",
        "message": "Embedding started in background. Check /embedding-status for progress.",
    }