import json
import logging
import uuid
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.case_study import CaseStudyModel, CaseDocumentModel, CaseMessageModel
from app.services.agent_service import _get_client, generate_legal_answer, LEGAL_SYSTEM_PROMPT
from app.services.document_service import DocumentService
from app.services.retriever_service import retrieve

logger = logging.getLogger(__name__)

PRACTICE_AREAS = [
    "Family Law", "Criminal Law", "Land & Property", "Commercial Law",
    "Cyber Law", "Constitutional Law", "Labor Law", "Immigration Law",
    "Intellectual Property", "Environmental Law", "Tax Law", "Banking Law",
    "Domestic Violence", "Shariah Law", "Corporate Law", "Civil Litigation"
]

_CLASSIFY_AREA_PROMPT = f"""
You are a Bangladesh legal classifier.
Given a case title, description, and document summaries, classify the case into ONE practice area.
Choose ONLY from this list: {', '.join(PRACTICE_AREAS)}
Return ONLY the practice area name, nothing else.
"""

_CASE_CHAT_SYSTEM = """
You are a Bangladesh Legal Assistant helping analyze a specific legal case.
You have access to the case documents provided below as context.
Answer questions specifically about this case and relevant Bangladesh law.
Be precise, cite document content when relevant, and give actionable advice.

CASE DOCUMENTS CONTEXT:
{doc_context}
"""


class CaseStudyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Case CRUD ────────────────────────────────────────────────────────

    async def create_case(self, user_id: str, title: str, description: str = "") -> dict:
        case = CaseStudyModel(user_id=user_id, title=title, description=description)
        self.db.add(case)
        await self.db.commit()
        await self.db.refresh(case)
        return self._case_to_dict(case)

    async def list_cases(self, user_id: str) -> List[dict]:
        result = await self.db.execute(
            select(CaseStudyModel)
            .where(CaseStudyModel.user_id == user_id)
            .order_by(CaseStudyModel.updated_at.desc())
        )
        cases = result.scalars().all()
        out = []
        for c in cases:
            docs = await self._get_docs(c.case_id)
            msgs = await self._get_messages(c.case_id)
            d = self._case_to_dict(c)
            d["document_count"] = len(docs)
            d["message_count"] = len(msgs)
            out.append(d)
        return out

    async def get_case(self, case_id: uuid.UUID, user_id: str) -> dict:
        case = await self._fetch_case(case_id, user_id)
        docs = await self._get_docs(case_id)
        msgs = await self._get_messages(case_id)
        d = self._case_to_dict(case)
        d["documents"] = [self._doc_to_dict(doc) for doc in docs]
        d["messages"] = [self._msg_to_dict(m) for m in msgs]
        return d

    async def update_case(self, case_id: uuid.UUID, user_id: str, title: str = None, description: str = None, status: str = None) -> dict:
        case = await self._fetch_case(case_id, user_id)
        if title: case.title = title
        if description is not None: case.description = description
        if status: case.status = status
        await self.db.commit()
        await self.db.refresh(case)
        return self._case_to_dict(case)

    async def delete_case(self, case_id: uuid.UUID, user_id: str) -> None:
        case = await self._fetch_case(case_id, user_id)
        await self.db.delete(case)
        await self.db.commit()

    # ── Documents ────────────────────────────────────────────────────────

    async def upload_document(self, case_id: uuid.UUID, user_id: str, content: bytes, filename: str) -> dict:
        await self._fetch_case(case_id, user_id)

        # Extract text
        svc = DocumentService()
        text = svc._extract_text(content, filename)

        # Summarize document briefly
        summary = None
        if text.strip():
            try:
                client = _get_client()
                r = client.chat.complete(
                    model=settings.MISTRAL_MODEL,
                    temperature=0.1,
                    messages=[
                        {"role": "system", "content": "Summarize this legal document in 2-3 sentences. Be concise."},
                        {"role": "user", "content": text[:3000]},
                    ],
                )
                summary = r.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Document summary failed: {e}")

        doc = CaseDocumentModel(
            case_id=case_id,
            filename=filename,
            file_type=filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt",
            extracted_text=text[:50000],  # cap at 50k chars
            summary=summary,
        )
        self.db.add(doc)

        # Auto-classify practice area after first document upload
        case = await self._fetch_case(case_id, user_id)
        if not case.practice_area:
            case.practice_area = await self._classify_practice_area(case.title, case.description or "", summary or text[:500])

        await self.db.commit()
        await self.db.refresh(doc)
        return self._doc_to_dict(doc)

    async def delete_document(self, case_id: uuid.UUID, doc_id: uuid.UUID, user_id: str) -> None:
        await self._fetch_case(case_id, user_id)
        result = await self.db.execute(
            select(CaseDocumentModel).where(
                CaseDocumentModel.doc_id == doc_id,
                CaseDocumentModel.case_id == case_id
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found.")
        await self.db.delete(doc)
        await self.db.commit()

    # ── Chat ─────────────────────────────────────────────────────────────

    async def send_message(self, case_id: uuid.UUID, user_id: str, query: str) -> dict:
        await self._fetch_case(case_id, user_id)

        # Build context from case documents
        docs = await self._get_docs(case_id)
        doc_context = ""
        if docs:
            parts = []
            for doc in docs:
                parts.append(f"[Document: {doc.filename}]\n{doc.extracted_text[:3000] if doc.extracted_text else 'No text extracted'}")
            doc_context = "\n\n---\n\n".join(parts)

        # Also do RAG retrieval
        rag = retrieve(query)
        rag_context = "\n\n---\n\n".join(
            f"SOURCE: {h['metadata'].get('citation', '')}\n{h['text']}"
            for h in rag.get("results", [])[:4]
        )

        # Save user message
        user_msg = CaseMessageModel(case_id=case_id, role="user", content=query)
        self.db.add(user_msg)
        await self.db.commit()

        # Generate answer
        try:
            client = _get_client()
            system = _CASE_CHAT_SYSTEM.format(doc_context=doc_context or "No documents uploaded yet.")
            if rag_context:
                system += f"\n\nBANGLADESH LAW CONTEXT (RAG):\n{rag_context}"

            history = await self._get_messages(case_id)
            messages = [{"role": "system", "content": system}]
            # Include last 10 messages for context
            for m in history[-10:]:
                messages.append({"role": m.role, "content": m.content})
            messages.append({"role": "user", "content": query})

            r = client.chat.complete(
                model=settings.MISTRAL_MODEL,
                temperature=0.1,
                messages=messages,
            )
            answer = r.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Case chat generation failed: {e}")
            answer = "I encountered an error generating a response. Please try again."

        # Save assistant message
        ai_msg = CaseMessageModel(case_id=case_id, role="assistant", content=answer)
        self.db.add(ai_msg)
        await self.db.commit()

        return {"answer": answer, "case_id": str(case_id)}

    # ── Practice Areas (public) ──────────────────────────────────────────

    async def get_practice_area_stats(self) -> List[dict]:
        """Returns case counts grouped by practice area for all users."""
        result = await self.db.execute(
            select(CaseStudyModel.practice_area)
            .where(CaseStudyModel.practice_area.isnot(None))
        )
        areas = result.scalars().all()
        counts = {}
        for a in areas:
            counts[a] = counts.get(a, 0) + 1
        return [{"area": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _fetch_case(self, case_id: uuid.UUID, user_id: str) -> CaseStudyModel:
        result = await self.db.execute(
            select(CaseStudyModel).where(
                CaseStudyModel.case_id == case_id,
                CaseStudyModel.user_id == user_id
            )
        )
        case = result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail="Case study not found.")
        return case

    async def _get_docs(self, case_id: uuid.UUID) -> List[CaseDocumentModel]:
        result = await self.db.execute(
            select(CaseDocumentModel).where(CaseDocumentModel.case_id == case_id)
            .order_by(CaseDocumentModel.uploaded_at.asc())
        )
        return result.scalars().all()

    async def _get_messages(self, case_id: uuid.UUID) -> List[CaseMessageModel]:
        result = await self.db.execute(
            select(CaseMessageModel).where(CaseMessageModel.case_id == case_id)
            .order_by(CaseMessageModel.created_at.asc())
        )
        return result.scalars().all()

    async def _classify_practice_area(self, title: str, description: str, doc_excerpt: str) -> str:
        try:
            client = _get_client()
            text = f"Case Title: {title}\nDescription: {description}\nDocument excerpt: {doc_excerpt[:500]}"
            r = client.chat.complete(
                model=settings.MISTRAL_MODEL,
                temperature=0,
                messages=[
                    {"role": "system", "content": _CLASSIFY_AREA_PROMPT},
                    {"role": "user", "content": text},
                ],
            )
            area = r.choices[0].message.content.strip()
            return area if area in PRACTICE_AREAS else "Civil Litigation"
        except Exception as e:
            logger.error(f"Practice area classification failed: {e}")
            return "Civil Litigation"

    def _case_to_dict(self, c: CaseStudyModel) -> dict:
        return {
            "case_id": str(c.case_id),
            "title": c.title,
            "description": c.description or "",
            "practice_area": c.practice_area,
            "status": c.status,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }

    def _doc_to_dict(self, d: CaseDocumentModel) -> dict:
        return {
            "doc_id": str(d.doc_id),
            "filename": d.filename,
            "file_type": d.file_type,
            "summary": d.summary,
            "uploaded_at": d.uploaded_at.isoformat(),
        }

    def _msg_to_dict(self, m: CaseMessageModel) -> dict:
        return {
            "message_id": str(m.message_id),
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
