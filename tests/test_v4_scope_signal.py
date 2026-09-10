"""Unit tests for V4 Scope Signal Prompting Architecture (EXP-ALL6F-PROMPT-001 V4)."""

import json
from pathlib import Path
from typing import Any

from tests.benchmark_all6f_prompting import (
    ALL_6_FIELDS,
    V4_SYSTEM_INSTRUCTION,
    V4_USER_PROMPT_TEMPLATE,
    normalize_llm_json,
    run_gemini_inference,
    run_mock_inference,
    write_comparative_summary_md,
)
from tests.gemini_client import GeminiCallResult


class TestV4PromptContract:
    def test_v4_prompt_templates_exist_and_format(self) -> None:
        """Memastikan prompt instruction dan user template V4 terdefinisi dan dapat di-format."""
        assert "pola_cakupan" in V4_SYSTEM_INSTRUCTION
        assert "TERBUKA_SE_INDONESIA" in V4_SYSTEM_INSTRUCTION
        assert "INTERNAL_KAMPUS" in V4_SYSTEM_INSTRUCTION
        assert "INTERNASIONAL" in V4_SYSTEM_INSTRUCTION
        assert "TIDAK_DITEMUKAN" in V4_SYSTEM_INSTRUCTION

        formatted = V4_USER_PROMPT_TEMPLATE.format(raw_ocr_text="SAMPLE OCR TEXT 123")
        assert "SAMPLE OCR TEXT 123" in formatted
        assert "pola_cakupan" in formatted
        assert "tingkat" in formatted

    def test_in_json_signal_extraction_and_stripping(self) -> None:
        """Memastikan pola_cakupan dapat diekstrak untuk audit lalu di-strip sebelum evaluasi 6F."""
        raw_response = {
            "nama_kegiatan_sertifikasi": "Lomba Hackathon Nasional 2025",
            "nomor_bukti_fisik_nomor_sertifikasi": "001/HACK/2025",
            "penyelenggara_kegiatan": "BEM Fakultas Teknologi Maju",
            "waktu_mulai_pelaksanaan": "15/05/2025",
            "waktu_selesai_pelaksanaan": "16/05/2025",
            "raw_role": "Juara 1",
            "pola_cakupan": "TERBUKA_SE_INDONESIA",
            "tingkat": "Nasional",
        }

        # Simulasi alur V4 di run_gemini_inference
        parsed_copy = dict(raw_response)
        pola_cakupan_audit = parsed_copy.pop("pola_cakupan", None)

        assert pola_cakupan_audit == "TERBUKA_SE_INDONESIA"
        assert "pola_cakupan" not in parsed_copy

        # Normalisasi ke format 6-field
        norm = normalize_llm_json(parsed_copy)

        # Pastikan key evaluator strictly ALL_6_FIELDS
        for f in ALL_6_FIELDS:
            assert f in norm
        assert "pola_cakupan" not in norm
        assert norm["tingkat"] == "Nasional"
        assert norm["nama_kegiatan_sertifikasi"] == "Lomba Hackathon Nasional 2025"

    def test_pola_cakupan_validity_and_discordance(self) -> None:
        """Memastikan audit validitas enum, needs_review, dan deteksi diskordansi."""
        class MockClientSuccess:
            def __init__(self, payload: dict[str, Any]) -> None:
                self.payload = payload

            def generate_json(self, **kwargs: Any) -> GeminiCallResult:
                return GeminiCallResult(
                    response_text=json.dumps(self.payload),
                    parsed_json=self.payload,
                    prompt_tokens=150,
                    candidates_tokens=40,
                    cached_tokens=0,
                    thoughts_tokens=0,
                    total_tokens=190,
                    cost_usd=0.0001,
                    cost_idr=1.5,
                    latency_s=0.4,
                    model="gemini-3.1-flash-lite",
                    status="success",
                )

        # Kasus 1: Konsisten (TERBUKA_SE_INDONESIA -> Nasional)
        payload1 = {"pola_cakupan": "TERBUKA_SE_INDONESIA", "tingkat": "Nasional"}
        _, meta1 = run_gemini_inference("v4_scope_signal", "sample", MockClientSuccess(payload1), "gemini-3.1-flash-lite")
        assert meta1["pola_cakupan"] == "TERBUKA_SE_INDONESIA"
        assert meta1["pola_is_valid"] is True
        assert meta1["pola_discordance"] is False
        assert meta1["needs_review"] is False

        # Kasus 2: Diskordan (TERBUKA_SE_INDONESIA -> Fakultas) -> picu needs_review
        payload2 = {"pola_cakupan": "TERBUKA_SE_INDONESIA", "tingkat": "Fakultas"}
        _, meta2 = run_gemini_inference("v4_scope_signal", "sample", MockClientSuccess(payload2), "gemini-3.1-flash-lite")
        assert meta2["pola_cakupan"] == "TERBUKA_SE_INDONESIA"
        assert meta2["pola_is_valid"] is True
        assert meta2["pola_discordance"] is True
        assert meta2["needs_review"] is True

        # Kasus 3: Invalid enum -> picu needs_review
        payload3 = {"pola_cakupan": "ASUMSI_SENDIRI", "tingkat": "Nasional"}
        _, meta3 = run_gemini_inference("v4_scope_signal", "sample", MockClientSuccess(payload3), "gemini-3.1-flash-lite")
        assert meta3["pola_cakupan"] == "ASUMSI_SENDIRI"
        assert meta3["pola_is_valid"] is False
        assert meta3["needs_review"] is True

    def test_fail_closed_on_none_or_malformed(self) -> None:
        """Memastikan respons kosong/malformed ditangani secara fail-closed pada run_gemini_inference."""
        class MockGeminiClientFail:
            def generate_json(self, **kwargs: Any) -> GeminiCallResult:
                return GeminiCallResult(
                    response_text="",
                    parsed_json=None,
                    prompt_tokens=100,
                    candidates_tokens=0,
                    cached_tokens=0,
                    thoughts_tokens=0,
                    total_tokens=100,
                    cost_usd=0.0,
                    cost_idr=0.0,
                    latency_s=0.5,
                    model="gemini-3.1-flash-lite",
                    status="error",
                    error_message="JSON parse error",
                )

        norm_fields, meta = run_gemini_inference(
            variant="v4_scope_signal",
            raw_text="Random text",
            client=MockGeminiClientFail(),
            model="gemini-3.1-flash-lite",
        )
        assert meta["status"] == "error"
        assert meta["error"] == "JSON parse error"
        assert meta["pola_cakupan"] is None
        assert meta["needs_review"] is True
        for f in ALL_6_FIELDS:
            assert norm_fields.get(f) is None

    def test_run_mock_inference_v4_heuristics(self) -> None:
        """Memastikan mock inference V4 dapat dieksekusi tanpa menyalin ground truth secara naif."""
        doc_info = {
            "Nama Kegiatan Sertifikasi": "Seminar Nasional AI",
            "Nomor Bukti Fisik Nomor Sertifikasi": "123/SN/2024",
            "Penyelenggara Kegiatan": "BEM FTMM",
            "Waktu Mulai Pelaksanaan": "10/10/2024",
            "Waktu Selesai Pelaksanaan": "10/10/2024",
            "Tingkat": "Nasional",
        }
        raw_text = "Seminar Nasional AI untuk Indonesia Maju diselenggarakan oleh BEM FTMM"
        fields, meta = run_mock_inference("v4_scope_signal", raw_text, doc_info)

        assert fields["tingkat"] == "Nasional"
        assert fields["nama_kegiatan_sertifikasi"] == "Seminar Nasional AI"
        assert fields["nomor_bukti_fisik_nomor_sertifikasi"] == "123/SN/2024"
        assert fields["penyelenggara_kegiatan"] == "BEM FTMM"
        assert meta["status"] == "success"
        for f in ALL_6_FIELDS:
            assert f in fields

    def test_write_comparative_summary_dynamic_paired_v2_v4(self, tmp_path: Path) -> None:
        """Memastikan summary markdown dinamis berjalan mulus pada paired run V2 vs V4 tanpa V1."""
        dummy_slice = {
            "n_docs": 10,
            "all_cells_6f": {"exact_pct": 70.0, "fuzzy_pct": 75.0},
            "framework_5f": {"exact_pct": 80.0, "fuzzy_pct": 82.0},
            "per_field": {f: {"exact_pct": 75.0} for f in ALL_6_FIELDS},
            "confusion_tingkat": {"nasional_to_fakultas_count": 1},
            "tokens_and_cost": {
                "eff_tokens_per_doc": 1200.0,
                "total_cost_idr": 150.0,
                "projection_100k_certs_idr": 1500000.0,
            },
        }
        summary = {
            "is_complete": True,
            "completed_evaluations": 20,
            "expected_evaluations": 20,
            "total_docs_fully_evaluated": 10,
            "target_universe_documents": 10,
            "model": "gemini-3.1-flash-lite",
            "backend": "gemini",
            "gt_path": "Ground_Truth_Sertifikat_v9.csv",
            "variants": {
                "v2_scope_aware": {
                    "unified_full": dummy_slice,
                    "train_v9": dummy_slice,
                    "test_elzandi": dummy_slice,
                },
                "v4_scope_signal": {
                    "unified_full": dummy_slice,
                    "train_v9": dummy_slice,
                    "test_elzandi": dummy_slice,
                },
            },
        }
        out_file = tmp_path / "comparative_summary.md"
        write_comparative_summary_md(out_file, summary)

        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "Varian 2 (Scope-Aware)" in content
        assert "Varian 4 (Scope Signal)" in content
        assert "Varian 1 (Baseline)" not in content
        assert "Varian 3 (Decoupled 2-Stage)" not in content
        assert "N=10" in content
        assert "Ground_Truth_Sertifikat_v9.csv" in content

        # Cek konsistensi kolom tabel markdown: jumlah header sama dengan separator
        lines = content.splitlines()
        for idx, line in enumerate(lines):
            if line.startswith("| Metrik Evaluasi |"):
                headers = [c.strip() for c in line.split("|")[1:-1]]
                assert len(headers) == 3  # Metrik + V2 + V4
                # Cek separator tepat di bawah header Metrik Evaluasi
                sep_line = lines[idx + 1]
                seps = [c.strip() for c in sep_line.split("|")[1:-1]]
                assert len(seps) == len(headers)
