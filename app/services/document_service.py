import logging

from app.core.config import settings
from app.services.agent_service import _get_client
from app.services.retriever_service import retrieve

logger = logging.getLogger(__name__)

_DOC_CLASSIFIER_PROMPT = """
You are a document classifier for a Bangladesh legal AI.
Classify the following document as LEGAL or NON_LEGAL.
A LEGAL document includes: contracts, NDAs, leases, court filings, statutes, legal notices.
Return ONLY one word: LEGAL or NON_LEGAL.
"""

_SUMMARIZER_PROMPT = """
You are a Bangladesh Legal Assistant. Summarize the legal document below.
Use this structure:
**Document Type:** (e.g. Employment Contract)
**Parties:** List the parties
**Summary:** 3-5 sentence overview
**Key Obligations:** 3-5 bullet points
"""

_RISK_PROMPT = """
You are a Bangladesh Legal Risk Analyst.
Analyze the legal document below and identify potential legal risks under Bangladesh law.
Return a JSON array (no markdown, no explanation, just raw JSON) like:
[
  {"title": "Risk title", "description": "What the risk is and why it matters", "severity": "high"},
  {"title": "Another risk", "description": "Details", "severity": "medium"},
  {"title": "Minor issue", "description": "Details", "severity": "low"}
]
severity must be one of: high, medium, low
Identify 3-6 risks. Focus on issues relevant to Bangladesh law (Contract Act 1872, etc.).
"""

_CLAUSE_PROMPT = """
You are a Bangladesh Legal Assistant specializing in contract analysis.
Extract the key legal clauses from the document below.
Return a JSON array (no markdown, no explanation, just raw JSON) like:
[
  {"type": "Termination Clause", "content": "Summary of the clause in plain language"},
  {"type": "Payment Terms", "content": "Summary of payment obligations"},
  {"type": "Jurisdiction", "content": "Which court/law governs disputes"}
]
Extract 4-8 clauses. Focus on: payment, termination, jurisdiction, liability, confidentiality, penalties, dispute resolution.
"""

_SUGGESTIONS_PROMPT = """
You are a Bangladesh Legal Assistant.
Based on the document text and the Bangladesh law context below,
give 3-5 specific, actionable suggestions for the user.
Format each as a bullet point starting with an action verb.

DOCUMENT (excerpt):
{doc_text}

BANGLADESH LAW CONTEXT:
{context}
"""


class DocumentService:

    async def analyze(
        self,
        content: bytes,
        filename: str,
        risk_assessment: bool = True,
        summarize: bool = True,
        clause_extraction: bool = False,
    ) -> dict:

        text = self._extract_text(content, filename)
        if not text.strip():
            return {"is_legal": False, "error": "Could not extract text from document."}

        is_legal = self._classify(text)
        if not is_legal:
            return {
                "is_legal": False,
                "message": "This does not appear to be a legal document.",
            }

        result: dict = {"is_legal": True, "filename": filename}

        if summarize:
            result["summary"] = self._summarize(text)

        if risk_assessment:
            result["risks"] = self._assess_risks(text)

        if clause_extraction:
            result["clauses"] = self._extract_clauses(text)

        # RAG-based suggestions (always run if any analysis is selected)
        if summarize or risk_assessment or clause_extraction:
            rag = retrieve(text[:600])
            context_text = "\n\n---\n\n".join(
                hit["text"] for hit in rag.get("results", [])[:5]
            )
            if context_text:
                result["suggestions"] = self._suggestions(text[:1500], context_text)
                result["sources"] = [
                    hit["metadata"]["citation"]
                    for hit in rag.get("results", [])[:3]
                    if hit.get("metadata", {}).get("citation")
                ]

        return result

    # ── text extraction ──────────────────────────────────────────────────

    def _extract_text(self, content: bytes, filename: str) -> str:
        fn = filename.lower()
        try:
            if fn.endswith(".pdf"):
                import fitz
                doc = fitz.open(stream=content, filetype="pdf")
                return "\n".join(page.get_text() for page in doc)
            elif fn.endswith(".docx"):
                import docx as _docx
                from io import BytesIO
                d = _docx.Document(BytesIO(content))
                return "\n".join(p.text for p in d.paragraphs)
            else:
                return content.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"Text extraction error: {e}")
            return ""

    # ── AI calls ─────────────────────────────────────────────────────────

    def _classify(self, text: str) -> bool:
        client = _get_client()
        r = client.chat.complete(
            model=settings.MISTRAL_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": _DOC_CLASSIFIER_PROMPT},
                {"role": "user", "content": text[:2000]},
            ],
        )
        return r.choices[0].message.content.strip().upper() == "LEGAL"

    def _summarize(self, text: str) -> str:
        client = _get_client()
        r = client.chat.complete(
            model=settings.MISTRAL_MODEL,
            temperature=0.1,
            messages=[
                {"role": "system", "content": _SUMMARIZER_PROMPT},
                {"role": "user", "content": text[:4000]},
            ],
        )
        return r.choices[0].message.content.strip()

    def _assess_risks(self, text: str) -> list:
        import json
        client = _get_client()
        r = client.chat.complete(
            model=settings.MISTRAL_MODEL,
            temperature=0.1,
            messages=[
                {"role": "system", "content": _RISK_PROMPT},
                {"role": "user", "content": text[:4000]},
            ],
        )
        raw = r.choices[0].message.content.strip()
        try:
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception as e:
            logger.error(f"Risk parsing error: {e} | raw: {raw[:200]}")
            return [{"title": "Analysis Error", "description": "Could not parse risk assessment.", "severity": "low"}]

    def _extract_clauses(self, text: str) -> list:
        import json
        client = _get_client()
        r = client.chat.complete(
            model=settings.MISTRAL_MODEL,
            temperature=0.1,
            messages=[
                {"role": "system", "content": _CLAUSE_PROMPT},
                {"role": "user", "content": text[:4000]},
            ],
        )
        raw = r.choices[0].message.content.strip()
        try:
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception as e:
            logger.error(f"Clause parsing error: {e} | raw: {raw[:200]}")
            return [{"type": "Extraction Error", "content": "Could not parse clause extraction."}]

    def _suggestions(self, doc_text: str, context: str) -> str:
        client = _get_client()
        prompt = _SUGGESTIONS_PROMPT.format(doc_text=doc_text, context=context)
        r = client.chat.complete(
            model=settings.MISTRAL_MODEL,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.choices[0].message.content.strip()
