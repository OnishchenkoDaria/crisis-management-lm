from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.rag.schemas import (
    RagQueryRequest, RagQueryResponse, EmbeddingStatusResponse
)
from app.rag.rag_service import handle_query
from app.rag.rag_chunk_dao import RagChunkDAO
from app.rag.embed_chunks import embed_pending_chunks

router = APIRouter(
    prefix="/api/rag",
    tags=["Rag agents cooperation calls"],
)


@router.post("/query", response_model=RagQueryResponse, summary="Dss Query")
async def dss_query(
    req: RagQueryRequest,
    background_tasks: BackgroundTasks,
) -> RagQueryResponse:
    try:
        response = await handle_query(req)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG pipeline error: {e}")

    background_tasks.add_task(_save_analysis, response, req, None, None)
    return response

async def _save_analysis(case_id: int, workspace_id: int,
                         req: RagQueryRequest, resp: RagQueryResponse):
    from app.database import async_session_maker
    from app.analysis.models import CaseAnalysis

    async with async_session_maker() as session:
        session.add(CaseAnalysis(
            case_id             = case_id,
            workspace_id        = workspace_id,
            crisis_type         = resp.crisis_type or "reputational_crisis",
            stage               = _map_phase(req.phase),
            attribution         = "unknown",        # can be set by user later
            evidence_confidence = _map_confidence(resp.confidence),
            risk_score          = _calc_risk(resp),
            factors_json        = {"recommended_actions": resp.recommended_actions,
                                   "risks": resp.risks},
            retrieved_refs_json = {"sources": [s.model_dump() for s in resp.sources]},
        ))
        await session.commit()

def _map_phase(phase: str | None) -> str:
    return {
        "pre_crisis":   "signal_detection",
        "acute":        "acute_crisis",
        "containment":  "stabilization",
        "recovery":     "recovery",
        "post_crisis":  "post_crisis_learning",
    }.get(phase or "", "acute_crisis")


def _map_confidence(confidence: str) -> str:
    return {"high": "high", "medium": "medium", "low": "low"}.get(confidence, "low")


def _calc_risk(resp: RagQueryResponse) -> float:
    """Simple risk score: 0.0–1.0 based on severity signals in response."""
    base = {"high": 0.8, "medium": 0.5, "low": 0.3}.get(resp.confidence, 0.5)
    risk_count = len(resp.risks)
    return min(1.0, base + risk_count * 0.05)

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