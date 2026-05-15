from app.dao.base import BaseDAO
from app.database import async_session_maker
import logging

from sqlalchemy import select, text

from app.chats.model import Chat

log = logging.getLogger(__name__)


class ChatDAO(BaseDAO):
    model = Chat

    @classmethod
    async def find_by_workspace(cls, workspace_id: int) -> list:
        async with async_session_maker() as session:
            result = await session.execute(
                select(cls.model)
                .filter_by(workspace_id=workspace_id)
                .order_by(cls.model.updated_at.desc())
            )
            return result.scalars().all()

    @classmethod
    async def find_by_workspace_and_id(cls, workspace_id: int, chat_id: int):
        async with async_session_maker() as session:
            result = await session.execute(
                select(cls.model).filter_by(id=chat_id, workspace_id=workspace_id)
            )
            return result.scalar_one_or_none()

    @classmethod
    async def set_status(cls, chat_id: int, status: str) -> int:
        return await cls.update({"id": chat_id}, status=status)

    @classmethod
    async def set_generating(cls, chat_id: int) -> int:
        return await cls.update({"id": chat_id}, status="generating")

    @classmethod
    async def set_in_progress(cls, chat_id: int) -> int:
        return await cls.update({"id": chat_id}, status="in_progress")

    @classmethod
    async def set_finished(cls, chat_id: int) -> int:
        return await cls.update({"id": chat_id}, status="finished")

    @classmethod
    async def increment_message_count(cls, chat_id: int) -> None:
        async with async_session_maker() as session:
            await session.execute(text(
                "UPDATE chats SET message_count = message_count + 1 WHERE id = :chat_id"
            ), {"chat_id": chat_id})
            await session.commit()

    @classmethod
    async def count_by_status(cls, workspace_id: int) -> dict[str, int]:
        async with async_session_maker() as session:
            rows = (await session.execute(
                text(
                    """
                    SELECT status, COUNT(*) AS cnt
                    FROM chats
                    WHERE workspace_id = :ws_id
                    GROUP BY status
                    """
                ), {"ws_id": workspace_id})).fetchall()
        return {row.status: row.cnt for row in rows}