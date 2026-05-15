from app.dao.base import BaseDAO
from app.database import async_session_maker
import logging

from sqlalchemy import text

from app.workspaces.models import Workspace

log = logging.getLogger(__name__)

STALE_LOCK_MINUTES = 3


class WorkspaceDAO(BaseDAO):
    model = Workspace

    @classmethod
    async def acquire_generation_lock(cls, workspace_id: int, chat_id: int) -> bool:
        async with async_session_maker() as session:
            await session.execute(
                text(
                    """
                    UPDATE workspaces
                    SET generating_chat_id = NULL,
                    generating_since   = NULL
                    WHERE id = :ws_id
                    AND generating_chat_id IS NOT NULL
                    AND generating_since < NOW() - (:mins * INTERVAL '1 minute')
                    """
                ), {"ws_id": workspace_id, "mins": STALE_LOCK_MINUTES})

            result = await session.execute(
                text(
                    """
                    UPDATE workspaces
                    SET generating_chat_id = :chat_id,
                        generating_since   = NOW()
                    WHERE id = :ws_id
                      AND generating_chat_id IS NULL
                    """
                ), {"ws_id": workspace_id, "chat_id": chat_id})

            await session.commit()
            acquired = result.rowcount == 1

        if acquired:
            log.info("Lock acquired: workspace=%d chat=%d", workspace_id, chat_id)
        return acquired

    @classmethod
    async def release_generation_lock(cls, workspace_id: int, chat_id: int) -> None:
        async with async_session_maker() as session:
            await session.execute(
                text(
                    """
                    UPDATE workspaces
                    SET generating_chat_id = NULL,
                    generating_since   = NULL
                    WHERE id = :ws_id
                    AND generating_chat_id = :chat_id
                    """
                ), {"ws_id": workspace_id, "chat_id": chat_id})
            await session.commit()
        log.info("Lock released: workspace=%d chat=%d", workspace_id, chat_id)

    @classmethod
    async def get_lock_status(cls, workspace_id: int) -> dict:
        async with async_session_maker() as session:
            row = (await session.execute(
                text(
                    """
                    SELECT generating_chat_id, generating_since
                    FROM workspaces
                    WHERE id = :ws_id
                    """
                ), {"ws_id": workspace_id})).fetchone()

        if not row:
            return {"workspace_id": workspace_id, "is_locked": False,
                    "generating_chat_id": None, "generating_since": None}

        return {
            "workspace_id": workspace_id,
            "is_locked": row.generating_chat_id is not None,
            "generating_chat_id": row.generating_chat_id,
            "generating_since": row.generating_since.isoformat()
            if row.generating_since else None,
        }