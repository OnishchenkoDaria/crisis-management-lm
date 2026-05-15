from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.analysis.schemas import (
    SituationInput, RefinementRequest,
    AnalysisResponse, RoadmapResponse, ActionItemUpdate,
)
from app.analysis.analysis_service import create_analysis, refine_analysis, generate_roadmap
from app.analysis.models import Analysis
from app.roadmaps.models import Roadmap
from app.database import async_session_maker

# TODO: from app.users.dependencies import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/analysis",
    tags=["Crisis Analysis & Roadmap"]
)


async def verify_workspace(workspace_id: int) -> int:
    # TODO: replace with proper auth
    # user = get_current_user(...)
    # workspace = await WorkspaceDAO.find_one_or_none(id=workspace_id, user_id=user.id)
    # if not workspace:
    #     raise HTTPException(403, "Access denied")
    return workspace_id


@router.post(
    "/workspaces/{workspace_id}/analyses",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Step 1 — Submit crisis situation and get preliminary analysis",
)
async def submit_situation(
    workspace_id: int,
    body: SituationInput,
    _: int = Depends(verify_workspace),
) -> AnalysisResponse:

    # Accepts a structured crisis situation form.
    """ Frontend req should have:
    - crisis_summary, urgency_level, confidence badge
    - key_risks, stakeholders, recommended_strategy
    - relevant_tactics (as expandable cards)
    - suggested_initial_message (as copyable block)
    - next_questions (if confidence < high)
    - "Generate Roadmap" button enabled only if can_generate_roadmap == True
    """
    try:
        return await create_analysis(workspace_id, body)
    except Exception as e:
        log.error("Analysis creation failed: %s", e)
        raise HTTPException(500, detail=f"Analysis failed: {e}")



@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisResponse,
    summary="Step 2 — Get preliminary analysis",
)
async def get_analysis(analysis_id: str) -> AnalysisResponse:
    async with async_session_maker() as session:
        row = (await session.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )).scalar_one_or_none()

    if not row:
        raise HTTPException(404, "Analysis not found")

    return AnalysisResponse(**row.response_json)


@router.post(
    "/analyses/{analysis_id}/refine",
    response_model=AnalysisResponse,
    summary="Step 3 — Submit user corrections and get refined analysis",
)
async def refine(
    analysis_id: str,
    body: RefinementRequest,
) -> AnalysisResponse:
    # User adds corrections, missing context
    try:
        async with async_session_maker() as session:
            row = (await session.execute(
                select(Analysis).where(Analysis.id == analysis_id)
            )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Analysis not found")

        return await refine_analysis(analysis_id, row.workspace_id, body)
    except HTTPException:
        raise
    except Exception as e:
        log.error("Refinement failed: %s", e)
        raise HTTPException(500, detail=f"Refinement failed: {e}")


@router.post(
    "/analyses/{analysis_id}/roadmap",
    response_model=RoadmapResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Step 4 — Generate final action roadmap",
)
async def create_roadmap(analysis_id: str) -> RoadmapResponse:
    # Only available when analysis.can_generate_roadmap == True.
    # returns phased action plan with monitoring and escalation rules.
    try:
        async with async_session_maker() as session:
            row = (await session.execute(
                select(Analysis).where(Analysis.id == analysis_id)
            )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Analysis not found")
        if not row.can_generate_roadmap:
            raise HTTPException(
                400,
                "Analysis not ready for roadmap generation. "
                "Confidence too low or missing information fields present. "
                "Use /refine to add missing details first."
            )

        return await generate_roadmap(analysis_id, row.workspace_id)
    except HTTPException:
        raise
    except Exception as e:
        log.error("Roadmap generation failed: %s", e)
        raise HTTPException(500, detail=f"Roadmap generation failed: {e}")


@router.get(
    "/roadmaps/{roadmap_id}",
    response_model=RoadmapResponse,
    summary="Step 5 — Get final roadmap",
)
async def get_roadmap(roadmap_id: str) -> RoadmapResponse:
    async with async_session_maker() as session:
        row = (await session.execute(
            select(Roadmap).where(Roadmap.id == roadmap_id)
        )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Roadmap not found")
    return RoadmapResponse(**row.roadmap_json)



@router.patch(
    "/roadmaps/{roadmap_id}/items/{item_id}",
    summary="Step 6 — Update action item status",
)
async def update_action_item(
    roadmap_id: str,
    item_id:    str,
    body:       ActionItemUpdate,
) -> dict:
    # User marks action items as done/in_progress/skipped in the live roadmap.
    async with async_session_maker() as session:
        row = (await session.execute(
            select(Roadmap).where(Roadmap.id == roadmap_id)
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Roadmap not found")

        # Mutate the JSONB
        roadmap_data = row.roadmap_json
        updated = False
        for phase in roadmap_data.get("phases", []):
            for item in phase.get("action_items", []):
                if item["id"] == item_id:
                    item["status"] = body.status.value
                    if body.note:
                        item["note"] = body.note
                    updated = True
                    break

        if not updated:
            raise HTTPException(404, f"Action item {item_id} not found")

        row.roadmap_json = roadmap_data
        await session.commit()

    return {"status": "updated", "item_id": item_id, "new_status": body.status.value}