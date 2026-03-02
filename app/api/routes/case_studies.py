import uuid
import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.security import get_current_user_id
from app.db.session import get_db
from app.services.case_study_service import CaseStudyService

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateCaseRequest(BaseModel):
    title: str
    description: Optional[str] = ""


class UpdateCaseRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class ChatRequest(BaseModel):
    query: str


# ── Cases ─────────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_case(req: CreateCaseRequest, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = CaseStudyService(db)
    return await svc.create_case(user_id, req.title, req.description or "")


@router.get("")
async def list_cases(db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = CaseStudyService(db)
    cases = await svc.list_cases(user_id)
    return {"cases": cases}


@router.get("/practice-areas")
async def get_practice_areas(db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = CaseStudyService(db)
    return {"areas": await svc.get_practice_area_stats()}


@router.get("/{case_id}")
async def get_case(case_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = CaseStudyService(db)
    return await svc.get_case(case_id, user_id)


@router.patch("/{case_id}")
async def update_case(case_id: uuid.UUID, req: UpdateCaseRequest, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = CaseStudyService(db)
    return await svc.update_case(case_id, user_id, req.title, req.description, req.status)


@router.delete("/{case_id}", status_code=204)
async def delete_case(case_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = CaseStudyService(db)
    await svc.delete_case(case_id, user_id)


# ── Documents ─────────────────────────────────────────────────────────────────

@router.post("/{case_id}/documents", status_code=201)
async def upload_document(case_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 25MB limit.")
    svc = CaseStudyService(db)
    return await svc.upload_document(case_id, user_id, content, file.filename or "document")


@router.delete("/{case_id}/documents/{doc_id}", status_code=204)
async def delete_document(case_id: uuid.UUID, doc_id: uuid.UUID, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = CaseStudyService(db)
    await svc.delete_document(case_id, doc_id, user_id)


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.post("/{case_id}/chat")
async def case_chat(case_id: uuid.UUID, req: ChatRequest, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = CaseStudyService(db)
    return await svc.send_message(case_id, user_id, req.query)
