import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.lawyer import LawyerModel

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Pydantic schemas ──────────────────────────────────────────────────────────

class LawyerCreate(BaseModel):
    name: str
    specialization: str
    district: str
    bar_association: str
    experience: int = 0
    rating: float = 4.0
    budget: str = ""
    languages: list[str] = ["Bangla"]
    phone: str = ""
    email: str = ""
    avatar_color: str = "#1a8a3c"


class LawyerUpdate(BaseModel):
    name: Optional[str] = None
    specialization: Optional[str] = None
    district: Optional[str] = None
    bar_association: Optional[str] = None
    experience: Optional[int] = None
    rating: Optional[float] = None
    budget: Optional[str] = None
    languages: Optional[list[str]] = None
    phone: Optional[str] = None
    email: Optional[str] = None


# Seed data for initial population
SEED_LAWYERS = [
    {"name": "Adv. Fatima Begum", "specialization": "Family Law, Divorce", "district": "Dhaka", "bar_association": "Dhaka Bar", "experience": 12, "rating": 4.8, "budget": "৳5,000–৳15,000", "languages": ["Bangla", "English"], "avatar_color": "#8E44AD"},
    {"name": "Barrister Kamal Hossain Jr.", "specialization": "Land Dispute, Civil Law", "district": "Chittagong", "bar_association": "Chittagong Bar", "experience": 8, "rating": 4.6, "budget": "৳10,000–৳30,000", "languages": ["Bangla", "English"], "avatar_color": "#2980B9"},
    {"name": "Adv. Nusrat Jahan", "specialization": "Cyber Crime, Criminal Law", "district": "Dhaka", "bar_association": "Supreme Court Bar", "experience": 6, "rating": 4.7, "budget": "৳8,000–৳25,000", "languages": ["Bangla", "English"], "avatar_color": "#16A085"},
    {"name": "Adv. Mohammad Rafiq", "specialization": "Commercial, Cheque Bounce", "district": "Sylhet", "bar_association": "Sylhet Bar", "experience": 15, "rating": 4.9, "budget": "৳3,000–৳10,000", "languages": ["Bangla"], "avatar_color": "#E67E22"},
    {"name": "Adv. Saima Islam", "specialization": "Domestic Violence, Women's Rights", "district": "Dhaka", "bar_association": "Dhaka Bar", "experience": 9, "rating": 4.8, "budget": "৳2,000–৳8,000", "languages": ["Bangla", "English", "Arabic"], "avatar_color": "#C0392B"},
    {"name": "Adv. Tarekul Islam", "specialization": "Land, Property, Civil", "district": "Rajshahi", "bar_association": "Rajshahi Bar", "experience": 20, "rating": 4.7, "budget": "৳5,000–৳20,000", "languages": ["Bangla"], "avatar_color": "#27AE60"},
    {"name": "Adv. Shaheen Akhter", "specialization": "Family Law, Shariah", "district": "Dhaka", "bar_association": "Supreme Court Bar", "experience": 14, "rating": 4.9, "budget": "৳6,000–৳18,000", "languages": ["Bangla", "English", "Arabic"], "avatar_color": "#7B5EA7"},
    {"name": "Adv. Rezaul Karim", "specialization": "Criminal, NI Act", "district": "Khulna", "bar_association": "Khulna Bar", "experience": 11, "rating": 4.5, "budget": "৳4,000–৳12,000", "languages": ["Bangla"], "avatar_color": "#34495E"},
    {"name": "Adv. Rania Chowdhury", "specialization": "Corporate Law, Contracts", "district": "Dhaka", "bar_association": "Supreme Court Bar", "experience": 7, "rating": 4.6, "budget": "৳15,000–৳50,000", "languages": ["Bangla", "English"], "avatar_color": "#1A6B8A"},
    {"name": "Adv. Abdul Mannan", "specialization": "Immigration, Labour Law", "district": "Chittagong", "bar_association": "Chittagong Bar", "experience": 18, "rating": 4.8, "budget": "৳5,000–৳18,000", "languages": ["Bangla", "English", "Arabic"], "avatar_color": "#2C3E50"},
]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def get_lawyers(
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    specialization: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """Get lawyers with optional filtering. Seeds DB if empty."""
    try:
        # Check if any lawyers exist; seed if empty
        count_result = await db.execute(select(func.count(LawyerModel.id)))
        count = count_result.scalar()
        if count == 0:
            for data in SEED_LAWYERS:
                db.add(LawyerModel(**data))
            await db.commit()
            logger.info("Seeded lawyer database with initial data.")

        query = select(LawyerModel).where(LawyerModel.is_active == 1)

        if search:
            query = query.where(
                or_(
                    LawyerModel.name.ilike(f"%{search}%"),
                    LawyerModel.specialization.ilike(f"%{search}%"),
                )
            )
        if district and district != "All":
            query = query.where(LawyerModel.district == district)
        if specialization and specialization != "All":
            query = query.where(LawyerModel.specialization.ilike(f"%{specialization}%"))

        query = query.offset(skip).limit(limit).order_by(LawyerModel.rating.desc())
        result = await db.execute(query)
        lawyers = result.scalars().all()

        return {"lawyers": [l.to_dict() for l in lawyers], "total": len(lawyers)}
    except Exception as e:
        logger.error(f"get_lawyers error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", status_code=201)
async def create_lawyer(
    data: LawyerCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a new lawyer to the directory."""
    lawyer = LawyerModel(**data.model_dump())
    db.add(lawyer)
    await db.commit()
    await db.refresh(lawyer)
    return {"lawyer": lawyer.to_dict(), "message": "Lawyer added successfully"}


@router.get("/{lawyer_id}")
async def get_lawyer(lawyer_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single lawyer by ID."""
    result = await db.execute(select(LawyerModel).where(LawyerModel.id == lawyer_id))
    lawyer = result.scalar_one_or_none()
    if not lawyer:
        raise HTTPException(status_code=404, detail="Lawyer not found")
    return lawyer.to_dict()


@router.patch("/{lawyer_id}")
async def update_lawyer(
    lawyer_id: str,
    data: LawyerUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a lawyer's information."""
    result = await db.execute(select(LawyerModel).where(LawyerModel.id == lawyer_id))
    lawyer = result.scalar_one_or_none()
    if not lawyer:
        raise HTTPException(status_code=404, detail="Lawyer not found")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(lawyer, field, value)

    await db.commit()
    await db.refresh(lawyer)
    return {"lawyer": lawyer.to_dict(), "message": "Updated successfully"}


@router.delete("/{lawyer_id}")
async def delete_lawyer(lawyer_id: str, db: AsyncSession = Depends(get_db)):
    """Soft delete a lawyer (mark as inactive)."""
    result = await db.execute(select(LawyerModel).where(LawyerModel.id == lawyer_id))
    lawyer = result.scalar_one_or_none()
    if not lawyer:
        raise HTTPException(status_code=404, detail="Lawyer not found")
    lawyer.is_active = 0
    await db.commit()
    return {"deleted": True, "id": lawyer_id}
