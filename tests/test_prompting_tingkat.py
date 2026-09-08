"""Unit tests untuk 5 teknik prompting tingkat sertifikat."""

import pytest
from tests.prompting_tingkat import (
    TINGKAT_OPTIONS,
    build_zero_shot_prompt,
    build_few_shot_prompt,
    build_cot_prompt,
    validate_tingkat,
    run_self_consistency,
    run_iterative_prompting,
)


def test_zero_shot_prompt_structure():
    raw_text = "Diberikan sertifikat atas partisipasi sebagai peserta lomba."
    known = {"nama_kegiatan_sertifikasi": "Lomba AI", "penyelenggara_kegiatan": "BEM"}
    prompt = build_zero_shot_prompt(raw_text, known)

    assert "Pilihan Tingkat yang Valid:" in prompt
    for opt in TINGKAT_OPTIONS:
        assert opt in prompt
    assert "Lomba AI" in prompt
    assert "BEM" in prompt
    assert raw_text in prompt
    assert prompt.endswith("Jawaban:")


def test_few_shot_prompt_no_dataset_leakage():
    raw_text = "Sertifikat keikutsertaan kompetisi."
    prompt = build_few_shot_prompt(raw_text)

    # Verifikasi tidak ada kebocoran nama event/file dari dataset nyata
    forbidden_dataset_names = [
        "Data Slayer",
        "Airnology",
        "Dataquest",
        "Dekan Cup",
        "Amerta",
        "Karsa",
        "Binary",
        "Elzandi",
    ]
    for name in forbidden_dataset_names:
        assert name.lower() not in prompt.lower(), f"Leakage detected: {name} in few-shot prompt"

    assert "CONTOH 1:" in prompt
    assert "Tingkat: Nasional" in prompt
    assert prompt.endswith("Tingkat:")


def test_cot_prompt_steps_instruction():
    raw_text = "Sertifikat webinar nasional."
    prompt = build_cot_prompt(raw_text)

    assert "ATURAN PENALARAN (Chain of Thought):" in prompt
    assert "Langkah 1" in prompt
    assert "Langkah 2" in prompt
    assert "Langkah 3" in prompt
    assert "Langkah 4" in prompt
    assert "TINGKAT:" in prompt


def test_validate_tingkat_exact_and_canonical():
    assert validate_tingkat("Nasional") == "Nasional"
    assert validate_tingkat("Fakultas") == "Fakultas"
    assert validate_tingkat("Departemen/Program Studi") == "Departemen/Program Studi"
    assert validate_tingkat("Universitas") == "Universitas"
    assert validate_tingkat("Internasional") == "Internasional"
    assert validate_tingkat("Lainnya") == "Lainnya"


def test_validate_tingkat_structured_responses():
    resp_cot = """Langkah 1: Penyelenggara adalah BEM Fakultas Teknik
Langkah 2: Kegiatan adalah kompetisi terbuka se-Indonesia
Langkah 3: Cakupan sasaran peserta bersifat nasional
Langkah 4: Kesimpulan adalah nasional
TINGKAT: Nasional"""
    assert validate_tingkat(resp_cot) == "Nasional"

    resp_markdown = "```\nFakultas\n```"
    assert validate_tingkat(resp_markdown) == "Fakultas"


def test_validate_tingkat_rejects_ambiguous_and_empty():
    assert validate_tingkat("") is None
    assert validate_tingkat(None) is None
    assert validate_tingkat("Tidak ada informasi tingkat di sertifikat ini.") is None
    assert validate_tingkat("Bisa jadi regional atau tingkat kota.") is None


def test_self_consistency_majority_vote():
    # 2 suara 'Nasional' dan 1 suara 'Fakultas' (majority, tapi confidence 0.67 < 0.85 -> review)
    responses = [
        "TINGKAT: Nasional",
        "TINGKAT: Fakultas",
        "TINGKAT: Nasional",
    ]
    call_idx = 0

    def mock_llm(prompt: str, temp: float) -> str:
        nonlocal call_idx
        resp = responses[call_idx % len(responses)]
        call_idx += 1
        return resp

    res = run_self_consistency("Teks sertifikat", None, mock_llm, n_samples=3)
    assert res.tingkat == "Nasional"
    assert res.confidence == pytest.approx(2 / 3)
    assert res.needs_review is True
    assert res.technique == "self-consistency"


def test_self_consistency_unanimous_no_review():
    # 3 suara bulat 'Nasional' (confidence 1.0 >= 0.85 -> no review)
    def mock_llm(prompt: str, temp: float) -> str:
        return "TINGKAT: Nasional"

    res = run_self_consistency("Teks sertifikat", None, mock_llm, n_samples=3)
    assert res.tingkat == "Nasional"
    assert res.confidence == 1.0
    assert res.needs_review is False


def test_self_consistency_tie_vote_handling():
    # 1 suara 'Nasional', 1 suara 'Fakultas' (tie eksplisit)
    responses = [
        "TINGKAT: Nasional",
        "TINGKAT: Fakultas",
    ]
    call_idx = 0

    def mock_llm(prompt: str, temp: float) -> str:
        nonlocal call_idx
        resp = responses[call_idx % len(responses)]
        call_idx += 1
        return resp

    res = run_self_consistency("Teks sertifikat", None, mock_llm, n_samples=2)
    assert res.tingkat is None
    assert res.confidence == 0.5
    assert res.needs_review is True
    assert res.metadata.get("is_tie") is True


def test_self_consistency_invalid_n_samples():
    with pytest.raises(ValueError, match="n_samples harus >= 1"):
        run_self_consistency("Teks sertifikat", None, lambda p, t: "", n_samples=0)

def test_self_consistency_all_invalid():
    def mock_llm_invalid(prompt: str, temp: float) -> str:
        return "Saya tidak tahu tingkat kegiatannya."

    res = run_self_consistency("Teks sertifikat", None, mock_llm_invalid, n_samples=3)
    assert res.tingkat is None
    assert res.confidence == 0.0
    assert res.needs_review is True


def test_iterative_prompting_coherent_path():
    step_outputs = [
        # Step 1: Ekstraksi
        "- Nama Kegiatan: Data Science Hackathon\n- Penyelenggara: BEM FTMM\n- Jenis Kegiatan: Lomba/Kompetisi",
        # Step 2: Cakupan
        "Kegiatan ini merupakan lomba terbuka berskala Nasional untuk mahasiswa seluruh Indonesia.",
        # Step 3: Final Tingkat
        "TINGKAT: Nasional",
    ]
    call_idx = 0

    def mock_llm(prompt: str, temp: float) -> str:
        nonlocal call_idx
        out = step_outputs[call_idx]
        call_idx += 1
        return out

    res = run_iterative_prompting("Teks sertifikat", None, mock_llm)
    assert res.tingkat == "Nasional"
    assert res.confidence == 0.80
    # Karena confidence 0.80 < 0.85 (konservatif sebelum kalibrasi), needs_review tetap True
    assert res.needs_review is True
    assert len(res.reasoning_steps) == 3


def test_iterative_prompting_incoherent_review_flag():
    step_outputs = [
        "- Nama Kegiatan: Rapat internal\n- Penyelenggara: Panitia\n- Jenis Kegiatan: Internal",
        "Kegiatan ini tidak jelas cakupan wilayahnya dan ambigu.",
        "TINGKAT: Lainnya",
    ]
    call_idx = 0

    def mock_llm(prompt: str, temp: float) -> str:
        nonlocal call_idx
        out = step_outputs[call_idx]
        call_idx += 1
        return out

    res = run_iterative_prompting("Teks sertifikat", None, mock_llm)
    assert res.tingkat == "Lainnya"
    assert res.needs_review is True
    assert res.confidence < 0.85

def test_load_ocr_texts_map_marker_format(tmp_path):
    from pathlib import Path
    from tests.benchmark_prompting_tingkat import load_ocr_texts_map

    marker_file = tmp_path / "sample_extracted.txt"
    marker_file.write_text(
        "========== doc1.pdf ==========\n"
        "Teks sertifikat 1\n\n"
        "========== doc2.pdf ==========\n"
        "Teks sertifikat 2\n",
        encoding="utf-8",
    )
    t_map = load_ocr_texts_map(marker_file)
    assert "doc1.pdf" in t_map
    assert t_map["doc1.pdf"] == "Teks sertifikat 1"
    assert "doc2.pdf" in t_map
    assert t_map["doc2.pdf"] == "Teks sertifikat 2"


def test_load_ocr_texts_map_missing_file():
    from pathlib import Path
    from tests.benchmark_prompting_tingkat import load_ocr_texts_map

    with pytest.raises(FileNotFoundError, match="Sumber teks OCR tidak ditemukan"):
        load_ocr_texts_map(Path("non_existent_dir_or_file_xyz.txt"))


def test_load_ocr_texts_map_conflict_detection(tmp_path):
    from tests.benchmark_prompting_tingkat import load_ocr_texts_map

    marker_file = tmp_path / "conflict.txt"
    marker_file.write_text(
        "========== doc1.pdf ==========\n"
        "Teks versi 1\n"
        "========== doc1.pdf ==========\n"
        "Teks versi 2 yang berbeda\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Deteksi duplikasi/konflik"):
        load_ocr_texts_map(marker_file)
