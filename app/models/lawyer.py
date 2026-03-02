import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, String, Float, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.db.base import Base


class LawyerModel(Base):
    __tablename__ = "lawyers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False, index=True)
    specialization = Column(String(500), nullable=False)
    district = Column(String(100), nullable=False, index=True)
    bar_association = Column(String(200), nullable=False)
    experience = Column(Integer, default=0)
    rating = Column(Float, default=4.0)
    budget = Column(String(100))
    languages = Column(ARRAY(String), default=["Bangla"])
    phone = Column(String(30))
    email = Column(String(200))
    avatar_color = Column(String(10), default="#1a8a3c")
    is_active = Column(Integer, default=1)  # 1 = active, 0 = inactive
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "specialization": self.specialization,
            "district": self.district,
            "bar_association": self.bar_association,
            "experience": self.experience,
            "rating": self.rating,
            "budget": self.budget,
            "languages": self.languages or ["Bangla"],
            "phone": self.phone,
            "email": self.email,
            "avatar_color": self.avatar_color,
        }
