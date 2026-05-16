from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.utils import get_current_user
from app.chats.dao import ChatDAO
from app.workspaces.dao import WorkspaceDAO
from app.chats.model import Chat
from app.chats.schemas import ChatCreate, ChatRename, ChatResponse, WorkspaceLockStatus
from app.users.models import User
from app.analysis.analysis_service import create_analysis
from app.analysis.schemas import SituationInput

log = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api",
    tags=["Chats"]
)


async def verify_workspace_access(
        workspace_id: int,
        current_user: User = Depends(get_current_user),
) -> int:
    # Confirm the current user owns (or belongs to) the workspace.
    # Adjust the query to match your Workspace model's user relationship.

    workspace = await WorkspaceDAO.find_one_or_none_by_filter(
        id=workspace_id, user_id=current_user.id  # adjust field name if needed
    )
    if not workspace:
        raise HTTPException(403, "Access denied to this workspace")
    return workspace_id


def _to_response(chat: Chat) -> ChatResponse:
    return ChatResponse(
        id=chat.id, workspace_id=chat.workspace_id, title=chat.title,
        status=chat.status, message_count=chat.message_count,
        created_at=chat.created_at, updated_at=chat.updated_at,
        is_locked=chat.status == "generating",
        can_send=chat.status in ("empty", "in_progress"),
    )


async def _get_chat_or_404(chat_id: int, workspace_id: int) -> Chat:
    chat = await ChatDAO.find_by_workspace_and_id(workspace_id, chat_id)
    if not chat:
        raise HTTPException(404, f"Chat {chat_id} not found in workspace {workspace_id}")
    return chat


@asynccontextmanager
async def generation_lock(workspace_id: int, chat_id: int):
    acquired = await WorkspaceDAO.acquire_generation_lock(workspace_id, chat_id)
    if not acquired:
        lock = await WorkspaceDAO.get_lock_status(workspace_id)
        raise HTTPException(status_code=409, detail={
            "error": "workspace_locked",
            "message": "Another chat is currently generating a response.",
            "generating_chat_id": lock["generating_chat_id"],
            "generating_since": lock["generating_since"],
        })
    await ChatDAO.set_generating(chat_id)
    try:
        yield
    finally:
        await WorkspaceDAO.release_generation_lock(workspace_id, chat_id)
        await ChatDAO.set_in_progress(chat_id)
        log.info("Generation complete: workspace=%d chat=%d", workspace_id, chat_id)


@router.post("/workspaces/{workspace_id}/chats",
             response_model=ChatResponse,
             status_code=status.HTTP_201_CREATED,
             summary="Create a new chat in workspace"
             )
async def create_chat(
        workspace_id: int,
        body: ChatCreate,
        ws: int = Depends(verify_workspace_access),
) -> ChatResponse:
    chat = await ChatDAO.add(workspace_id=workspace_id, title=body.title, status="empty")
    return _to_response(chat)


@router.get("/workspaces/{workspace_id}/chats",
            response_model=list[ChatResponse],
            summary="List all chats in workspace"
            )
async def list_chats(
        workspace_id: int,
        ws: int = Depends(verify_workspace_access),
) -> list[ChatResponse]:
    rows = await ChatDAO.find_by_workspace(workspace_id)
    return [_to_response(c) for c in rows]


@router.delete("/workspaces/{workspace_id}/chats/{chat_id}",
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a chat"
               )
async def delete_chat(
        workspace_id: int, chat_id: int,
        ws: int = Depends(verify_workspace_access),
) -> None:
    chat = await _get_chat_or_404(chat_id, workspace_id)
    if chat.status == "generating":
        raise HTTPException(409, "Cannot delete a chat that is currently generating.")
    await ChatDAO.delete(id=chat_id, workspace_id=workspace_id)


@router.patch("/workspaces/{workspace_id}/chats/{chat_id}",
              response_model=ChatResponse,
              summary="Rename a chat"
              )
async def rename_chat(
        workspace_id: int, chat_id: int, body: ChatRename,
        ws: int = Depends(verify_workspace_access),
) -> ChatResponse:
    await _get_chat_or_404(chat_id, workspace_id)
    await ChatDAO.update({"id": chat_id, "workspace_id": workspace_id}, title=body.title)
    return _to_response(await _get_chat_or_404(chat_id, workspace_id))


@router.patch("/workspaces/{workspace_id}/chats/{chat_id}/finish",
              response_model=ChatResponse,
              summary="Mark chat as finished (read-only)"
              )
async def finish_chat(
        workspace_id: int, chat_id: int,
        ws: int = Depends(verify_workspace_access),
) -> ChatResponse:
    chat = await _get_chat_or_404(chat_id, workspace_id)
    if chat.status == "generating":
        raise HTTPException(409, "Cannot finish a generating chat.")
    if chat.status == "empty":
        raise HTTPException(400, "Cannot finish an empty chat.")
    await ChatDAO.set_finished(chat_id)
    return _to_response(await _get_chat_or_404(chat_id, workspace_id))


@router.get("/workspaces/{workspace_id}/chats/{chat_id}/status",
            summary="Get current status of a specific chat"
            )
async def get_chat_status(
        workspace_id: int, chat_id: int,
        ws: int = Depends(verify_workspace_access),
) -> dict:
    chat = await _get_chat_or_404(chat_id, workspace_id)
    return {
        "chat_id": chat.id, "status": chat.status,
        "is_locked": chat.status == "generating",
        "can_send": chat.status in ("empty", "in_progress"),
        "is_read_only": chat.status == "finished",
    }


@router.get("/workspaces/{workspace_id}/lock", response_model=WorkspaceLockStatus,
            summary="Get workspace generation lock status"
            )
async def workspace_lock_status(
        workspace_id: int,
        ws: int = Depends(verify_workspace_access),
) -> WorkspaceLockStatus:
    lock = await WorkspaceDAO.get_lock_status(workspace_id)
    return WorkspaceLockStatus(**lock)

@router.post("/workspaces/{workspace_id}/chats/{chat_id}/send", summary="Send message")
async def send_message(
        workspace_id: int, chat_id: int,
        body: dict,
        ws: int = Depends(verify_workspace_access),
) -> dict:
    chat = await _get_chat_or_404(chat_id, workspace_id)
    if chat.status == "finished":
        raise HTTPException(400, "This chat is finished.")
    async with generation_lock(workspace_id, chat_id):
        response = await create_analysis(workspace_id, SituationInput(**body))
        await ChatDAO.increment_message_count(chat_id)
        response = {"message": "ok", "chat_id": chat_id}
    return response