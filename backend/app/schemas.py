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
