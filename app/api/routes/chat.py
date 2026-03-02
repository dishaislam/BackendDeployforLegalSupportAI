import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.db.session import get_db
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request schemas ───────────────────────────────────────────────────────────

class CreateChatRequest(BaseModel):
    title: Optional[str] = "New Consultation"


class SendMessageRequest(BaseModel):
    chat_id: uuid.UUID
    query: str

    @property
    def query_stripped(self) -> str:
        return self.query.strip()


class RenameChatRequest(BaseModel):
    title: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/create", status_code=201)
async def create_chat(
    request: CreateChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Create a new chat session."""
    service = ChatService(db)
    chat = await service.create_chat(
        user_id=user_id,
        title=request.title or "New Consultation",
    )
    return {
        "chat_id": str(chat.chat_id),
        "title": chat.title,
        "created_at": chat.created_at.isoformat(),
    }


@router.post("/send")
async def send_message(
    request: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):

    if not request.query_stripped:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query cannot be empty.",
        )

    service = ChatService(db)
    return await service.send_message(
        chat_id=request.chat_id,
        user_id=user_id,
        query=request.query_stripped,
    )


@router.get("/list")
async def list_chats(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """List all chat sessions for the current user with message previews."""
    service = ChatService(db)
    chats = await service.list_user_chats(user_id=user_id)
    return {"chats": chats, "total": len(chats)}


@router.get("/{chat_id}/history")
async def get_history(
    chat_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Retrieve all messages for a specific chat session."""
    service = ChatService(db)
    messages = await service.get_chat_history(chat_id, user_id)
    return {"chat_id": str(chat_id), "messages": messages, "total": len(messages)}


@router.patch("/{chat_id}/rename")
async def rename_chat(
    chat_id: uuid.UUID,
    request: RenameChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Rename a chat session."""
    service = ChatService(db)
    await service.rename_chat(chat_id, user_id, request.title)
    return {"chat_id": str(chat_id), "title": request.title}


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Delete a chat session and all its messages."""
    service = ChatService(db)
    await service.delete_chat(chat_id, user_id)
    return {"deleted": True, "chat_id": str(chat_id)}
