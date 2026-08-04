from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.services.docling_parser import parse_with_docling
from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from app.services.ocr_fallback import extract_text_with_ocr
from app.services.pdf_fast_path import extract_text_with_pymupdf


@dataclass
class PipelineResult:
    parser_engine: str
    raw_text: str
    raw_markdown: str | None
    raw_json: dict[str, Any] | None
    mapped_fields: dict


def run_extraction_pipeline(
    pdf_bytes: bytes,
    original_file_name: str,
    tahun_akademik: str,
    bukti_fisik: str,
) -> PipelineResult:
    fast = extract_text_with_pymupdf(pdf_bytes)
    raw_text = fast.text
    parser_engine = "pymupdf_fast_path"
    raw_markdown = None
    raw_json: dict[str, Any] | None = None

    if settings.enable_docling and len(raw_text.strip()) < settings.min_text_length:
        docling_result = parse_with_docling(pdf_bytes, original_file_name)
        if len(docling_result.text.strip()) >= settings.min_text_length:
            raw_text = docling_result.text
            parser_engine = "docling"
            raw_markdown = docling_result.markdown
            raw_json = docling_result.json_data
        elif docling_result.text.strip():
            raw_text = f"{raw_text}\n{docling_result.text}".strip()
            raw_markdown = docling_result.markdown
            raw_json = docling_result.json_data

    # Tahap OCR tidak hanya dipakai saat teks kosong. Pada sertifikat berbasis gambar,
    # Docling/RapidOCR kadang sudah menghasilkan teks panjang tetapi melewatkan baris
    # tanggal kecil seperti "24 Agustus - 22 September 2024". Karena itu pipeline
    # melakukan ekstraksi field sementara dulu, lalu memaksa OCR tambahan jika field
    # tanggal belum ditemukan. Ini bukan hardcode tanggal; OCR tetap membaca isi PDF.
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
            combined_text = f"{raw_text}\n{ocr_text}".strip()
            raw_text = combined_text
            parser_engine = "ocr_fallback" if len(raw_text.strip()) < settings.min_text_length else f"{parser_engine}+ocr_date_check"
            extracted = extract_certificate_fields(raw_text)

    # v8: ekstraktor organizer phrase-anchored (v7 P1) — memperbaiki field
    # penyelenggara dan memberi sinyal lebih baik ke router tingkat.
    from app.services.field_extractor import ExtractedValue
    from app.services.organizer_v2 import extract_organizer_v2

    v2_org = extract_organizer_v2(raw_text)
    if v2_org:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(v2_org, 0.84, "organizer_v2")

    mapped = map_fields_to_form(extracted, tahun_akademik=tahun_akademik, bukti_fisik=bukti_fisik)

    return PipelineResult(
        parser_engine=parser_engine,
        raw_text=raw_text,
        raw_markdown=raw_markdown,
        raw_json=raw_json,
        mapped_fields=mapped,
    )
