from __future__ import annotations
from sqlalchemy import select
from app.dao.base import BaseDAO
from app.database import async_session_maker
from app.messages.models import Message


class MessageDAO(BaseDAO):
    model = Message

    @staticmethod
    async def get_chat_history(chat_id: int) -> list[Message]:
        async with async_session_maker() as db:
            result = await db.execute(
                select(Message)
                .where(Message.chat_id == chat_id)
                .order_by(Message.created_at.asc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def save_user_message(
        chat_id: int,
        content: str,
        payload: dict,
    ) -> Message:
        async with async_session_maker() as db:
            msg = Message(
                chat_id=chat_id,
                role="user",
                content=content,
                payload=payload,
            )
            db.add(msg)
            await db.commit()
            await db.refresh(msg)
        return msg

    @staticmethod
    async def save_assistant_message(
        chat_id:     int,
        content:     str,
        payload:     dict,
        analysis_id: str | None = None,
    ) -> Message:
        async with async_session_maker() as db:
            msg = Message(
                chat_id=chat_id,
                role="assistant",
                content=content,
                payload=payload,
                analysis_id=analysis_id,
            )
            db.add(msg)
            await db.commit()
            await db.refresh(msg)
        return msg

    @staticmethod
    async def delete_last_user_message(chat_id: int) -> None:
        async with async_session_maker() as db:
            result = await db.execute(
                select(Message)
                .where(Message.chat_id == chat_id, Message.role == "user")
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            msg = result.scalar_one_or_none()
            if msg:
                await db.delete(msg)
                await db.commit()

    @classmethod
    async def find_last_analysis_message(cls, chat_id: int):
        """Return the last assistant message with a non-null analysis_id."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Message)
                .where(Message.chat_id == chat_id)
                .where(Message.role == "assistant")
                .where(Message.analysis_id.isnot(None))
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()