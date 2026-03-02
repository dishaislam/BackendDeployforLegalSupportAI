import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
 
 
class RatingModel(Base):
    __tablename__ = "ratings"
 
    rating_id  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(String, nullable=False, index=True)
    stars      = Column(Integer, nullable=False)  # 1–5
    comment    = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
 