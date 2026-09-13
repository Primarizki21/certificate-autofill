"""Unit tests for V5 Natural Rationale Architecture (EXP-ALL6F-PROMPT-005)."""

import json
from typing import Any

from tests.benchmark_all6f_prompting import (
    ALL_6_FIELDS,
    V5_SYSTEM_INSTRUCTION,
    V5_USER_PROMPT_TEMPLATE,
    normalize_llm_json,
    run_gemini_inference,
    run_mock_inference,
)
from tests.gemini_client import GeminiCallResult


class TestV5PromptContract:
    def test_v5_prompt_templates_exist_and_format(self) -> None:
        """Memastikan prompt instruction dan user template V5 terdefinisi dan dapat di-format."""
        assert "pertimbangan_tingkat" in V5_SYSTEM_INSTRUCTION
        assert "Chain-of-Thought" in V5_SYSTEM_INSTRUCTION or "penalaran" in V5_SYSTEM_INSTRUCTION
        assert "Nasional" in V5_SYSTEM_INSTRUCTION
        assert "Internasional" in V5_SYSTEM_INSTRUCTION

        formatted = V5_USER_PROMPT_TEMPLATE.format(raw_ocr_text="SAMPLE OCR TEXT 123")
        assert "SAMPLE OCR TEXT 123" in formatted
        assert "pertimbangan_tingkat" in formatted
        assert "tingkat" in formatted

    def test_in_json_rationale_extraction_and_stripping(self) -> None:
        """Memastikan pertimbangan_tingkat dapat diekstrak untuk audit lalu di-strip sebelum evaluasi 6F."""
        raw_response = {
            "nama_kegiatan_sertifikasi": "Lomba Hackathon Nasional 2025",
            "nomor_bukti_fisik_nomor_sertifikasi": "001/HACK/2025",
            "penyelenggara_kegiatan": "BEM Fakultas Teknologi Maju",
            "waktu_mulai_pelaksanaan": "15/05/2025",
            "waktu_selesai_pelaksanaan": "16/05/2025",
            "raw_role": "Juara 1",
            "pertimbangan_tingkat": "1. Penyelenggara: BEM Fakultas. 2. Sifat: Lomba terbuka nasional se-Indonesia. 3. Skala peserta mengalahkan hierarki penyelenggara.",
            "tingkat": "Nasional",
        }

        parsed_copy = dict(raw_response)
        rationale_audit = parsed_copy.pop("pertimbangan_tingkat", None)

        assert rationale_audit is not None
        assert "Lomba terbuka nasional" in rationale_audit
        assert "pertimbangan_tingkat" not in parsed_copy

        norm = normalize_llm_json(parsed_copy)

        # Evaluator strictly hanya memeriksa ALL_6_FIELDS
        for f in ALL_6_FIELDS:
            assert f in norm
        assert "pertimbangan_tingkat" not in norm
        assert norm["tingkat"] == "Nasional"
        assert norm["nama_kegiatan_sertifikasi"] == "Lomba Hackathon Nasional 2025"

    def test_fallback_alias_extraction(self) -> None:
        """Memastikan varian alias field (analisis_tingkat, penalaran) tetap tertangkap."""
        class MockClientAlias:
            def __init__(self, key: str) -> None:
                self.key = key

            def generate_json(self, **kwargs: Any) -> GeminiCallResult:
                payload = {
                    "nama_kegiatan_sertifikasi": "Dataquest 4.0",
                    "nomor_bukti_fisik_nomor_sertifikasi": "123/DQ/2024",
                    "penyelenggara_kegiatan": "BEM FTMM UNAIR",
                    "waktu_mulai_pelaksanaan": "24/08/2024",
                    "waktu_selesai_pelaksanaan": "24/08/2024",
                    "raw_role": "Peserta",
                    self.key: "Penalaran singkat untuk tingkat",
                    "tingkat": "Nasional",
                }
                return GeminiCallResult(
                    response_text=json.dumps(payload),
                    parsed_json=payload,
                    prompt_tokens=200,
                    candidates_tokens=50,
                    cached_tokens=0,
                    thoughts_tokens=0,
                    total_tokens=250,
                    cost_usd=0.0001,
                    cost_idr=1.5,
                    latency_s=0.5,
                    model="gemini-3.1-flash-lite",
                    status="success",
                )

        # Test alias 'analisis_tingkat'
        fields1, meta1 = run_gemini_inference("v5_natural_rationale", "sample", MockClientAlias("analisis_tingkat"), "gemini-3.1-flash-lite")
        assert meta1["pertimbangan_tingkat"] == "Penalaran singkat untuk tingkat"
        assert meta1["has_rationale"] is True
        assert fields1["tingkat"] == "Nasional"

        # Test alias 'penalaran'
        fields2, meta2 = run_gemini_inference("v5_natural_rationale", "sample", MockClientAlias("penalaran"), "gemini-3.1-flash-lite")
        assert meta2["pertimbangan_tingkat"] == "Penalaran singkat untuk tingkat"
        assert meta2["has_rationale"] is True
        assert fields2["tingkat"] == "Nasional"

    def test_v5_mock_inference_determinism(self) -> None:
        """Memastikan mock inference untuk v5 berjalan deterministik dan menghasilkan 6 field standar."""
        raw_text = "Sertifikat Dataquest 4.0 kompetisi sains data tingkat nasional se-Indonesia."
        fields, meta = run_mock_inference("v5_natural_rationale", raw_text)

        for f in ALL_6_FIELDS:
            assert f in fields
        assert fields["tingkat"] == "Nasional"
        assert meta["status"] == "success"
        assert meta["latency_s"] > 0
