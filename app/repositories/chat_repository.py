import logging
import uuid
from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatModel

logger = logging.getLogger(__name__)


class ChatRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: uuid.UUID, title: str = "New Consultation") -> ChatModel:
        chat = ChatModel(user_id=user_id, title=title)
        self.db.add(chat)
        await self.db.commit()
        await self.db.refresh(chat)
        logger.debug(f"Created chat {chat.chat_id} for user {user_id}")
        return chat

    async def get_by_id(self, chat_id: uuid.UUID) -> Optional[ChatModel]:
        result = await self.db.execute(
            select(ChatModel).where(ChatModel.chat_id == chat_id)
        )
        return result.scalar_one_or_none()

    async def get_user_chats(self, user_id: uuid.UUID) -> List[ChatModel]:
        result = await self.db.execute(
            select(ChatModel)
            .where(ChatModel.user_id == user_id)
            .order_by(ChatModel.updated_at.desc())
        )
        return list(result.scalars().all())

    async def rename(self, chat_id: uuid.UUID, new_title: str) -> None:
        await self.db.execute(
            update(ChatModel)
            .where(ChatModel.chat_id == chat_id)
            .values(title=new_title)
        )
        await self.db.commit()

    async def update_title_if_default(self, chat_id: uuid.UUID, new_title: str) -> None:
        """Auto-set title only while still using the placeholder."""
        await self.db.execute(
            update(ChatModel)
            .where(
                ChatModel.chat_id == chat_id,
                ChatModel.title == "New Consultation",
            )
            .values(title=new_title)
        )
        await self.db.commit()

    async def delete(self, chat_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(ChatModel).where(ChatModel.chat_id == chat_id)
        )
        await self.db.commit()
        logger.info(f"Deleted chat {chat_id}")

    async def belongs_to_user(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        chat = await self.get_by_id(chat_id)
        return chat is not None and chat.user_id == user_id
