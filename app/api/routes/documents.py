import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
 
from app.core.security import get_current_user_id
from app.db.session import get_db
from app.services.document_service import DocumentService
 
logger = logging.getLogger(__name__)
router = APIRouter()
 
 
@router.post("/analyze")
async def analyze_document(
    file: UploadFile = File(...),
    risk_assessment: bool = Form(True),
    summarize: bool = Form(True),
    clause_extraction: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Classify, summarize and get RAG-based suggestions for an uploaded document."""
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 25 MB limit.")
 
    service = DocumentService()
    return await service.analyze(
        content=content,
        filename=file.filename or "document",
        risk_assessment=risk_assessment,
        summarize=summarize,
        clause_extraction=clause_extraction,
    )