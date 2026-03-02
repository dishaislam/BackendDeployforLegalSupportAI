import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserModel

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[UserModel]:
        result = await self.db.execute(
            select(UserModel).where(UserModel.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[UserModel]:
        result = await self.db.execute(
            select(UserModel).where(UserModel.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        hashed_password: str,
        full_name: Optional[str] = None,
    ) -> UserModel:
        user = UserModel(
            user_id=uuid.uuid4(),
            email=email.lower().strip(),
            hashed_password=hashed_password,
            full_name=full_name,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        logger.info(f"Created user: {user.email}")
        return user

    async def email_exists(self, email: str) -> bool:
        user = await self.get_by_email(email)
        return user is not None
