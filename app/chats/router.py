"""
app/chats/router.py
====================
Chat management endpoints.

Endpoints:
  POST   /workspaces/{workspace_id}/chats                 Create chat
  GET    /workspaces/{workspace_id}/chats                 List all chats
  DELETE /workspaces/{workspace_id}/chats/{chat_id}       Delete chat
  PATCH  /workspaces/{workspace_id}/chats/{chat_id}       Rename chat
  GET    /workspaces/{workspace_id}/chats/{chat_id}/status Get chat status
  GET    /workspaces/{workspace_id}/lock                  Workspace lock state

  POST   /workspaces/{workspace_id}/chats/{chat_id}/send  Send message
         (shows lock integration — returns 409 if workspace locked)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update, delete

from app.analysis.schemas import SituationInput
from app.chats.model import Chat
from app.chats.schemas import ChatCreate, ChatRename, ChatResponse, WorkspaceLockStatus
from app.chats.lock import acquire_workspace_lock, release_workspace_lock, get_lock_status
from app.database import async_session_maker

log = logging.getLogger(__name__)
router = APIRouter(tags=["Chats"])



def _to_response(chat: Chat) -> ChatResponse:
    return ChatResponse(
        id = chat.id,
        workspace_id = chat.workspace_id,
        title = chat.title,
        status = chat.status,
        message_count = chat.message_count,
        created_at = chat.created_at,
        updated_at = chat.updated_at,
        is_locked = chat.status == "generating",
        can_send = chat.status in ("empty", "in_progress"),
    )


async def _get_chat_or_404(chat_id: int, workspace_id: int) -> Chat:
    async with async_session_maker() as session:
        chat = (await session.execute(
            select(Chat).where(Chat.id == chat_id, Chat.workspace_id == workspace_id)
        )).scalar_one_or_none()
    if not chat:
        raise HTTPException(404, f"Chat {chat_id} not found in workspace {workspace_id}")
    return chat


@asynccontextmanager
async def generation_lock(workspace_id: int, chat_id: int):
    # Context manager that acquires the workspace lock, sets chat status
    # to 'generating', runs the block, then releases lock and restores status.

    async with async_session_maker() as session:
        await session.execute(
            update(Chat)
            .where(Chat.id == chat_id)
            .values(status="generating")
        )
        await session.commit()

    try:
        yield
    finally:
        # Always release lock and restore status, even on exception
        await release_workspace_lock(workspace_id, chat_id)
        async with async_session_maker() as session:
            await session.execute(
                update(Chat)
                .where(Chat.id == chat_id)
                .values(status="in_progress")
            )
            await session.commit()
        log.info("Generation complete: workspace=%d chat=%d", workspace_id, chat_id)



@router.post(
    "/workspaces/{workspace_id}/chats",
    response_model=ChatResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat in workspace",
)
async def create_chat(workspace_id: int, body: ChatCreate) -> ChatResponse:
    async with async_session_maker() as session:
        chat = Chat(workspace_id=workspace_id, title=body.title, status="empty")
        session.add(chat)
        await session.commit()
        await session.refresh(chat)
    return _to_response(chat)


@router.get(
    "/workspaces/{workspace_id}/chats",
    response_model=list[ChatResponse],
    summary="List all chats in workspace",
)
async def list_chats(workspace_id: int) -> list[ChatResponse]:
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(Chat)
            .where(Chat.workspace_id == workspace_id)
            .order_by(Chat.updated_at.desc())
        )).scalars().all()
    return [_to_response(c) for c in rows]


@router.delete(
    "/workspaces/{workspace_id}/chats/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat",
)
async def delete_chat(workspace_id: int, chat_id: int) -> None:
    chat = await _get_chat_or_404(chat_id, workspace_id)

    # Refuse to delete a chat that is currently generating
    if chat.status == "generating":
        raise HTTPException(
            409,
            "Cannot delete a chat that is currently generating a response. "
            "Wait for generation to complete first."
        )

    async with async_session_maker() as session:
        await session.execute(
            delete(Chat).where(Chat.id == chat_id, Chat.workspace_id == workspace_id)
        )
        await session.commit()


@router.patch(
    "/workspaces/{workspace_id}/chats/{chat_id}",
    response_model=ChatResponse,
    summary="Rename a chat",
)
async def rename_chat(
    workspace_id: int,
    chat_id: int,
    body: ChatRename,
) -> ChatResponse:
    await _get_chat_or_404(chat_id, workspace_id)

    async with async_session_maker() as session:
        await session.execute(
            update(Chat)
            .where(Chat.id == chat_id, Chat.workspace_id == workspace_id)
            .values(title=body.title)
        )
        await session.commit()

    return _to_response(await _get_chat_or_404(chat_id, workspace_id))


@router.patch(
    "/workspaces/{workspace_id}/chats/{chat_id}/finish",
    response_model=ChatResponse,
    summary="Mark chat as finished (read-only)",
)
async def finish_chat(workspace_id: int, chat_id: int) -> ChatResponse:
    chat = await _get_chat_or_404(chat_id, workspace_id)

    if chat.status == "generating":
        raise HTTPException(409, "Cannot finish a chat that is currently generating.")
    if chat.status == "empty":
        raise HTTPException(400, "Cannot finish an empty chat.")

    async with async_session_maker() as session:
        await session.execute(
            update(Chat)
            .where(Chat.id == chat_id)
            .values(status="finished")
        )
        await session.commit()

    return _to_response(await _get_chat_or_404(chat_id, workspace_id))


@router.get(
    "/workspaces/{workspace_id}/chats/{chat_id}/status",
    summary="Get current status of a specific chat",
)
async def get_chat_status(workspace_id: int, chat_id: int) -> dict:
    chat = await _get_chat_or_404(chat_id, workspace_id)
    return {
        "chat_id": chat.id,
        "status": chat.status,
        "is_locked": chat.status == "generating",
        "can_send": chat.status in ("empty", "in_progress"),
        "is_read_only": chat.status == "finished",
    }


@router.get(
    "/workspaces/{workspace_id}/lock",
    response_model=WorkspaceLockStatus,
    summary="Get workspace generation lock status",
    description=(
        "Frontend polls this endpoint (every 2–3s) to know if any "
        "chat is generating. Disables send buttons across all chats "
        "when is_locked=true."
    ),
)
async def workspace_lock_status(workspace_id: int) -> WorkspaceLockStatus:
    lock = await get_lock_status(workspace_id)
    return WorkspaceLockStatus(**lock)



@router.post(
    "/workspaces/{workspace_id}/chats/{chat_id}/send",
    summary="Send message — shows lock enforcement pattern",
)
async def send_message(
    workspace_id: int,
    chat_id: int,
    body: SituationInput,
) -> dict:
    chat = await _get_chat_or_404(chat_id, workspace_id)

    if chat.status == "finished":
        raise HTTPException(400, "This chat is finished and cannot receive new messages.")

    async with generation_lock(workspace_id, chat_id):
        # TODO: Replace this with your actual RAG or analysis call
        # response = await handle_query(RagQueryRequest(**body))
        # response = await create_analysis(workspace_id, SituationInput(**body))

        # Increment message count
        async with async_session_maker() as session:
            await session.execute(
                update(Chat)
                .where(Chat.id == chat_id)
                .values(message_count=Chat.message_count + 1)
            )
            await session.commit()

        response = {"message": "Generation complete", "chat_id": chat_id}

    return response