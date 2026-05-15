from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from sqlalchemy import text

from app.database import async_session_maker

log = logging.getLogger(__name__)

STALE_LOCK_MINUTES = 5


async def acquire_workspace_lock(workspace_id: int, chat_id: int) -> None:
    # Auto-releases stale locks older than STALE_LOCK_MINUTES.
    async with async_session_maker() as session:
        # First, release any stale lock
        await session.execute(text("""
            UPDATE workspaces
            SET generating_chat_id = NULL, generating_since = NULL
            WHERE id = :ws_id
              AND generating_chat_id IS NOT NULL
              AND generating_since < NOW() - INTERVAL ':minutes minutes'
        """), {"ws_id": workspace_id, "minutes": STALE_LOCK_MINUTES})

        # Try to acquire
        result = await session.execute(text("""
            UPDATE workspaces
            SET generating_chat_id = :chat_id, generating_since = NOW()
            WHERE id = :ws_id AND generating_chat_id IS NULL
        """), {"ws_id": workspace_id, "chat_id": chat_id})

        if result.rowcount == 0:
            # Lock is taken — find out by whom
            row = (await session.execute(text("""
                SELECT generating_chat_id, generating_since
                FROM workspaces WHERE id = :ws_id
            """), {"ws_id": workspace_id})).fetchone()

            await session.commit()
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "workspace_locked",
                    "message": "Another chat is currently generating a response.",
                    "generating_chat_id": row.generating_chat_id if row else None,
                    "generating_since": row.generating_since.isoformat() if row and row.generating_since else None,
                    "hint": "Wait for the current generation to complete, then try again.",
                }
            )

        await session.commit()
        log.info("Lock acquired: workspace=%d chat=%d", workspace_id, chat_id)


async def release_workspace_lock(workspace_id: int, chat_id: int) -> None:
    # Release the workspace generation lock.
    # Only releases if this chat_id actually holds the lock (prevents accidental release).
    async with async_session_maker() as session:
        await session.execute(text("""
            UPDATE workspaces
            SET generating_chat_id = NULL, generating_since = NULL
            WHERE id = :ws_id AND generating_chat_id = :chat_id
        """), {"ws_id": workspace_id, "chat_id": chat_id})
        await session.commit()
        log.info("Lock released: workspace=%d chat=%d", workspace_id, chat_id)


async def get_lock_status(workspace_id: int) -> dict:
    async with async_session_maker() as session:
        row = (await session.execute(text("""
            SELECT generating_chat_id, generating_since
            FROM workspaces WHERE id = :ws_id
        """), {"ws_id": workspace_id})).fetchone()

    if not row:
        return {"is_locked": False, "generating_chat_id": None, "generating_since": None}

    return {
        "workspace_id": workspace_id,
        "is_locked": row.generating_chat_id is not None,
        "generating_chat_id": row.generating_chat_id,
        "generating_since": row.generating_since.isoformat() if row.generating_since else None,
    }