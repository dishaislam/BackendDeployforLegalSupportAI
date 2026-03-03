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

from pydantic import BaseModel
from typing import Optional

class NoticeRequest(BaseModel):
    notice_type: str
    sender_name: str
    sender_address: str
    sender_contact: str
    recipient_name: str
    recipient_address: str
    situation: str
    urgency: str          # standard | urgent | immediate
    tone: str             # formal | strongly_worded | final_warning
    relief_sought: str
    deadline_days: int


@router.post("/generate-notice")
async def generate_notice(
    req: NoticeRequest,
    user_id: str = Depends(get_current_user_id),
):
    from app.services.agent_service import _get_client
    from app.core.config import settings
    from datetime import date

    today = date.today().strftime("%d %B %Y")
    ref = f"LSA/{date.today().year}/{date.today().month:02d}{date.today().day:02d}/{hash(req.sender_name) % 9000 + 1000}"

    tone_instruction = {
        "formal": "Use a formal, professional, and measured tone.",
        "strongly_worded": "Use a firm, assertive, and strongly worded tone that conveys seriousness.",
        "final_warning": "Use an unequivocal final warning tone — this is the last notice before legal action.",
    }.get(req.tone, "Use a formal tone.")

    urgency_instruction = {
        "standard": f"Give the recipient {req.deadline_days} days to comply.",
        "urgent": f"Give the recipient {req.deadline_days} days to comply. Emphasize the urgency clearly.",
        "immediate": "Demand immediate compliance within 48 hours. Stress extreme urgency.",
    }.get(req.urgency, f"Give {req.deadline_days} days to comply.")

    prompt = f"""You are a senior Bangladesh legal advocate drafting a professional legal notice.

Draft a complete, formal legal notice using ONLY the information provided below. Do NOT use placeholder brackets like [AMOUNT], [DATE], [CHEQUE NUMBER] or any similar placeholders. If a specific detail (like a cheque number or exact amount) was not provided in the situation, omit that specific sub-point entirely or rephrase to reflect only what is known.

SENDER: {req.sender_name}
SENDER ADDRESS: {req.sender_address}
SENDER CONTACT: {req.sender_contact}

RECIPIENT: {req.recipient_name}
RECIPIENT ADDRESS: {req.recipient_address}

NOTICE TYPE: {req.notice_type}
DATE: {today}
REFERENCE: {ref}

SITUATION / FACTS:
{req.situation}

RELIEF SOUGHT:
{req.relief_sought}

TONE INSTRUCTION: {tone_instruction}
DEADLINE INSTRUCTION: {urgency_instruction}

REQUIREMENTS:
1. Start with proper legal notice heading and reference number
2. Include "WHEREAS" clauses laying out the facts using ONLY the details provided above
3. Include specific Bangladesh law citations relevant to this notice type (Contract Act 1872, Transfer of Property Act 1882, Negotiable Instruments Act 1881, etc.)
4. Include "THEREFORE TAKE NOTICE" section with clear demands based on the relief sought
5. State consequences of non-compliance (legal proceedings, damages, costs)
6. End with proper advocate signature block format
7. Include a disclaimer at the bottom
8. Format it as a real legal document with proper spacing and structure
9. Do NOT use any markdown formatting — no asterisks, no bold (**), no italic (*), no bullet symbols. Use plain text with ALL CAPS for headings only.
10. CRITICAL: Never write placeholder text in square brackets.

Output ONLY the notice text, nothing else."""

    client = _get_client()
    r = client.chat.complete(
        model=settings.MISTRAL_MODEL,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    notice_text = r.choices[0].message.content.strip()

    return {
        "notice": notice_text,
        "ref": ref,
        "date": today,
        "notice_type": req.notice_type,
    }