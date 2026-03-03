import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.security import get_current_user_id
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class RiskRequest(BaseModel):
    case_type: str
    situation: str
    stage: str          # pre_dispute | negotiation | filed | judgment
    has_documents: str  # yes | some | no
    time_elapsed: str   # under_1m | 1_6m | 6m_2y | over_2y
    opposing_party: str # individual | individual_lawyer | company | government


@router.post("/assess")
async def assess_risk(
    req: RiskRequest,
    user_id: str = Depends(get_current_user_id),
):
    from app.services.agent_service import _get_client
    import json

    client = _get_client()

    prompt = f"""You are a senior Bangladesh legal expert with 20+ years of experience. Conduct a thorough legal risk assessment for the following case.

CASE TYPE: {req.case_type}
DISPUTE STAGE: {req.stage}
SITUATION:
{req.situation}

CONTEXT:
- Documents available: {req.has_documents}
- Time elapsed: {req.time_elapsed}
- Opposing party: {req.opposing_party}

Return ONLY a valid JSON object (no markdown, no explanation) with this exact structure:
{{
  "overall_score": <integer 0-100, where 100 = strongest position>,
  "risk_level": "<Critical|High|Moderate|Favorable>",
  "summary": "<2-3 sentence plain English summary of the case assessment>",
  "strengths": [
    {{"point": "<strength>", "detail": "<why this helps>"}}
  ],
  "weaknesses": [
    {{"point": "<weakness>", "detail": "<why this hurts>"}}
  ],
  "applicable_laws": [
    {{"law": "<law name and section>", "relevance": "<how it applies to this case>"}}
  ],
  "evidence_to_gather": [
    "<specific evidence item>"
  ],
  "recommended_actions": [
    {{"priority": "<High|Medium|Low>", "action": "<what to do>", "reason": "<why>"}}
  ],
  "court_timeline": "<realistic estimate if taken to court in Bangladesh>",
  "settlement_advice": "<advice on whether to settle or litigate>"
}}

Provide 2-4 items for strengths, weaknesses, laws, evidence. Provide 3-5 recommended actions.
Base all advice strictly on Bangladesh law context."""

    r = client.chat.complete(
        model=settings.MISTRAL_MODEL,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = r.choices[0].message.content.strip()
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        logger.error(f"Risk parse error: {e} | raw: {raw[:300]}")
        raise