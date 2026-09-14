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
    reasons: list[str] = Field(default_factory=list)

class ExtractionResult(BaseModel):
    document_id: str
    status: str
    needs_review: bool
    fields: dict[str, FieldResult]
    raw_text_preview: str | None = None
    parser_engine: str | None = None
    master_resolution: MasterResolution | None = None


class OptionsResponse(BaseModel):
    options: dict[str, list[str | MasterOption]]
