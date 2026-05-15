from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm.attributes import flag_modified

from app.analysis.analysis_service import create_analysis, generate_roadmap, refine_analysis
from app.analysis.dao import AnalysisDAO
from app.roadmaps.dao import RoadmapDAO
from app.analysis.schemas import (
    SituationInput, RefinementRequest,
    AnalysisResponse, RoadmapResponse, ActionItemUpdate,
)
from app.auth.utils import get_current_user
from app.database import async_session_maker
from app.users.models import User
from app.workspaces.dao import WorkspaceDAO

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/analysis",
    tags=["Crisis Analysis & Roadmap"]
)


async def verify_workspace(
    workspace_id: int,
    current_user: User = Depends(get_current_user),
) -> int:
    workspace = await WorkspaceDAO.find_one_or_none_by_filter(
        id=workspace_id,
        user_id=current_user.id,
    )
    if not workspace:
        raise HTTPException(403, "Access denied to this workspace")
    return workspace_id


async def verify_analysis_access(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
) -> "Analysis":
    #Load analysis and confirm the current user owns its workspace
    row = await AnalysisDAO.find_one_or_none_by_id_str(analysis_id)
    if not row:
        raise HTTPException(404, "Analysis not found")

    workspace = await WorkspaceDAO.find_one_or_none_by_filter(
        id=row.workspace_id,
        user_id=current_user.id,
    )
    if not workspace:
        raise HTTPException(403, "Access denied to this analysis")

    return row


async def verify_roadmap_access(
    roadmap_id: str,
    current_user: User = Depends(get_current_user),
) -> "Roadmap":
    #Load roadmap and confirm the current user owns its workspace
    row = await RoadmapDAO.find_one_or_none_by_id_str(roadmap_id)
    if not row:
        raise HTTPException(404, "Roadmap not found")

    workspace = await WorkspaceDAO.find_one_or_none_by_filter(
        id=row.workspace_id,
        user_id=current_user.id,
    )
    if not workspace:
        raise HTTPException(403, "Access denied to this roadmap")

    return row


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
async def get_analysis(
    row=Depends(verify_analysis_access),
) -> AnalysisResponse:
    return AnalysisResponse(**row.response_json)


@router.post(
    "/analyses/{analysis_id}/refine",
    response_model=AnalysisResponse,
    summary="Step 3 — Submit user corrections and get refined analysis",
)
async def refine(
    analysis_id: str,
    body: RefinementRequest,
    row=Depends(verify_analysis_access),
) -> AnalysisResponse:
    try:
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
async def create_roadmap(
    analysis_id: str,
    row =Depends(verify_analysis_access),
) -> RoadmapResponse:
    # Only available when analysis.can_generate_roadmap == True.
    # returns phased action plan with monitoring and escalation rules.
    if not row.can_generate_roadmap:
        raise HTTPException(
            400,
            "Analysis not ready for roadmap generation. "
            "Confidence too low or missing information fields present. "
            "Use /refine to add missing details first.",
        )
    try:
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
async def get_roadmap(
    row=Depends(verify_roadmap_access),
) -> RoadmapResponse:
    return RoadmapResponse(**row.roadmap_json)



@router.patch(
    "/roadmaps/{roadmap_id}/items/{item_id}",
    summary="Step 6 — Update action item status",
)
async def update_action_item(
    item_id: str,
    body: ActionItemUpdate,
    row=Depends(verify_roadmap_access),
) -> dict:
    roadmap_data = dict(row.roadmap_json)   # shallow copy so SQLAlchemy sees the change
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

    async with async_session_maker() as session:
        session.add(row)
        row.roadmap_json = roadmap_data
        flag_modified(row, "roadmap_json")   # tell SQLAlchemy the JSONB changed
        await session.commit()

    return {
        "status": "updated",
        "item_id": item_id,
        "new_status": body.status.value,
    }