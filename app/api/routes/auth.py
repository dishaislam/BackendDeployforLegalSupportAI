import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.db.session import get_db
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)
router = APIRouter()


#  Request schemas 

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# Endpoints 

@router.post("/signup", status_code=201)
async def signup(request: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Register a new account and receive a JWT access token."""
    service = AuthService(db)
    return await service.register(
        email=str(request.email),
        password=request.password,
        full_name=request.full_name,
    )


@router.post("/login")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate and receive a JWT access token."""
    service = AuthService(db)
    return await service.login(
        email=str(request.email),
        password=request.password,
    )


@router.get("/me")
async def get_profile(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Return the profile of the currently authenticated user."""
    service = AuthService(db)
    user = await service.get_profile(user_id)
    return {
        "id": str(user.user_id),
        "email": user.email,
        "full_name": user.full_name,
        "created_at": user.created_at.isoformat(),
    }
