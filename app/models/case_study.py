import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from app.db.base import Base


class CaseStudyModel(Base):
    __tablename__ = "case_studies"

    case_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(300), nullable=False, default="New Case Study")
    description = Column(Text, nullable=True)
    practice_area = Column(String(100), nullable=True)   # e.g. "Family Law", "Criminal Law"
    status = Column(String(50), default="active")        # active, closed, archived
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    documents = relationship("CaseDocumentModel", back_populates="case_study", cascade="all, delete-orphan", lazy="select")
    messages = relationship("CaseMessageModel", back_populates="case_study", cascade="all, delete-orphan", lazy="select")

    def __repr__(self):
        return f"<CaseStudy id={self.case_id} title={self.title}>"


class CaseDocumentModel(Base):
    __tablename__ = "case_documents"

    doc_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("case_studies.case_id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(300), nullable=False)
    file_type = Column(String(20), nullable=True)
    extracted_text = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    case_study = relationship("CaseStudyModel", back_populates="documents")

    def __repr__(self):
        return f"<CaseDocument id={self.doc_id} filename={self.filename}>"


class CaseMessageModel(Base):
    __tablename__ = "case_messages"

    message_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("case_studies.case_id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)   # user / assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    case_study = relationship("CaseStudyModel", back_populates="messages")
