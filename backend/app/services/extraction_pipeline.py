import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from app.services.ocr_fallback import extract_text_with_ocr
from app.services.organizer_boundary import apply_organizer_boundary
from app.services.pdf_fast_path import extract_text_with_pymupdf
from app.services.semantic_review import (
    SemanticReviewAnnotation,
    build_semantic_review,
    merge_semantic_reviews,
)
from app.services.title_boundary import apply_title_boundary

logger = logging.getLogger(__name__)



@dataclass
class PipelineResult:
    parser_engine: str
    raw_text: str
    raw_markdown: str | None
    raw_json: dict[str, Any] | None
    mapped_fields: dict
    review_annotations: dict[str, SemanticReviewAnnotation] = field(
        default_factory=dict
    )


def _disabled_gemini_meta() -> dict[str, Any]:
    return {
        "status": "disabled",
        "gemini_status": "disabled",
        "model": settings.google_gemini_model,
        "fallback_reason": "feature_disabled",
        "error_fallback": True,
        "error": None,
        "error_type": None,
        "latency_s": 0.0,
        "prompt_tokens": 0,
        "candidates_tokens": 0,
        "cached_tokens": 0,
        "thoughts_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "cost_idr": 0.0,
        "calls_count": 0,
        "web_search_queries": [],
        "calls_details": [],
    }


def _complete_gemini_meta(
    meta: dict[str, Any] | None,
    *,
    model: str,
    extracted_available: bool,
) -> dict[str, Any]:
    provided = dict(meta or {})
    completed = _disabled_gemini_meta()
    completed.update(provided)
    status = str(
        provided.get("status")
        or ("success" if extracted_available else "error")
    )
    if status == "success" and not extracted_available:
        status = "error"
    fallback_reason = provided.get("fallback_reason")
    if status != "success" and not fallback_reason:
        fallback_reason = "gemini_error"
    completed.update(
        {
            "status": status,
            "gemini_status": status,
            "model": completed.get("model") or model,
            "fallback_reason": fallback_reason,
            "error_fallback": status != "success",
        }
    )
    if "calls_count" not in provided:
        completed["calls_count"] = 1 if status in {"success", "error"} else 0
    if not isinstance(completed.get("web_search_queries"), list):
        completed["web_search_queries"] = []
    if not isinstance(completed.get("calls_details"), list):
        completed["calls_details"] = []
    return completed


def _log_gemini_fallback(meta: dict[str, Any], offline_engine: str) -> None:
    logger.info(
        (
            "Gemini fallback status=%s model=%s fallback_reason=%s "
            "offline_engine=%s latency_s=%.4f calls_count=%d "
            "prompt_tokens=%d candidates_tokens=%d cached_tokens=%d "
            "thoughts_tokens=%d total_tokens=%d cost_usd=%.6f cost_idr=%.2f"
        ),
        meta.get("status", "unknown"),
        meta.get("model", "unknown"),
        meta.get("fallback_reason"),
        offline_engine,
        float(meta.get("latency_s", 0.0) or 0.0),
        int(meta.get("calls_count", 0) or 0),
        int(meta.get("prompt_tokens", 0) or 0),
        int(meta.get("candidates_tokens", 0) or 0),
        int(meta.get("cached_tokens", 0) or 0),
        int(meta.get("thoughts_tokens", 0) or 0),
        int(meta.get("total_tokens", 0) or 0),
        float(meta.get("cost_usd", 0.0) or 0.0),
        float(meta.get("cost_idr", 0.0) or 0.0),
    )


def run_extraction_pipeline(
    pdf_bytes: bytes,
    tahun_akademik: str,
    bukti_fisik: str,
) -> PipelineResult:
    fast = extract_text_with_pymupdf(pdf_bytes)
    raw_text = fast.text
    parser_engine = "pymupdf_fast_path"
    raw_markdown = None
    raw_json: dict[str, Any] | None = None
    review_annotations: dict[str, SemanticReviewAnnotation] = {}

    extracted = extract_certificate_fields(raw_text)
    date_missing = not (
        extracted.get("waktu_mulai_pelaksanaan")
        and extracted["waktu_mulai_pelaksanaan"].value
        and extracted.get("waktu_selesai_pelaksanaan")
        and extracted["waktu_selesai_pelaksanaan"].value
    )
    should_run_ocr = settings.enable_ocr_fallback and (
        len(raw_text.strip()) < settings.min_text_length or date_missing
    )
    if should_run_ocr:
        ocr_text = extract_text_with_ocr(pdf_bytes)
        if ocr_text.strip():
            raw_text = f"{raw_text}\n{ocr_text}".strip()
            parser_engine = (
                "ocr_fallback"
                if len(raw_text.strip()) < settings.min_text_length
                else f"{parser_engine}+ocr_date_check"
            )
            extracted = extract_certificate_fields(raw_text)

    gemini_used = False
    gemini_meta = _disabled_gemini_meta()
    raw_json = gemini_meta
    if settings.enable_tesseract_gemini:
        from app.services.gemini_extractor import extract_fields_with_gemini

        gemini_extracted, meta = extract_fields_with_gemini(raw_text)
        gemini_meta = _complete_gemini_meta(
            meta,
            model=settings.google_gemini_model,
            extracted_available=gemini_extracted is not None,
        )
        raw_json = gemini_meta
        if gemini_extracted is not None:
            review_annotations = build_semantic_review(raw_text, gemini_extracted)
            extracted = gemini_extracted
            parser_engine = f"{parser_engine}+{gemini_meta.get('model', 'gemini')}"
            gemini_used = True

    if not gemini_used:
        from app.services.organizer_v2 import extract_organizer_v2

        v2_org = extract_organizer_v2(raw_text)
        if v2_org:
            extracted["penyelenggara_kegiatan"] = ExtractedValue(
                v2_org, 0.84, "organizer_v2"
            )

        if settings.enable_organizer_normalization:
            from app.services.organizer_normalize import normalize_nomor, normalize_organizer

            norm_org = normalize_organizer(
                extracted.get("penyelenggara_kegiatan").value, raw_text
            )
            if norm_org:
                extracted["penyelenggara_kegiatan"] = ExtractedValue(
                    norm_org, 0.84, "organizer_v2"
                )
            norm_nomor = normalize_nomor(raw_text)
            if norm_nomor:
                extracted["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(
                    norm_nomor, 0.95, "regex_certificate_number"
                )

        offline_engine = "offline_rules"
        if settings.enable_combined_v4_2:
            from app.services.combined_extractor import apply_combined_v4_2

            extracted = apply_combined_v4_2(extracted, raw_text)
            parser_engine = f"{parser_engine}+combined_v4_2"
            offline_engine = "combined_v4_2"
        elif settings.enable_combined_v4_1:
            from app.services.combined_extractor import apply_combined_v4_1

            extracted = apply_combined_v4_1(extracted, raw_text)
            offline_engine = "combined_v4_1"
        elif settings.enable_combined_v4:
            from app.services.combined_extractor import apply_combined_v4

            extracted = apply_combined_v4(extracted, raw_text)
            offline_engine = "combined_v4"
        elif settings.enable_combined_v3:
            from app.services.combined_extractor import apply_combined_v3

            extracted = apply_combined_v3(extracted, raw_text)
            offline_engine = "combined_v3"
        elif settings.enable_combined_v2:
            from app.services.combined_extractor import apply_combined_v2

            extracted = apply_combined_v2(extracted, raw_text)
            offline_engine = "combined_v2"

        gemini_meta["fallback_engine"] = offline_engine
        gemini_meta["fallback_used"] = True
        raw_json = gemini_meta
        _log_gemini_fallback(gemini_meta, offline_engine)

    if gemini_used:
        title = extracted.get("nama_kegiatan_sertifikasi")
        if title is not None:
            title_boundary = apply_title_boundary(raw_text, title.value)
            if title_boundary.changed:
                extracted["nama_kegiatan_sertifikasi"] = ExtractedValue(
                    title_boundary.value,
                    title_boundary.confidence,
                    "title_boundary",
                )

        organizer = extracted.get("penyelenggara_kegiatan")
        if organizer is not None:
            organizer_boundary = apply_organizer_boundary(raw_text, organizer.value)
            if organizer_boundary.changed:
                extracted["penyelenggara_kegiatan"] = ExtractedValue(
                    organizer_boundary.value,
                    organizer_boundary.confidence,
                    "organizer_boundary",
                )

    mapped = map_fields_to_form(
        extracted, tahun_akademik=tahun_akademik, bukti_fisik=bukti_fisik
    )
    review_annotations = merge_semantic_reviews(
        review_annotations,
        build_semantic_review(raw_text, mapped),
    )
    return PipelineResult(
        parser_engine=parser_engine,
        raw_text=raw_text,
        raw_markdown=raw_markdown,
        raw_json=raw_json,
        mapped_fields=mapped,
        review_annotations=review_annotations,
    )
