import logging
import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import MessageModel

logger = logging.getLogger(__name__)


class MessageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        chat_id: uuid.UUID,
        role: str,
        content: str,
    ) -> MessageModel:
        message = MessageModel(chat_id=chat_id, role=role, content=content)
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_by_chat(self, chat_id: uuid.UUID) -> List[MessageModel]:
        result = await self.db.execute(
            select(MessageModel)
            .where(MessageModel.chat_id == chat_id)
            .order_by(MessageModel.created_at.asc())
        )
        return list(result.scalars().all())
