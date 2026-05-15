from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from sqlalchemy import text

from app.database import async_session_maker
from app.workspaces.dao import WorkspaceDAO

log = logging.getLogger(__name__)

STALE_LOCK_MINUTES = 5


async def acquire_workspace_lock(workspace_id: int, chat_id: int) -> None:
    await WorkspaceDAO.release_stale_lock(workspace_id)
    acquired = await WorkspaceDAO.acquire_generation_lock(workspace_id, chat_id)
    if not acquired:
        lock = await WorkspaceDAO.get_lock_status(workspace_id)
        raise HTTPException(status_code=409, detail={
            "error":              "workspace_locked",
            "generating_chat_id": lock["generating_chat_id"],
            "generating_since":   lock["generating_since"],
        })


async def release_workspace_lock(workspace_id: int, chat_id: int) -> None:
    await WorkspaceDAO.release_generation_lock(workspace_id, chat_id)


async def get_lock_status(workspace_id: int) -> dict:
    return await WorkspaceDAO.get_lock_status(workspace_id)