# Add to imports
from fastapi import APIRouter, Depends, Query, HTTPException

from app.analysis.analysis_service import create_analysis
from app.analysis.schemas import AnalysisResponse, SituationInput
from app.auth.utils import get_optional_user, get_chat_permission
from app.chats.dao import ChatDAO
from app.chats.router import _get_chat_or_404, generation_lock
from app.messages.dao import MessageDAO
from app.messages.schemas import MessageResponse
from app.users.models import User

router = APIRouter(prefix="/api", tags=["Auth"])

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

    # 1. Persist user message immediately — visible in history before AI responds
    await MessageDAO.save_user_message(
        chat_id=chat_id,
        content=body.situation_description,
        payload=body.model_dump(),  # full SituationInput stored
    )

    async with generation_lock(workspace_id, chat_id):
        # 2. Run the full RAG + analysis pipeline
        response = await create_analysis(workspace_id, body)

        # 3. Persist assistant response
        # content = executive summary shown in chat bubble
        # payload = full AnalysisResponse for the detail panel
        await MessageDAO.save_assistant_message(
            chat_id=chat_id,
            content=_build_assistant_summary(response),
            payload=response.model_dump(),
            analysis_id=response.analysis_id,
        )
        # 4. One increment covers the full exchange (user + assistant = 1 round)
        await ChatDAO.increment_message_count(chat_id)

    return response


def _build_assistant_summary(response: AnalysisResponse) -> str:
    # Single readable string stored as the chat bubble text
    # Frontend uses analysis_id to load the full detail panel

    lines = [
        f"**{response.detected_crisis_type.upper()} · {response.urgency_level} urgency**",
        "",
        response.crisis_summary,
    ]
    if response.missing_information:
        lines += ["", "WARNING: Missing information:"]
        lines += [f"  – {item}" for item in response.missing_information[:3]]
    return "\n".join(lines)


@router.get(
    "/workspaces/{workspace_id}/chats/{chat_id}/messages",
    response_model=list[MessageResponse],
)
async def get_chat_history(
    workspace_id: int,
    chat_id:      int,
    current_user: User | None = Depends(get_optional_user),
    token:        str | None  = Query(None),
) -> list[MessageResponse]:
    # Both owner and share link readers can view history
    permission = await get_chat_permission(chat_id, current_user, token)
    if permission == "none":
        raise HTTPException(403, "Access denied")

    await _get_chat_or_404(chat_id, workspace_id)
    messages = await MessageDAO.get_chat_history(chat_id)
    return [MessageResponse.model_validate(m) for m in messages]