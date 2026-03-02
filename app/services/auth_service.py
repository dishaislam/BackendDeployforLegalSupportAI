import logging
import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import UserModel
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.user_repo = UserRepository(db)

    # Firebase handles registration, backend only stores profile if needed
    async def register(
        self,
        email: str,
        password: str,
        full_name: Optional[str] = None,
    ) -> dict:

        if await self.user_repo.email_exists(email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        hashed = hash_password(password)

        user = await self.user_repo.create(
            email=email,
            hashed_password=hashed,
            full_name=full_name,
        )

        logger.info(f"User profile created: {user.email}")

        return {
            "message": "User profile created successfully",
            "user": {
                "id": str(user.user_id),
                "email": user.email,
                "full_name": user.full_name,
            },
        }

    # Firebase handles login, backend does NOT generate token
    async def login(self, email: str, password: str) -> dict:

        user = await self.user_repo.get_by_email(email)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        # Optional check (only if using hybrid auth)
        if user.hashed_password != "firebase":
            if not verify_password(password, user.hashed_password):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials.",
                )

        logger.info(f"User authenticated: {user.email}")

        return {
            "message": "Authentication successful (Firebase handled token)",
            "user": {
                "id": str(user.user_id),
                "email": user.email,
                "full_name": user.full_name,
            },
        }

    async def get_profile(self, user_id: str) -> UserModel:

        user = await self.user_repo.get_by_id(uuid.UUID(user_id))

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        return user