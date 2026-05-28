from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.analysis.analysis_service import create_analysis, refine_analysis
from app.analysis.schemas import SituationInput, AnalysisResponse
from app.auth.utils import get_current_user, get_optional_user, get_chat_permission
from app.chats.dao import ChatDAO
from app.chats.models import Chat
from app.chats.schemas import ChatCreate, ChatRename, ChatResponse, WorkspaceLockStatus, ClarifyRequest
from app.chats.dao import ShareLinkDAO
from app.chats.schemas import ShareLinkResponse
from app.messages.dao import MessageDAO
from app.roadmaps.dao import RoadmapDAO
from app.users.models import User
from app.workspaces.dao import WorkspaceDAO
from app.analysis.schemas import RefinementRequest
from app.analysis.analysis_service import generate_roadmap
from app.analysis.schemas import RoadmapResponse
from app.chats.schemas import RoadmapGenerateRequest

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Chats"])


async def verify_workspace_access(
    workspace_id: int,
    current_user: User = Depends(get_current_user),
) -> int:
    """Confirms the logged-in user owns this workspace."""
    workspace = await WorkspaceDAO.find_one_or_none_by_filter(
        id=workspace_id, user_id=current_user.id
    )
    if not workspace:
        raise HTTPException(403, "Access denied to this workspace")
    return workspace_id


def _to_response(chat: Chat) -> ChatResponse:
    return ChatResponse(
        id=chat.id, workspace_id=chat.workspace_id,
        title=chat.title, status=chat.status,
        message_count=chat.message_count,
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
        chat = await ChatDAO.find_by_workspace_and_id(workspace_id, chat_id)
        if chat and chat.status != "finished":
            await ChatDAO.set_in_progress(chat_id)
        log.info("Generation complete: workspace=%d chat=%d", workspace_id, chat_id)


@router.post(
    "/workspaces/{workspace_id}/chats",
    response_model=ChatResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat(
    workspace_id: int,
    body: ChatCreate,
    current_user: User = Depends(get_current_user),
    _: int = Depends(verify_workspace_access),
) -> ChatResponse:
    # user_id stored — this user becomes the chat owner
    chat = await ChatDAO.add(
        workspace_id=workspace_id,
        user_id=current_user.id,          # ← new
        title=body.title,
        status="empty",
    )
    return _to_response(chat)


@router.get("/workspaces/{workspace_id}/chats", response_model=list[ChatResponse])
async def list_chats(
    workspace_id: int,
    _: int = Depends(verify_workspace_access),  # workspace owner only
) -> list[ChatResponse]:
    rows = await ChatDAO.find_by_workspace(workspace_id)
    return [_to_response(c) for c in rows]


@router.delete(
    "/workspaces/{workspace_id}/chats/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat(
    workspace_id: int,
    chat_id: int,
    current_user: User | None = Depends(get_optional_user),
    token: str | None = Query(None),
) -> None:
    permission = await get_chat_permission(chat_id, current_user, token)
    if permission != "owner":
        raise HTTPException(403, "Only the chat owner can delete this chat")

    chat = await _get_chat_or_404(chat_id, workspace_id)
    if chat.status == "generating":
        raise HTTPException(409, "Cannot delete a chat that is currently generating")
    await ChatDAO.delete(id=chat_id, workspace_id=workspace_id)


@router.patch("/workspaces/{workspace_id}/chats/{chat_id}", response_model=ChatResponse)
async def rename_chat(
    workspace_id: int,
    chat_id: int,
    body: ChatRename,
    current_user: User | None = Depends(get_optional_user),
    token: str | None = Query(None),
) -> ChatResponse:
    permission = await get_chat_permission(chat_id, current_user, token)
    if permission != "owner":
        raise HTTPException(403, "Only the chat owner can rename this chat")

    await _get_chat_or_404(chat_id, workspace_id)
    await ChatDAO.update({"id": chat_id, "workspace_id": workspace_id}, title=body.title)
    return _to_response(await _get_chat_or_404(chat_id, workspace_id))


@router.patch(
    "/workspaces/{workspace_id}/chats/{chat_id}/finish",
    response_model=ChatResponse,
)
async def finish_chat(
    workspace_id: int,
    chat_id: int,
    current_user: User | None = Depends(get_optional_user),
    token: str | None = Query(None),
) -> ChatResponse:
    permission = await get_chat_permission(chat_id, current_user, token)
    if permission != "owner":
        raise HTTPException(403, "Only the chat owner can finish this chat")

    chat = await _get_chat_or_404(chat_id, workspace_id)
    if chat.status == "generating":
        raise HTTPException(409, "Cannot finish a generating chat")
    if chat.status == "empty":
        raise HTTPException(400, "Cannot finish an empty chat")
    await ChatDAO.set_finished(chat_id)
    return _to_response(await _get_chat_or_404(chat_id, workspace_id))


@router.get("/workspaces/{workspace_id}/chats/{chat_id}/status")
async def get_chat_status(
    workspace_id: int,
    chat_id: int,
    current_user: User | None = Depends(get_optional_user),  # ← optional
    token: str | None = Query(None),
) -> dict:
    permission = await get_chat_permission(chat_id, current_user, token)
    if permission == "none":
        raise HTTPException(403, "Access denied")

    chat = await _get_chat_or_404(chat_id, workspace_id)
    return {
        "chat_id": chat.id,
        "status": chat.status,
        "is_locked": chat.status == "generating",
        "can_send": chat.status in ("empty", "in_progress"),
        "is_read_only": chat.status == "finished",
        "permission": permission,
    }


@router.get("/workspaces/{workspace_id}/lock", response_model=WorkspaceLockStatus)
async def workspace_lock_status(
    workspace_id: int,
    _: int = Depends(verify_workspace_access),
) -> WorkspaceLockStatus:
    lock = await WorkspaceDAO.get_lock_status(workspace_id)
    return WorkspaceLockStatus(**lock)


@router.post(
    "/workspaces/{workspace_id}/chats/{chat_id}/send",
    response_model=AnalysisResponse,
)
async def send_message(
    workspace_id: int,
    chat_id: int,
    body: SituationInput,
    current_user: User | None = Depends(get_optional_user),
    token: str | None = Query(None),
) -> AnalysisResponse:
    permission = await get_chat_permission(chat_id, current_user, token)
    if permission != "owner":
        raise HTTPException(403, "Only the chat owner can send messages")

    chat = await _get_chat_or_404(chat_id, workspace_id)
    if chat.status == "finished":
        raise HTTPException(400, "This chat is finished")

    await MessageDAO.save_user_message(
        chat_id=chat_id,
        content=body.situation_description,
        payload=body.model_dump(),
    )

    async with generation_lock(workspace_id, chat_id):
        try:
            response = await create_analysis(workspace_id, body)
        except ValueError as e:
            await MessageDAO.delete_last_user_message(chat_id)
            raise HTTPException(422, str(e))
        except (RuntimeError, ConnectionError, OSError) as e:
            await MessageDAO.delete_last_user_message(chat_id)
            log.error("Connectivity error during analysis: %s", e)
            raise HTTPException(503, "Analysis service temporarily unavailable — please try again")

        await MessageDAO.save_assistant_message(
            chat_id=chat_id,
            content=_build_assistant_summary(response),
            payload=response.model_dump(),
            analysis_id=response.analysis_id,
        )
        await ChatDAO.increment_message_count(chat_id)

    return response

def _build_assistant_summary(response: AnalysisResponse) -> str:
    crisis_type = response.detected_crisis_type
    urgency     = response.urgency_level
    if hasattr(crisis_type, "value"): crisis_type = crisis_type.value
    if hasattr(urgency, "value"):     urgency     = urgency.value

    lines = [
        f"**{crisis_type.upper()} · {urgency} urgency**",
        "",
        response.crisis_summary,
    ]

    # Recommended strategy — the core advice
    if response.recommended_strategy:
        lines += ["", "**Recommended strategy**", response.recommended_strategy]

    # Tactics — specific actions to take
    if response.relevant_tactics:
        lines += ["", "**Tactics**"]
        for t in response.relevant_tactics:
            lines.append(f"**{t.name}** — {t.description}")
            if t.anti_pattern:
                lines.append(f"⚠ Avoid: {t.anti_pattern}")

    # Suggested message — ready to use
    if response.suggested_initial_message:
        lines += ["", "**Suggested statement**", f"> {response.suggested_initial_message}"]

    # Key risks
    if response.key_risks:
        lines += ["", "**Key risks**"]
        lines += [f"– {r}" for r in response.key_risks[:3]]

    # Missing info — informational only, not a blocker
    if response.missing_information:
        lines += ["", "⚠ **Would improve analysis**"]
        lines += [f"– {item}" for item in response.missing_information[:3]]

    # Sources
    if response.retrieved_sources:
        lines += ["", "**Sources**"]
        lines += [
            f"– *{s.title}* — {s.chapter} (relevance: {s.similarity:.0%})"
            for s in response.retrieved_sources[:3]
        ]

    return "\n".join(lines)

@router.post(
    "/workspaces/{workspace_id}/chats/{chat_id}/share",
    response_model=ShareLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_share_link(
    workspace_id: int,
    chat_id: int,
    current_user: User | None = Depends(get_optional_user),
    token: str | None = Query(None),
) -> ShareLinkResponse:
    permission = await get_chat_permission(chat_id, current_user, token)
    if permission != "owner":
        raise HTTPException(403, "Only the chat owner can create share links")

    await _get_chat_or_404(chat_id, workspace_id)
    link = await ShareLinkDAO.create(chat_id=chat_id, created_by=current_user.id)
    return ShareLinkResponse.model_validate(link)


@router.delete(
    "/workspaces/{workspace_id}/chats/{chat_id}/share/{link_token}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_share_link(
    workspace_id: int,
    chat_id: int,
    link_token: str,
    current_user: User | None = Depends(get_optional_user),
    token: str | None = Query(None),
) -> None:
    permission = await get_chat_permission(chat_id, current_user, token)
    if permission != "owner":
        raise HTTPException(403, "Only the chat owner can revoke share links")

    revoked = await ShareLinkDAO.revoke(link_token)
    if not revoked:
        raise HTTPException(404, "Share link not found")


@router.post(
    "/workspaces/{workspace_id}/chats/{chat_id}/clarify",
    response_model=AnalysisResponse,
)
async def clarify_analysis(
    workspace_id: int,
    chat_id:      int,
    body:         ClarifyRequest,
    current_user: User | None = Depends(get_optional_user),
    token:        str | None  = Query(None),
) -> AnalysisResponse:
    permission = await get_chat_permission(chat_id, current_user, token)
    if permission != "owner":
        raise HTTPException(403, "Only the chat owner can clarify")

    answers_text = "\n".join(f"**{q}**\n{a}" for q, a in body.answers.items())
    await MessageDAO.save_user_message(
        chat_id=chat_id,
        content=answers_text,
        payload={"type": "clarification", "answers": body.answers},
    )

    # Build RefinementRequest object — not keyword args
    refinement = RefinementRequest(
        user_comment="\n".join(f"{q}: {a}" for q, a in body.answers.items()),
        fields_to_update=body.answers,
        additional_context=None,
        changed_constraints=[],
    )

    response = await refine_analysis(
        analysis_id=body.analysis_id,
        workspace_id=workspace_id,
        refinement=refinement,
    )

    await MessageDAO.save_assistant_message(
        chat_id=chat_id,
        content=_build_assistant_summary(response),
        payload=response.model_dump(),
        analysis_id=response.analysis_id,
    )

    return response

@router.post(
    "/workspaces/{workspace_id}/chats/{chat_id}/roadmap",
    response_model=RoadmapResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_chat_roadmap(
    workspace_id: int,
    chat_id: int,
    body: RoadmapGenerateRequest,
    current_user: User | None = Depends(get_optional_user),
    token: str | None = Query(None),
) -> RoadmapResponse:
    async with generation_lock(workspace_id, chat_id):
        try:
            roadmap = await generate_roadmap(body.analysis_id, workspace_id)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except (RuntimeError, ConnectionError, OSError) as e:
            raise HTTPException(503, "Roadmap generation temporarily unavailable")

        # Set finished INSIDE the lock, before finally releases it
        await ChatDAO.set_finished(chat_id)

    return roadmap


@router.get(
    "/workspaces/{workspace_id}/chats/{chat_id}/roadmap",
    response_model=RoadmapResponse,
)
async def get_chat_roadmap(
    workspace_id: int,
    chat_id: int,
    current_user: User | None = Depends(get_optional_user),
    token: str | None = Query(None),
) -> RoadmapResponse:
    permission = await get_chat_permission(chat_id, current_user, token)
    if permission == "none":
        raise HTTPException(403, "Access denied")

    # Find last analysis_id from this chat's messages
    last_msg = await MessageDAO.find_last_analysis_message(chat_id)
    if not last_msg or not last_msg.analysis_id:
        raise HTTPException(404, "No analysis found for this chat")

    roadmap = await RoadmapDAO.find_latest_by_analysis_id(last_msg.analysis_id)
    if not roadmap:
        raise HTTPException(404, "No roadmap generated for this chat yet")

    log.info("roadmap_json keys: %s", list(roadmap.roadmap_json.keys()))
    log.info("phases count: %s", len(roadmap.roadmap_json.get("phases", [])))

    return RoadmapResponse(**roadmap.roadmap_json)