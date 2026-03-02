import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class ChatModel(Base):
    __tablename__ = "chats"

    # UUID is correct here
    chat_id = Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)

    # MUST be String to match Firebase UID
    user_id = Column(
        String,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = Column(
        String(200),
        default="New Consultation",
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    messages = relationship(
        "MessageModel",
        back_populates="chat",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self):
        return f"<Chat id={self.chat_id} title={self.title}>"