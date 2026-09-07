from typing import Any
from pydantic import BaseModel


class UploadResponse(BaseModel):
    document_id: str
    job_id: str
    status: str


class FieldResult(BaseModel):
    value: str | None
    confidence: float
    source: str
    needs_review: bool


class ExtractionResult(BaseModel):
    document_id: str
    status: str
    needs_review: bool
    fields: dict[str, FieldResult]
    raw_text_preview: str | None = None
    parser_engine: str | None = None


class OptionsResponse(BaseModel):
    options: dict[str, list[str]]
