import logging
from typing import Literal

from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_mistral_client = None


def _get_client():
    global _mistral_client
    if _mistral_client is None:
        if not settings.MISTRAL_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MISTRAL_API_KEY is not configured.",
            )
        from mistralai import Mistral
        _mistral_client = Mistral(api_key=settings.MISTRAL_API_KEY)
        logger.info("Mistral client initialized.")
    return _mistral_client


CLASSIFIER_PROMPT = """
You are an intent classifier for a Bangladesh Legal Assistant.

Classify the user's message into EXACTLY ONE category:
- GREETING: greetings, introductions, hello, hi, etc.
- LEGAL: any legal matter — crimes, victim situations, legal procedures, laws, rights, FIR, court, bail, etc.
- NON_LEGAL: topics unrelated to Bangladesh law (weather, programming, jokes, etc.)

IMPORTANT: Even without the word "law", classify as LEGAL if it involves crime, illegal activity, victim situations, or legal consequences.

Return ONLY ONE WORD: GREETING, LEGAL, or NON_LEGAL. No explanation.
""".strip()

LEGAL_SYSTEM_PROMPT = """
You are Bangladesh Legal Assistant.

You answer ONLY Bangladesh legal questions using the provided LEGAL_CONTEXT.

STRICT RULES:
1. Use ONLY the provided LEGAL_CONTEXT — do NOT invent laws or hallucinate.
2. If context is insufficient, respond EXACTLY: "I apologize, but I do not have sufficient legal information in the database to answer this question."

RESPONSE FORMAT (mandatory):

**Answer:**
A clear 1–2 sentence explanation.

**What You Should Do:**
3–5 practical bullet points.

**Legal Basis:**
Relevant law sections from context.
""".strip()

GENERAL_SYSTEM_PROMPT = """
You are Bangladesh Legal Assistant.
- If the user greets you, respond politely and explain you assist with Bangladesh legal matters.
- If the user asks a non-legal question, respond: "I apologize, but I am designed to assist only with Bangladesh legal matters."
""".strip()


def classify_intent(query: str) -> Literal["LEGAL", "GREETING", "NON_LEGAL"]:
    try:
        client = _get_client()
        response = client.chat.complete(
            model=settings.MISTRAL_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": query},
            ],
        )
        raw = response.choices[0].message.content.strip().upper()
        if raw in ("LEGAL", "GREETING", "NON_LEGAL"):
            return raw
        logger.warning(f"Unexpected intent classification: {raw!r}, defaulting to LEGAL")
        return "LEGAL"
    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        return "LEGAL"


def generate_legal_answer(context: str, query: str) -> str:
    try:
        client = _get_client()
        prompt = f"LEGAL_CONTEXT:\n{context}\n\nUSER QUESTION:\n{query}"
        response = client.chat.complete(
            model=settings.MISTRAL_MODEL,
            temperature=0.1,
            messages=[
                {"role": "system", "content": LEGAL_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Legal answer generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable. Please try again.",
        )


def handle_general(query: str) -> str:
    try:
        client = _get_client()
        response = client.chat.complete(
            model=settings.MISTRAL_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": GENERAL_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"General response generation failed: {e}")
        return "I'm here to help with Bangladesh legal questions. How can I assist you?"
