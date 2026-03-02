import json
import logging
import os
from typing import Optional

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from sqlalchemy import select
from app.models.user import UserModel as User

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# ── Firebase init ─────────────────────────────────────────────────────────────

def _init_firebase():
    if firebase_admin._apps:
        return

    # Try env var first (JSON string for cloud deployment)
    sa_env = os.getenv("FIREBASE_SERVICE_ACCOUNT", "").strip()
    if sa_env:
        try:
            sa_dict = json.loads(sa_env)
            cred = credentials.Certificate(sa_dict)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialised from env var")
            return
        except Exception as e:
            logger.error(f"Failed to init Firebase from env var: {e}")
            raise

    # Fall back to file
    path = "/app/service_account.json"
    if not os.path.exists(path):
        raise RuntimeError(f"Firebase service account not found. Set FIREBASE_SERVICE_ACCOUNT env var.")

    cred = credentials.Certificate(path)
    firebase_admin.initialize_app(cred)
    logger.info("Firebase Admin initialised from file")


_init_firebase()

# ── Password utilities ────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# ── Firebase token verification ───────────────────────────────────────────────

async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    Verifies the Firebase ID token and returns the Firebase UID.
    Auto-creates a Postgres user record on first login.
    """
    try:
        decoded = firebase_auth.verify_id_token(credentials.credentials)
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token has expired. Please sign in again.")
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token.")
    except Exception as e:
        logger.error(f"Firebase token verification failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Could not verify credentials.")

    uid: Optional[str] = decoded.get("uid")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token missing user identity.")

    # Auto-create user in Postgres on first login
    await _ensure_user_exists(uid, decoded, db)

    return uid


async def _ensure_user_exists(uid: str, decoded: dict, db: AsyncSession):
    """Creates a Postgres user record the first time a Firebase user hits the API."""

    result = await db.execute(select(User).where(User.user_id == uid))
    if result.scalar_one_or_none():
        return  # already exists

    email = decoded.get("email", "")
    name = decoded.get("name", email.split("@")[0] if email else "User")

    new_user = User(
        user_id=uid,
        email=email,
        full_name=name,
        hashed_password="firebase",  # not used — Firebase handles auth
    )
    db.add(new_user)
    await db.commit()
    logger.info(f"Auto-created Postgres user for Firebase UID: {uid}")