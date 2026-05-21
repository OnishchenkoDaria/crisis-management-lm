from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.utils import get_current_user
from app.users.models import User
from app.workspaces.dao import WorkspaceDAO
from app.workspaces.schemas import WorkspaceCreate, WorkspaceRename, WorkspaceResponse

router = APIRouter(
    prefix="/api/workspaces",
    tags=["Workspaces"],
)


async def get_owned_workspace(
    workspace_id: int,
    current_user: User = Depends(get_current_user),
):
    workspace = await WorkspaceDAO.find_one_or_none_by_filter(
        id=workspace_id,
        user_id=current_user.id,
    )
    if not workspace:
        raise HTTPException(403, "Access denied to this workspace")
    return workspace


@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
) -> WorkspaceResponse:
    workspace = await WorkspaceDAO.add(
        user_id = current_user.id,
        name = body.name,
        description = body.description,
        language = body.language,
        do_rules = body.do_rules,
        dont_rules = body.dont_rules,
        preferred_terms = body.preferred_terms,
        forbidden_phrases = body.forbidden_phrases,
        example_messages = body.example_messages,
        tov_formality = body.tone_of_voice.formality,
        tov_empathy = body.tone_of_voice.empathy,
        tov_assertiveness = body.tone_of_voice.assertiveness,
        tov_transparency = body.tone_of_voice.transparency,
    )
    return WorkspaceResponse.model_validate(workspace)


@router.get(
    "/",
    response_model=list[WorkspaceResponse],
    summary="List all workspaces for current user",
)
async def list_workspaces(
    current_user: User = Depends(get_current_user),
) -> list[WorkspaceResponse]:
    rows = await WorkspaceDAO.find_all(user_id=current_user.id)
    return [WorkspaceResponse.model_validate(r) for r in rows]


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Get a specific workspace",
)
async def get_workspace(
    workspace=Depends(get_owned_workspace),
) -> WorkspaceResponse:
    return WorkspaceResponse.model_validate(workspace)


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Rename / update workspace",
)
async def update_workspace(
    workspace_id: int,
    body: WorkspaceRename,
    workspace=Depends(get_owned_workspace),
) -> WorkspaceResponse:
    await WorkspaceDAO.update(
        {"id": workspace_id},
        name = body.name,
        description = body.description,
    )
    updated = await WorkspaceDAO.find_one_or_none_by_filter(id=workspace_id)
    return WorkspaceResponse.model_validate(updated)


@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace and all its chats",
)
async def delete_workspace(
    workspace_id: int,
    workspace=Depends(get_owned_workspace),
) -> None:
    # Chats cascade-delete via FK ondelete="CASCADE"
    await WorkspaceDAO.delete(id=workspace_id)