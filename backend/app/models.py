from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
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
    parser_engine = Column(String(150), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    jobs = relationship("ExtractionJob", back_populates="document", cascade="all, delete-orphan")
    khp_master_resolution = relationship(
        "KHPMasterResolution",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"

    id = Column(UUID(as_uuid=False), primary_key=True)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="queued")
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    temp_file_key = Column(String(64), nullable=True)
    available_at = Column(DateTime(timezone=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    worker_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="jobs")
    __table_args__ = (
        Index("ix_extraction_jobs_polling", "status", "available_at", "created_at"),
        Index("ix_extraction_jobs_lease", "status", "lease_expires_at"),
    )


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id = Column(UUID(as_uuid=False), primary_key=True)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    form_field_name = Column(String(120), nullable=False)
    extracted_value = Column(Text, nullable=True)
    mapped_value = Column(Text, nullable=True)
    confidence = Column(Numeric(5, 4), nullable=False, default=0)
    source = Column(String(100), nullable=False)
    needs_review = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KHPMasterResolution(Base):
    __tablename__ = "khp_master_resolutions"

    id = Column(String(36), primary_key=True)
    document_id = Column(
        UUID(as_uuid=False),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    resolution_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="khp_master_resolution")


class KHPKelompokKegiatan(Base):
    __tablename__ = "khp_kelompok_kegiatan"

    id_kelompok_kegiatan = Column(Integer, primary_key=True)
    nm_kelompok_kegiatan = Column(Text, nullable=False)
    is_aktif = Column(Boolean, nullable=False, default=True)


class KHPKegiatan1(Base):
    __tablename__ = "khp_kegiatan_1"

    id_kegiatan_1 = Column(Integer, primary_key=True)
    nm_kegiatan_1 = Column(Text, nullable=False)
    id_kelompok_kegiatan = Column(
        Integer,
        ForeignKey("khp_kelompok_kegiatan.id_kelompok_kegiatan", ondelete="CASCADE"),
        nullable=False,
    )
    is_aktif = Column(Boolean, nullable=False, default=True)

    kelompok = relationship("KHPKelompokKegiatan", backref="kegiatan_1_list")


class KHPTingkat(Base):
    __tablename__ = "khp_tingkat"

    id_tingkat = Column(Integer, primary_key=True)
    nm_tingkat = Column(Text, nullable=False)


class KHPJabatanPrestasi(Base):
    __tablename__ = "khp_jabatan_prestasi"

    id_jabatan_prestasi = Column(Integer, primary_key=True)
    nm_jabatan_prestasi = Column(Text, nullable=False)


class KHPKegiatan2(Base):
    __tablename__ = "khp_kegiatan_2"

    id_kegiatan_2 = Column(Integer, primary_key=True)
    id_kegiatan_1 = Column(
        Integer,
        ForeignKey("khp_kegiatan_1.id_kegiatan_1", ondelete="CASCADE"),
        nullable=False,
    )
    id_tingkat = Column(
        Integer,
        ForeignKey("khp_tingkat.id_tingkat", ondelete="SET NULL"),
        nullable=True,
    )
    id_jabatan_prestasi = Column(
        Integer,
        ForeignKey("khp_jabatan_prestasi.id_jabatan_prestasi", ondelete="SET NULL"),
        nullable=True,
    )

    kegiatan_1 = relationship("KHPKegiatan1", backref="kegiatan_2_list")
    tingkat = relationship("KHPTingkat")
    jabatan_prestasi = relationship("KHPJabatanPrestasi")


class KHPMasterRule(Base):
    __tablename__ = "khp_master_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_no = Column(Integer, nullable=False)
    id_kelompok_kegiatan = Column(
        Integer,
        ForeignKey("khp_kelompok_kegiatan.id_kelompok_kegiatan", ondelete="CASCADE"),
        nullable=False,
    )
    id_kegiatan_1 = Column(
        Integer,
        ForeignKey("khp_kegiatan_1.id_kegiatan_1", ondelete="CASCADE"),
        nullable=False,
    )
    id_tingkat = Column(
        Integer,
        ForeignKey("khp_tingkat.id_tingkat", ondelete="SET NULL"),
        nullable=True,
    )
    id_jabatan_prestasi = Column(
        Integer,
        ForeignKey("khp_jabatan_prestasi.id_jabatan_prestasi", ondelete="SET NULL"),
        nullable=True,
    )
    dasar_penilaian = Column(Text, nullable=False)
    id_kegiatan_2 = Column(
        Integer,
        ForeignKey("khp_kegiatan_2.id_kegiatan_2", ondelete="CASCADE"),
        nullable=False,
    )
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    kelompok = relationship("KHPKelompokKegiatan")
    kegiatan_1 = relationship("KHPKegiatan1")
    tingkat = relationship("KHPTingkat")
    jabatan_prestasi = relationship("KHPJabatanPrestasi")
    kegiatan_2 = relationship("KHPKegiatan2")
