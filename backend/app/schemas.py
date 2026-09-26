from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    document_id: str
    job_id: str
    status: str


class FieldResult(BaseModel):
    value: str | None
    confidence: float
    source: str
    needs_review: bool


class MasterOption(BaseModel):
    id: int
    label: str
    active: bool = True
    group_id: int | None = None


class MasterResolutionField(BaseModel):
    id: int | None = None
    label: str | None = None
    status: str
    reasons: list[str] = Field(default_factory=list)


class MasterResolution(BaseModel):
    fields: dict[str, MasterResolutionField]
    status: str
    id_kegiatan_2: int | None = None
    lookup_status: str
    master_rule: dict[str, object] | None = None
    rule_status: str = "not_loaded"
    evidence_status: str = "not_checked"
    reasons: list[str] = Field(default_factory=list)

class ExtractionResult(BaseModel):
    document_id: str
    status: str
    needs_review: bool
    fields: dict[str, FieldResult]
    raw_text_preview: str | None = None
    parser_engine: str | None = None
    master_resolution: MasterResolution | None = None

class PublicExtractionResult(BaseModel):
    document_id: str
    status: str
    needs_review: bool
    fields: dict[str, FieldResult]


class OptionsResponse(BaseModel):
    options: dict[str, list[str | MasterOption]]


class KHPRuleResponse(BaseModel):
    id: int
    source_no: int
    id_kelompok_kegiatan: int
    nama_kelompok_kegiatan: str | None = None
    id_kegiatan_1: int
    nama_kegiatan_1: str | None = None
    id_tingkat: int | None = None
    nama_tingkat: str | None = None
    id_jabatan_prestasi: int | None = None
    nama_jabatan_prestasi: str | None = None
    dasar_penilaian: str
    id_kegiatan_2: int
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


class CreateKHPRuleRequest(BaseModel):
    id_kelompok_kegiatan: int
    id_kegiatan_1: int
    id_tingkat: int | None = None
    id_jabatan_prestasi: int | None = None
    dasar_penilaian: str
    id_kegiatan_2: int | None = None
    is_active: bool = True


class UpdateKHPRuleRequest(BaseModel):
    dasar_penilaian: str | None = None
    is_active: bool | None = None


class KHPRulesListResponse(BaseModel):
    total: int
    items: list[KHPRuleResponse]


class KHPFieldSelection(BaseModel):
    id: int | None = None
    label: str | None = None


class ExtractedCertificateData(BaseModel):
    nama_kegiatan_sertifikasi: str | None = None
    nomor_bukti_fisik_nomor_sertifikasi: str | None = None
    penyelenggara_kegiatan: str | None = None
    jenis_penyelenggara: str | None = None
    waktu_mulai_pelaksanaan: str | None = None
    waktu_selesai_pelaksanaan: str | None = None
    bukti_fisik: str | None = "Sertifikat"
    tahun_akademik: str | None = None
    kelompok_kegiatan: KHPFieldSelection | None = None
    jenis_kegiatan: KHPFieldSelection | None = None
    tingkat: KHPFieldSelection | None = None
    prestasi_partisipasi_jabatan: KHPFieldSelection | None = None
    id_kegiatan_2: int | None = None


class ExtractV1Response(BaseModel):
    status: str = "success"
    needs_review: bool = False
    data: ExtractedCertificateData
    confidence: dict[str, float] = Field(default_factory=dict)
    sources: dict[str, str] = Field(default_factory=dict)
    review_reasons: list[str] = Field(default_factory=list)
    parser_engine: str | None = None
