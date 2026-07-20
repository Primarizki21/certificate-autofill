from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=False), primary_key=True)
    source_system = Column(String(100), nullable=True)
    tahun_akademik = Column(String(50), nullable=False)
    bukti_fisik = Column(String(50), nullable=False, default="Sertifikat")
    original_file_name = Column(Text, nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    checksum_sha256 = Column(String(64), nullable=False)
    status = Column(String(50), nullable=False, default="queued")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    file = relationship("DocumentFile", back_populates="document", uselist=False, cascade="all, delete-orphan")
    jobs = relationship("ExtractionJob", back_populates="document", cascade="all, delete-orphan")


class DocumentFile(Base):
    __tablename__ = "document_files"

    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    pdf_data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="file")


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"

    id = Column(UUID(as_uuid=False), primary_key=True)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), nullable=False, default="queued")
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="jobs")


class ParsedDocument(Base):
    __tablename__ = "parsed_documents"

    id = Column(UUID(as_uuid=False), primary_key=True)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    parser_engine = Column(String(50), nullable=False)
    raw_text = Column(Text, nullable=True)
    raw_markdown = Column(Text, nullable=True)
    raw_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id = Column(UUID(as_uuid=False), primary_key=True)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    form_field_name = Column(String(120), nullable=False)
    extracted_value = Column(Text, nullable=True)
    mapped_value = Column(Text, nullable=True)
    confidence = Column(Numeric(5, 4), nullable=False, default=0)
    source = Column(String(100), nullable=False)
    needs_review = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
