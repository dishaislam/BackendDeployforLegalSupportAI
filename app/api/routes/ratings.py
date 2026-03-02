import logging
from typing import Optional
 
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
 
from app.core.security import get_current_user_id
from app.db.session import get_db
from app.models.rating import RatingModel
 
logger = logging.getLogger(__name__)
router = APIRouter()
 
 
class RatingRequest(BaseModel):
    stars: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
 
 
@router.post("", status_code=201)
async def submit_rating(
    body: RatingRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    rating = RatingModel(user_id=user_id, stars=body.stars, comment=body.comment)
    db.add(rating)
    await db.commit()
    logger.info(f"Rating submitted: user={user_id} stars={body.stars}")
    return {"submitted": True, "stars": body.stars}