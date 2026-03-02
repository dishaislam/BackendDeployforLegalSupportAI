import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class UserModel(Base):
    """
    Stores locally-authenticated users.
    Passwords are bcrypt-hashed; authentication is handled via JWT.
    """

    __tablename__ = "users"

    user_id = Column(String, primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.user_id} email={self.email}>"
