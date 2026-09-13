import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)
from app.config import settings
from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from app.services.ocr_fallback import extract_text_with_ocr
from app.services.organizer_boundary import apply_organizer_boundary
from app.services.pdf_fast_path import extract_text_with_pymupdf
from app.services.title_boundary import apply_title_boundary


@dataclass
class PipelineResult:
    parser_engine: str
    raw_text: str
    raw_markdown: str | None
    raw_json: dict[str, Any] | None
    mapped_fields: dict


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

    # Ekstraksi awal menentukan apakah OCR perlu dipaksa untuk mencari tanggal.
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

    # Gemini menjadi jalur utama saat diaktifkan; error/key kosong tetap fallback.
    gemini_used = False
    if settings.enable_tesseract_gemini:
        from app.services.gemini_extractor import extract_fields_with_gemini

        gemini_extracted, meta = extract_fields_with_gemini(raw_text)
        if gemini_extracted is not None:
            extracted = gemini_extracted
            parser_engine = f"{parser_engine}+{meta.get('model', 'gemini')}"
            raw_json = meta
            gemini_used = True

    if not gemini_used:
        # v8: ekstraktor organizer phrase-anchored — memperbaiki field
        # penyelenggara dan memberi sinyal lebih baik ke router tingkat.
        from app.services.organizer_v2 import extract_organizer_v2

        v2_org = extract_organizer_v2(raw_text)
        if v2_org:
            extracted["penyelenggara_kegiatan"] = ExtractedValue(
                v2_org, 0.84, "organizer_v2"
            )

        # PROD-002: normalisasi organizer & nomor pasca-organizer_v2 (0 LLM).
        # DEFAULT OFF (config) — aktifkan hanya setelah re-eval disetujui user.
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

        # Combined v4.2 Staging — fallback offline saat Gemini tidak dipakai.
        # DEFAULT OFF (config) — aktifkan via ENABLE_COMBINED_V4_2=true.
        if settings.enable_combined_v4_2:
            from app.services.combined_extractor import apply_combined_v4_2

            extracted = apply_combined_v4_2(extracted, raw_text)
            parser_engine = f"{parser_engine}+combined_v4_2"
        elif settings.enable_combined_v4_1:
            from app.services.combined_extractor import apply_combined_v4_1

            extracted = apply_combined_v4_1(extracted, raw_text)
        elif settings.enable_combined_v4:
            from app.services.combined_extractor import apply_combined_v4

            extracted = apply_combined_v4(extracted, raw_text)
        elif settings.enable_combined_v3:
            from app.services.combined_extractor import apply_combined_v3

            extracted = apply_combined_v3(extracted, raw_text)
        elif settings.enable_combined_v2:
            from app.services.combined_extractor import apply_combined_v2

            extracted = apply_combined_v2(extracted, raw_text)

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
    return PipelineResult(
        parser_engine=parser_engine,
        raw_text=raw_text,
        raw_markdown=raw_markdown,
        raw_json=raw_json,
        mapped_fields=mapped,
    )
