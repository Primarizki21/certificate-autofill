from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

AuccBase = declarative_base()


class KRP_KHP(AuccBase):
    __tablename__ = "krp_khp"
    __table_args__ = {"schema": "aucc"}

    id_krp_khp = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(
        UUID(as_uuid=False),
        ForeignKey("public.documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    id_semester = Column(BigInteger, nullable=True)
    id_kegiatan_2 = Column(
        BigInteger,
        ForeignKey("aucc.kegiatan_2.id_kegiatan_2"),
        nullable=True,
    )
    id_bukti_fisik = Column(BigInteger, nullable=True)
    id_mhs = Column(String(32), nullable=True)
    penyelenggara_krp_khp = Column(Text, nullable=True)
    nm_krp_khp = Column(Text, nullable=True)
    skor_krp_khp = Column(Numeric(10, 2), nullable=True)
    waktu_krp_khp = Column(Date, nullable=True)
    tgl_insert = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    id_pengguna = Column(String(120), nullable=True)
    is_ajukan_reward = Column(Boolean, nullable=False, default=False, server_default="false")
    waktu_krp_khp_selesai = Column(Date, nullable=True)
    jenis_penyelenggara = Column(Text, nullable=True)
    pembimbing_nidn = Column(String(32), nullable=True)
    pembimbing_nama = Column(Text, nullable=True)
    url_publikasi = Column(Text, nullable=True)
    no_bukti_fisik = Column(Text, nullable=True)
    pembimbing_nuptk = Column(String(32), nullable=True)
