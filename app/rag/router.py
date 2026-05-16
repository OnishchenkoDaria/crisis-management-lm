from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.auth.utils import get_current_user
from app.rag.embed_chunks import embed_pending_chunks
from app.rag.rag_chunk_dao import RagChunkDAO
from app.rag.rag_service import handle_query
from app.rag.schemas import EmbeddingStatusResponse, RagQueryRequest, RagQueryResponse
from app.users.models import User

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/rag",
    tags=["Rag agents cooperation calls"],
)


_CRISIS_TYPE_MAP = {
    "media":                      "information_disinformation_crisis",
    "reputational":               "reputational_crisis",
    "reputational_crisis":        "reputational_crisis",
    "operational":                "operational_failure_crisis",
    "operational_failure_crisis": "operational_failure_crisis",
    "safety":                     "physical_or_cyber_security_crisis",
    "political":                  "values_ethics_crisis",
    "internal":                   "operational_failure_crisis",
    "natural_disaster":           "physical_or_cyber_security_crisis",
    "information_disinformation_crisis": "information_disinformation_crisis",
    "values_ethics_crisis":       "values_ethics_crisis",
    "leadership_personal_crisis": "leadership_personal_crisis",
    "physical_or_cyber_security_crisis": "physical_or_cyber_security_crisis",
}


def _map_crisis_type(crisis_type: str | None) -> str:
    if not crisis_type:
        return "reputational_crisis"
    return _CRISIS_TYPE_MAP.get(crisis_type.lower(), "reputational_crisis")


def _map_phase(phase: str | None) -> str:
    return {
        "pre_crisis": "signal_detection",
        "acute": "acute_crisis",
        "containment": "stabilization",
        "recovery": "recovery",
        "post_crisis": "post_crisis_learning",
    }.get(phase or "", "acute_crisis")


def _map_confidence(confidence: str) -> str:
    return {"high": "high", "medium": "medium", "low": "low"}.get(confidence, "low")


def _calc_risk(resp: RagQueryResponse) -> float:
    base = {"high": 0.8, "medium": 0.5, "low": 0.3}.get(resp.confidence, 0.5)
    return min(1.0, base + len(resp.risks) * 0.05)



async def _save_analysis(
    resp: RagQueryResponse,
    req: RagQueryRequest,
    case_id: int | None,
    workspace_id: int | None,
) -> None:
    if resp is None:
        log.warning("_save_analysis called with None response — skipping")
        return

    try:
        from app.database import async_session_maker
        import app.workspaces.models
        import app.cases.models
        from app.analysis.models import CaseAnalysis

        async with async_session_maker() as session:
            session.add(CaseAnalysis(
                case_id = case_id,
                workspace_id = workspace_id,
                crisis_type = _map_crisis_type(resp.crisis_type),
                stage = _map_phase(req.phase),
                attribution = "unknown",
                evidence_confidence = _map_confidence(resp.confidence),
                risk_score = _calc_risk(resp),
                factors_json = {
                    "recommended_actions": resp.recommended_actions,
                    "risks": resp.risks,
                },
                retrieved_refs_json = {
                    "sources": [s.model_dump() for s in resp.sources],
                },
            ))
            await session.commit()
            log.info("CaseAnalysis saved (risk=%.2f)", _calc_risk(resp))

    except Exception as e:
        log.warning("CaseAnalysis save failed (non-fatal): %s", e)



@router.post("/query", response_model=RagQueryResponse, summary="Dss Query")
async def dss_query(
    req: RagQueryRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(get_current_user),
) -> RagQueryResponse:
    try:
        response = await handle_query(req)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG pipeline error: {e}")

    background_tasks.add_task(_save_analysis, response, req, None, None)
    return response


@router.get("/embedding-status",
            response_model=EmbeddingStatusResponse, summary="Embedding coverage status")
async def embedding_status(
    _: User = Depends(get_current_user),
) -> EmbeddingStatusResponse:
    stats = await RagChunkDAO.count_embedded()
    total = stats["total"] or 1
    return EmbeddingStatusResponse(
        total    = stats["total"],
        embedded = stats["embedded"],
        pending  = stats["pending"],
        coverage = round(stats["embedded"] / total, 3),
    )


@router.post("/embed", summary="Trigger embedding for pending chunks")
async def trigger_embedding(
    background_tasks: BackgroundTasks,
    _: User = Depends(get_current_user),
    limit: int | None = None,
) -> dict:
    background_tasks.add_task(embed_pending_chunks, limit)
    return {
        "status":  "started",
        "message": "Embedding started in background. Check /embedding-status for progress.",
    }