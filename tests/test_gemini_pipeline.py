"""Unit tests for Gemini extraction pipeline, client, extractor, and evaluation.

Verifies:
  - Pricing table and cost calculations (USD & IDR per kurs 17.758)
  - Markdown fence cleaning and API key sanitization
  - Date standardization across formats (ISO, ID, EN, ordinal)
  - Enum mapping for tingkat and role
  - Mandatory full_text injection for form_mapper compatibility
  - Evaluation metric aggregation and Matcher v2 compatibility
  - 4-layer empirical proof functions (5-fold CV, Bootstrap CI, anti-hardcoding audit, safety net)
"""

import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from tests.gemini_client import (
    DEFAULT_EXCHANGE_RATE_IDR,
    PRICING_TABLE,
    GeminiCallResult,
    GeminiClient,
    calculate_cost,
    clean_json_markdown,
)
from tests.gemini_field_extractor import (
    ALL_EVAL_FIELDS,
    EVAL_FIELDS,
    SYSTEM_INSTRUCTION_STANDARD,
    USER_PROMPT_TEMPLATE,
    llm_json_to_extracted_values,
    normalize_llm_json,
    standardize_date,
)
from tests.benchmark_gemini_tesseract import (
    aggregate_metrics,
    evaluate_certificate_row,
)
from tests.validate_gemini_4layer import (
    run_anti_hardcoding_audit,
    run_bootstrap_resampling,
    run_safety_net_calibration,
    run_stratified_5fold_cv,
)
from tests.matchers import match_field


class TestGeminiClientAccounting:
    def test_pricing_table_rates(self):
        """Verifikasi tabel tarif resmi untuk ketiga model."""
        assert "gemini-2.5-flash" in PRICING_TABLE
        assert "gemini-2.5-flash-lite" in PRICING_TABLE
        assert "gemini-3.1-flash-lite" in PRICING_TABLE

        p_flash = PRICING_TABLE["gemini-2.5-flash"]
        assert p_flash.input_rate == 0.30
        assert p_flash.output_rate == 2.50
        assert p_flash.cache_rate == 0.03

        p_lite = PRICING_TABLE["gemini-2.5-flash-lite"]
        assert p_lite.input_rate == 0.10
        assert p_lite.output_rate == 0.40
        assert p_lite.cache_rate == 0.01

        p_31 = PRICING_TABLE["gemini-3.1-flash-lite"]
        assert p_31.input_rate == 0.25
        assert p_31.output_rate == 1.50
        assert p_31.cache_rate == 0.025

    def test_calculate_cost_calculation(self):
        """Uji perhitungan biaya USD dan IDR dengan kurs Rp17.758."""
        # 1M prompt tokens @ $0.30 + 1M output tokens @ $2.50 = $2.80 USD
        cost_usd, cost_idr = calculate_cost(
            model="gemini-2.5-flash",
            prompt_tokens=1_000_000,
            candidates_tokens=1_000_000,
            cached_tokens=0,
            thoughts_tokens=0,
            exchange_rate=17758.0,
        )
        assert pytest.approx(cost_usd, 0.0001) == 2.80
        assert pytest.approx(cost_idr, 0.1) == 2.80 * 17758.0

    def test_clean_json_markdown(self):
        """Uji pembersihan format markdown code block ```json ... ```."""
        raw_markdown = "```json\n{\"nama_kegiatan_sertifikasi\": \"Workshop AI\"}\n```"
        cleaned = clean_json_markdown(raw_markdown)
        assert cleaned == '{"nama_kegiatan_sertifikasi": "Workshop AI"}'

        plain = '{"status": "ok"}'
        assert clean_json_markdown(plain) == plain

    def test_api_key_sanitization(self):
        """Pastikan API key disanitasi dari pesan error."""
        client = GeminiClient(api_key="AIzaSySECRETKEYTEST12345", request_delay=0.0)
        err_msg = "Error 400 occurred with key AIzaSySECRETKEYTEST12345 in URL"
        sanitized = client._sanitize_error(err_msg)
        assert "AIzaSySECRETKEYTEST12345" not in sanitized
        assert "[REDACTED_API_KEY]" in sanitized


class TestGeminiFieldExtractor:
    def test_standardize_date_formats(self):
        """Uji konversi berbagai format tanggal ke 'DD/MM/YYYY'."""
        assert standardize_date("24/08/2024") == "24/08/2024"
        assert standardize_date("2024-08-24") == "24/08/2024"  # ISO format
        assert standardize_date("24-08-2024") == "24/08/2024"
        assert standardize_date("24 Agustus 2024") == "24/08/2024"
        assert standardize_date("September 23, 2024") == "23/09/2024"
        assert standardize_date("23rd September 2024") == "23/09/2024"
        assert standardize_date(None) is None
        assert standardize_date("-") is None
        assert standardize_date("null") is None

    def test_normalize_llm_json_tingkat(self):
        """Uji normalisasi tingkat ke enum baku KHP."""
        d1 = {"tingkat": "FAKULTAS"}
        assert normalize_llm_json(d1)["tingkat"] == "Fakultas"

        d2 = {"tingkat": "departemen matematika"}
        assert normalize_llm_json(d2)["tingkat"] == "Departemen/Program Studi"

        d3 = {"tingkat": "tingkat nasional"}
        assert normalize_llm_json(d3)["tingkat"] == "Nasional"

        d4 = {"tingkat": "international level"}
        assert normalize_llm_json(d4)["tingkat"] == "Internasional"

        d5 = {"tingkat": "rektorat universitas"}
        assert normalize_llm_json(d5)["tingkat"] == "Universitas"

        d6 = {"tingkat": "komunitas mahasiswa"}
        assert normalize_llm_json(d6)["tingkat"] == "Lainnya"

    def test_full_text_injection_mandatory(self):
        """CRITICAL: Verifikasi full_text diinjeksi ke extracted dict untuk form_mapper."""
        norm_json = {
            "nama_kegiatan_sertifikasi": "Lomba Karya Tulis Ilmiah",
            "nomor_bukti_fisik_nomor_sertifikasi": "100/KM/2024",
            "penyelenggara_kegiatan": "BEM FTMM Universitas Airlangga",
            "waktu_mulai_pelaksanaan": "15/10/2024",
            "waktu_selesai_pelaksanaan": "15/10/2024",
            "tingkat": "Fakultas",
            "raw_role": "Peserta",
        }
        raw_ocr_text = "UNIVERSITAS AIRLANGGA FAKULTAS TEKNOLOGI MAJU DAN MULTIDISIPLIN BEM FTMM"

        extracted = llm_json_to_extracted_values(norm_json, raw_ocr_text=raw_ocr_text)

        # Cek full_text terinjeksi
        assert "full_text" in extracted
        assert extracted["full_text"].value == raw_ocr_text
        assert extracted["full_text"].confidence == 1.0
        assert extracted["full_text"].source == "tesseract_raw"

        # Cek integrasi form_mapper
        from app.services.form_mapper import map_fields_to_form
        mapped = map_fields_to_form(extracted, "2024/2025", "Sertifikat")

        assert mapped["nama_kegiatan_sertifikasi"].value == "Lomba Karya Tulis Ilmiah"
        assert mapped["penyelenggara_kegiatan"].value == "BEM FTMM Universitas Airlangga"
        assert mapped["tingkat"].value == "Fakultas"
        assert mapped["prestasi_partisipasi_jabatan"].value == "Peserta"
        # Membuktikan form_mapper tidak silent error
        assert mapped["kelompok_kegiatan"].value is not None


class TestBenchmarkAndEvaluation:
    def test_evaluate_certificate_row(self):
        """Uji evaluasi per baris terhadap Ground Truth v9."""
        from app.services.field_extractor import ExtractedValue

        mapped_form = {
            "nama_kegiatan_sertifikasi": ExtractedValue("Workshop Machine Learning", 0.9, "llm"),
            "waktu_mulai_pelaksanaan": ExtractedValue("20/11/2024", 0.9, "llm"),
            "waktu_selesai_pelaksanaan": ExtractedValue("20/11/2024", 0.9, "llm"),
            "penyelenggara_kegiatan": ExtractedValue("HIMA DSI UNAIR", 0.9, "llm"),
            "nomor_bukti_fisik_nomor_sertifikasi": ExtractedValue("05/DS/XI/2024", 0.9, "llm"),
            "tingkat": ExtractedValue("Departemen/Program Studi", 0.9, "llm"),
        }

        gt_row = {
            "nama_kegiatan_sertifikasi": "Workshop Machine Learning",
            "waktu_mulai_pelaksanaan": "20/11/2024",
            "waktu_selesai_pelaksanaan": "20/11/2024",
            "penyelenggara_kegiatan": "HIMA DSI UNAIR",
            "nomor_bukti_fisik_nomor_sertifikasi": "05/DS/XI/2024",
            "tingkat": "Departemen/Program Studi",
        }

        res = evaluate_certificate_row(mapped_form, gt_row)
        for f in ALL_EVAL_FIELDS:
            assert res[f]["exact"] is True
            assert res[f]["fuzzy"] is True
            assert res[f]["wer"] == 0.0
            assert res[f]["cer"] == 0.0

    def test_aggregate_metrics(self):
        """Uji agregasi metrik akurasi multi-row."""
        dummy_results = [
            {
                "evaluation": {
                    "nama_kegiatan_sertifikasi": {"exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                    "tingkat": {"exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                }
            },
            {
                "evaluation": {
                    "nama_kegiatan_sertifikasi": {"exact": False, "fuzzy": True, "wer": 0.2, "cer": 0.1},
                    "tingkat": {"exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                }
            },
        ]
        agg = aggregate_metrics(dummy_results, ["nama_kegiatan_sertifikasi", "tingkat"])
        assert agg["nama_kegiatan_sertifikasi"]["exact"] == 1
        assert agg["nama_kegiatan_sertifikasi"]["fuzzy"] == 2
        assert agg["nama_kegiatan_sertifikasi"]["exact_pct"] == 50.0
        assert agg["tingkat"]["exact_pct"] == 100.0
        assert agg["macro_avg"]["exact_pct"] == 75.0


class TestEmpirical4LayerComponents:
    def test_stratified_5fold_cv(self):
        """Uji split 5-fold CV terstratifikasi."""
        dummy_certs = []
        for i in range(25):
            dummy_certs.append({
                "doc_type": "scan" if i < 15 else "embedded",
                "evaluation": {f: {"exact": True} for f in ALL_EVAL_FIELDS},
            })
        cv_res = run_stratified_5fold_cv(dummy_certs, seed=42)
        assert cv_res["k_folds"] == 5
        assert len(cv_res["fold_results"]) == 5
        assert cv_res["mean_macro_exact_pct"] == 100.0
        assert cv_res["std_dev_pct"] == 0.0

    def test_bootstrap_resampling(self):
        """Uji Bootstrap 1000x resampling."""
        dummy_certs = []
        for i in range(20):
            dummy_certs.append({
                "evaluation": {f: {"exact": (i % 2 == 0)} for f in ALL_EVAL_FIELDS},
            })
        boot_res = run_bootstrap_resampling(dummy_certs, n_bootstraps=100, seed=42)
        assert "macro_exact_95_ci" in boot_res
        lower, upper = boot_res["macro_exact_95_ci"]
        assert lower <= upper
        assert 0.0 <= lower <= 100.0

    def test_anti_hardcoding_audit(self):
        """Uji deteksi anti-hardcoding kata kunci korpus."""
        # Prompt baku harus lolos 100%
        audit_res = run_anti_hardcoding_audit(SYSTEM_INSTRUCTION_STANDARD, USER_PROMPT_TEMPLATE)
        assert audit_res["anti_hardcoding_pass"] is True
        assert len(audit_res["violations_found"]) == 0

        # Prompt dengan keyword buatan harus gagal
        bad_prompt = "Jika melihat acara SPECTA atau AIRNOLOGY, petakan ke Fakultas."
        audit_fail = run_anti_hardcoding_audit(bad_prompt, "")
        assert audit_fail["anti_hardcoding_pass"] is False
        assert "SPECTA" in audit_fail["violations_found"]
        assert "AIRNOLOGY" in audit_fail["violations_found"]

    def test_safety_net_calibration(self):
        """Uji perhitungan metrik review recall & precision."""
        dummy_certs = [
            # Cert 1: error & flagged (TP)
            {
                "evaluation": {
                    f: {"exact": (f != "nama_kegiatan_sertifikasi"), "pred": "" if f == "nama_kegiatan_sertifikasi" else "Val", "confidence": 0.0 if f == "nama_kegiatan_sertifikasi" else 0.9}
                    for f in ALL_EVAL_FIELDS
                }
            },
            # Cert 2: perfect & unflagged (TN)
            {
                "evaluation": {
                    f: {"exact": True, "pred": "24/08/2024" if "tanggal" in f else "Val", "confidence": 0.90}
                    for f in ALL_EVAL_FIELDS
                }
            },
        ]
        sn_res = run_safety_net_calibration(dummy_certs)
        assert sn_res["confusion_matrix"]["true_positive"] == 1
        assert sn_res["confusion_matrix"]["true_negative"] == 1
        assert sn_res["review_recall_pct"] == 100.0


class TestDocumentModelSchema:
    def test_parser_engine_column_length_sufficient_for_ocr_and_llm(self):
        """Regression test: parser_engine column length must safely accommodate combined tags.

        Root cause of bug: 'pymupdf_fast_path+ocr_date_check+gemini-3.1-flash-lite' (54 chars)
        overflowed String(50). Column must be at least 150 chars.
        """
        from app.models import Document

        col_type = Document.__table__.c.parser_engine.type
        assert col_type.length >= 150

        tag_fast_path = "pymupdf_fast_path+gemini-3.1-flash-lite"
        tag_ocr_fallback = "pymupdf_fast_path+ocr_date_check+gemini-3.1-flash-lite"
        tag_combined = "pymupdf_fast_path+ocr_date_check+gemini-3.1-flash-lite+combined_v4_2"

        for tag in [tag_fast_path, tag_ocr_fallback, tag_combined]:
            assert len(tag) <= col_type.length
            doc = Document(
                id="test-id",
                tahun_akademik="2023/2024",
                bukti_fisik="Sertifikat",
                original_file_name="test.pdf",
                mime_type="application/pdf",
                file_size=100,
                checksum_sha256="abc",
                parser_engine=tag,
            )
            assert doc.parser_engine == tag
