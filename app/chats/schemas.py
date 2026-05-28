from __future__ import annotations
from typing import Literal
from datetime import datetime
from pydantic import BaseModel, Field


ChatStatus = Literal["empty", "in_progress", "generating", "finished"]


class ChatCreate(BaseModel):
    title: str = Field(default="New Chat", max_length=200)

class ChatRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)

class ChatResponse(BaseModel):
    id: int
    workspace_id: int
    title: str
    status: ChatStatus
    message_count: int
    created_at: datetime
    updated_at: datetime

    # Derived — whether this chat can receive new messages
    is_locked: bool   # True when status == "generating"
    can_send: bool   # True when status in (empty, in_progress)

class WorkspaceLockStatus(BaseModel):
    workspace_id: int
    is_locked: bool
    generating_chat_id: int | None   # which chat holds the lock
    generating_since: datetime | None


from pydantic import BaseModel
from datetime import datetime

class ShareLinkResponse(BaseModel):
    id:         int
    chat_id:    int
    token:      str
    expires_at: datetime | None
    is_active:  bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ClarifyRequest(BaseModel):
    analysis_id: str
    answers:     dict[str, str]

class RoadmapGenerateRequest(BaseModel):
    analysis_id: str