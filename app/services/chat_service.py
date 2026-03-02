import logging
import uuid
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatModel
from app.models.message import MessageModel
from app.repositories.chat_repository import ChatRepository
from app.repositories.message_repository import MessageRepository
from app.services.agent_service import classify_intent, generate_legal_answer, handle_general
from app.services.retriever_service import retrieve

logger = logging.getLogger(__name__)


def _format_context(retrieval_results: dict) -> str:
    parts = []
    for hit in retrieval_results.get("results", []):
        text = hit.get("text", "")
        citation = hit.get("metadata", {}).get("citation", "Unknown Source")
        parts.append(f"SOURCE: {citation}\nCONTENT: {text}")
    return "\n\n---\n\n".join(parts)


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.chat_repo = ChatRepository(db)
        self.message_repo = MessageRepository(db)

    async def create_chat(self, user_id: uuid.UUID, title: str = "New Consultation") -> ChatModel:
        return await self.chat_repo.create(user_id, title=title)

    async def list_user_chats(self, user_id: uuid.UUID) -> List[dict]:
        chats = await self.chat_repo.get_user_chats(user_id)
        result = []
        for chat in chats:
            messages = await self.message_repo.get_by_chat(chat.chat_id)
            last_msg = messages[-1] if messages else None
            result.append({
                "chat_id": str(chat.chat_id),
                "title": chat.title,
                "preview": (last_msg.content[:80] + "…") if last_msg and len(last_msg.content) > 80 else (last_msg.content if last_msg else "No messages yet"),
                "message_count": len(messages),
                "created_at": chat.created_at.isoformat(),
                "updated_at": chat.updated_at.isoformat(),
            })
        return result

    async def get_chat_history(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> List[dict]:
        if not await self.chat_repo.belongs_to_user(chat_id, user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this chat.",
            )
        messages = await self.message_repo.get_by_chat(chat_id)
        return [
            {
                "id": str(msg.message_id),
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ]

    async def send_message(
        self,
        chat_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
    ) -> dict:
        # Ownership check
        if not await self.chat_repo.belongs_to_user(chat_id, user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this chat.",
            )

        # Persist user message
        await self.message_repo.create(chat_id=chat_id, role="user", content=query)
        logger.info(f"[chat={chat_id}] User query: {query[:80]}...")

        # Classify intent
        intent = classify_intent(query)
        logger.info(f"[chat={chat_id}] Intent classified as: {intent}")

        # Generate response
        if intent == "GREETING":
            answer = handle_general(query)
        elif intent == "LEGAL":
            retrieval = retrieve(query)
            if retrieval["result_count"] > 0:
                context = _format_context(retrieval)
                answer = generate_legal_answer(context, query)
            else:
                answer = (
                    "I apologize, but I do not have sufficient legal information "
                    "in the database to answer this question."
                )
        else:
            answer = handle_general(query)

        # Persist assistant message
        await self.message_repo.create(chat_id=chat_id, role="assistant", content=answer)

        # Auto-title the chat on first message
        await self._auto_title(chat_id, query)

        logger.info(f"[chat={chat_id}] Response generated ({len(answer)} chars)")
        return {"chat_id": str(chat_id), "answer": answer, "intent": intent}

    async def rename_chat(self, chat_id: uuid.UUID, user_id: uuid.UUID, new_title: str) -> None:
        if not await self.chat_repo.belongs_to_user(chat_id, user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this chat.",
            )
        await self.chat_repo.rename(chat_id, new_title)

    async def delete_chat(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> None:
        if not await self.chat_repo.belongs_to_user(chat_id, user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this chat.",
            )
        await self.chat_repo.delete(chat_id)

    async def _auto_title(self, chat_id: uuid.UUID, first_query: str) -> None:
        title = first_query.strip()[:50]
        if len(first_query.strip()) > 50:
            title = title.rsplit(" ", 1)[0] + "…"
        await self.chat_repo.update_title_if_default(chat_id, title)
