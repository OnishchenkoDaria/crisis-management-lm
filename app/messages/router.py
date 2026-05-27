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


@router.get(
    "/workspaces/{workspace_id}/chats/{chat_id}/messages",
    response_model=list[MessageResponse],
)
async def get_chat_history(
    workspace_id: int,
    chat_id: int,
    current_user: User | None = Depends(get_optional_user),
    token: str | None = Query(None),
) -> list[MessageResponse]:
    permission = await get_chat_permission(chat_id, current_user, token)
    if permission == "none":
        raise HTTPException(403, "Access denied")

    await _get_chat_or_404(chat_id, workspace_id)
    messages = await MessageDAO.get_chat_history(chat_id)
    return [MessageResponse.model_validate(m) for m in messages]