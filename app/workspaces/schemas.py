from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str
    description: str | None = None


class WorkspaceRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=500)


class WorkspaceResponse(BaseModel):
    id: int
    user_id:  int
    name: str
    description: str | None
    generating_chat_id: int | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}