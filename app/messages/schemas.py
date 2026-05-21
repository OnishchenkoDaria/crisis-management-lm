from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class MessageResponse(BaseModel):
    id: int
    chat_id: int
    role: str
    content: str
    analysis_id: str | None
    payload: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}