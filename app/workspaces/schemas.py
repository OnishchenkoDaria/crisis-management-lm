from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name:        str      = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=500)


class WorkspaceRename(BaseModel):
    name:        str      = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=500)


class WorkspaceResponse(BaseModel):
    id:          int
    user_id:     int
    name:        str
    description: str | None
    created_at:  str | None = None   # from Base timestamps
    updated_at:  str | None = None

    model_config = {"from_attributes": True}