"""Handoff v7 Phase 4 — adaptive prompt compression.

After routing removes easy certs, this builder applies difficulty-based text
budgets + compact instructions to cut effective tokens/doc to <=200.

Reuses minimize_text/scoring from llm_extractor_v3.py. No new prompt rules —
the exact allowed values, EN department rule, HIMA/BEM rules, institution rule
and one-value output are preserved, just worded tighter.
"""

import re

from tests.llm_extractor import TINGKAT_OPTIONS, validate_tingkat
from tests.llm_extractor_v3 import (
    _context_block,
    build_prompt_tingkat_minimized,
    minimize_text,
)

PROMPT_VERSION = "v4_adaptive"

# Certificate type -> text budget (chars)
BUDGET_STRONG = 140
BUDGET_NORMAL = 200
BUDGET_POOR_OCR = 300

_INSTR = """Tentukan tingkat kegiatan. Jawab SATU opsi:
{options}

Aturan:
- EN DEPARTMENT/DEPT/STUDY PROGRAM -> Departemen/Program Studi
- BEM fakultas (BEM FEB, BEM FKM) -> Fakultas
- HIMA/Himpunan -> Departemen/Program Studi
- BEM universitas, rektorat, direktorat kemahasiswaan -> Universitas
- skala nasional -> Nasional; internasional -> Internasional
- UNIVERSITAS AIRLANGGA = institusi induk, bukan penentu
- Jawaban hanya satu nilai dari daftar, tanpa penjelasan
"""

# Variant D — middle ground: keeps option list + fallback + examples that
# the compact _INSTR dropped (caused 6 tingkat regressions vs v3 in P4), but
# trims the verbose sentence framing. Boilerplate 297 tok (v3=409, compact=258).
_MID_INSTR = """Tentukan tingkat kegiatan dari sertifikat berikut.

Opsi yang diizinkan:
- Internasional
- Nasional
- Universitas
- Fakultas
- Departemen/Program Studi
- Lainnya

PETUNJUK:
- DEPARTMENT/DEPT/STUDY PROGRAM (EN) == Departemen/Program Studi
- BEM tingkat fakultas (BEM FEB, BEM FKM, BEM FTMM) == Fakultas
- HIMA/Himpunan Mahasiswa (HIMATESDA, HIMANO) == Departemen/Program Studi
- BEM Universitas, Rektorat, Direktorat Kemahasiswaan == Universitas
- skala nasional == Nasional
- skala internasional == Internasional
- UNIVERSITAS AIRLANGGA = institusi induk, BUKAN penentu tingkat
- Jika tidak yakin, pilih yang paling mendekati
"""

_GARBLE_RE = re.compile(r"[a-z]{23,}")
_MIXED_CASE_RE = re.compile(r"[A-Z][a-z]{2,}[A-Z]")

# v8 Phase 2 (f_bias): aturan tambahan untuk mengoreksi bias bahasa Inggris.
# Versi verbose terukur menang (82.4%) vs versi terkompresi (78.4%);
# token 214/doc sedikit di atas gate 200, akurasi didahulukan.
_BIAS_LINES = [
    "- NAMA ACARA ATAU TEKS BAHASA INGGRIS TIDAK OTOMATIS berarti Internasional",
    "- Internasional HANYA jika penyelenggara/lembaganya asing (di luar Indonesia)",
    "- aturan BEM/HIMA/fakultas/universitas di atas TETAP berlaku dan diutamakan",
    "- tanpa bukti skala sama sekali, JANGAN menebak Internasional;",
    "  pilih Fakultas atau Nasional yang paling masuk akal dari konteks",
]

# v8 Phase 2 (g_evidence): format jawaban dua baris evidence + tingkat.
_EVIDENCE_OUT = [
    "",
    "Jawab persis dalam dua baris:",
    "Evidence: <satu kalimat bukti singkat dari teks, atau 'tidak ada'>",
    "Tingkat: <satu opsi dari daftar>",
    "",
]


def _bias_instr() -> str:
    """Sisipkan aturan bias ke instruksi e_hybrid (mid untuk garble, compact lain)."""
    return "\n".join(_BIAS_LINES)


def _needs_full_tingkat_prompt(raw_text: str, organizer: str | None) -> bool:
    """True untuk kategori yang butuh prompt penuh (v3/mid), bukan compact.

    Failure action V6: dokumen berisi OCR garble (run huruf kecil panjang =
    kata tergabung tanpa spasi), field conflict (>=6 pergantian huruf besar/
    kecil dalam satu token), atau organisasi UKM (paling rentan
    disalah-artikan) -> prompt penuh; sisanya prompt compact agar total
    budget <=200 tok/doc.
    """
    if _GARBLE_RE.search(raw_text):
        return True
    if len(_MIXED_CASE_RE.findall(raw_text)) >= 6:
        return True
    if organizer and re.search(r"UKM", organizer.upper()):
        return True
    return False


def _difficulty(raw_text: str) -> str:
    """Classify cert: strong / normal / poor_ocr."""
    if _GARBLE_RE.search(raw_text):
        return "poor_ocr"
    low = raw_text.lower()
    # Strong structured evidence: clear scale or organizer phrase near top.
    if re.search(r"\b(nasional|internasional|national|international)\b", low):
        return "strong"
    return "normal"


def _budget_for(difficulty: str) -> int:
    return {
        "strong": BUDGET_STRONG,
        "normal": BUDGET_NORMAL,
        "poor_ocr": BUDGET_POOR_OCR,
    }[difficulty]


def build_prompt_tingkat_adaptive(
    raw_text: str, known_fields: dict[str, str]
) -> tuple[str, str]:
    """Variant C — compact instructions + adaptive text budget.

    Returns (prompt, minimized_text).
    """
    difficulty = _difficulty(raw_text)
    budget = _budget_for(difficulty)
    minimized = minimize_text(raw_text, max_chars=budget)

    lines = [
        _INSTR.format(options=" / ".join(TINGKAT_OPTIONS)),
        "Teks sertifikat (bagian relevan):",
        minimized,
        "",
        *_context_block(known_fields),
        "",
        "Jawaban (satu opsi, tanpa penjelasan):",
    ]
    return "\n".join(lines), minimized


def build_prompt_tingkat_mid(
    raw_text: str, known_fields: dict[str, str]
) -> tuple[str, str]:
    """Variant D — mid-ground instructions + full 300-char budget.

    Keeps the accuracy-critical phrasing v3 had (option list, fallback,
    examples) while trimming boilerplate. Returns (prompt, minimized_text).
    """
    minimized = minimize_text(raw_text)
    lines = [
        _MID_INSTR.strip(),
        "Teks sertifikat (bagian relevan):",
        minimized,
        "",
        *_context_block(known_fields),
        "",
        "Jawaban (satu opsi, tanpa penjelasan):",
    ]
    return "\n".join(lines), minimized


def build_prompt_tingkat_hybrid(
    raw_text: str, known_fields: dict[str, str]
) -> tuple[str, str]:
    """Variant E — router beresiko rendah ke LLM: prompt penuh (v3 minimized)
    untuk kategori rentan (garble/UKM/conflict), compact untuk sisanya.

    Lihat docs/handoff_v5.md failure action: "larger prompt for affected
    category, compact elsewhere". Returns (prompt, minimized_text).
    """
    organizer = (known_fields or {}).get("penyelenggara_kegiatan")
    if _needs_full_tingkat_prompt(raw_text, organizer):
        return build_prompt_tingkat_minimized(raw_text, known_fields)
    return build_prompt_tingkat_adaptive(raw_text, known_fields)


def build_prompt_tingkat_bias(
    raw_text: str, known_fields: dict[str, str]
) -> tuple[str, str]:
    """Variant F — e_hybrid + aturan bias bahasa Inggris (v8 Phase 2).

    Menambahkan: English != International, konteks institusi Indonesia menang,
    sparse-evidence guard (jangan menebak Internasional tanpa bukti).
    Returns (prompt, minimized_text).
    """
    organizer = (known_fields or {}).get("penyelenggara_kegiatan")
    if _needs_full_tingkat_prompt(raw_text, organizer):
        prompt, minimized = build_prompt_tingkat_minimized(raw_text, known_fields)
        prompt = prompt.replace(
            "Jawaban (satu opsi, tanpa penjelasan):",
            _bias_instr() + "\nJawaban (satu opsi, tanpa penjelasan):",
        )
        return prompt, minimized
    difficulty = _difficulty(raw_text)
    budget = _budget_for(difficulty)
    minimized = minimize_text(raw_text, max_chars=budget)
    lines = [
        _INSTR.format(options=" / ".join(TINGKAT_OPTIONS)),
        _bias_instr(),
        "Teks sertifikat (bagian relevan):",
        minimized,
        "",
        *_context_block(known_fields),
        "",
        "Jawaban (satu opsi, tanpa penjelasan):",
    ]
    return "\n".join(lines), minimized


def build_prompt_tingkat_evidence(
    raw_text: str, known_fields: dict[str, str]
) -> tuple[str, str]:
    """Variant G — e_hybrid + output evidence (FaR-style, arXiv 2504.02190).

    Meminta satu baris bukti singkat sebelum jawaban tingkat. Response mentah
    disimpan di calls_*.json untuk debug; value diambil dari baris 'Tingkat:'.
    Returns (prompt, minimized_text).
    """
    organizer = (known_fields or {}).get("penyelenggara_kegiatan")
    if _needs_full_tingkat_prompt(raw_text, organizer):
        prompt, minimized = build_prompt_tingkat_minimized(raw_text, known_fields)
        prompt = prompt.replace(
            "Jawaban (satu opsi, tanpa penjelasan):",
            "Jawab persis dalam dua baris:\nEvidence: <bukti singkat, atau 'tidak ada'>\nTingkat: <satu opsi>",
        )
        return prompt, minimized
    difficulty = _difficulty(raw_text)
    budget = _budget_for(difficulty)
    minimized = minimize_text(raw_text, max_chars=budget)
    lines = [
        _INSTR.format(options=" / ".join(TINGKAT_OPTIONS)),
        "Teks sertifikat (bagian relevan):",
        minimized,
        "",
        *_context_block(known_fields),
        "",
        *_EVIDENCE_OUT,
    ]
    return "\n".join(lines), minimized


_EVIDENCE_VALUE_RE = re.compile(r"Tingkat\s*[:\-]\s*([^\n]+)", re.IGNORECASE)
_EVIDENCE_LINE_RE = re.compile(r"Evidence\s*[:\-]\s*(.*)", re.IGNORECASE)


def parse_evidence_response(response: str) -> tuple[str | None, str | None]:
    """Parse 'Evidence: ... / Tingkat: X'. Returns (evidence, validated_value)."""
    response = (response or "").strip()
    m = _EVIDENCE_VALUE_RE.search(response)
    if m:
        value = validate_tingkat(m.group(1).strip())
        if value:
            ev = _EVIDENCE_LINE_RE.search(response)
            evidence = ev.group(1).strip() if ev else ""
            return evidence, value
    # fallback: validasi seluruh response
    value = validate_tingkat(response)
    if value:
        return "", value
    return "", None


if __name__ == "__main__":
    cases = [
        ("SEMINAR NASIONAL ...", "strong"),
        ("somewordswithoutanyspacesaccidentalbossung", "poor_ocr"),
        ("held in a national competition 2024", "strong"),
        ("Dies Natalis Fakultas Ekonomi", "normal"),
    ]
    for text, want in cases:
        got = _difficulty(text)
        assert got == want, (got, want)
    assert _budget_for("strong") < _budget_for("normal") < _budget_for("poor_ocr")
    assert _needs_full_tingkat_prompt(
        "AbcDef GhiJkl MnoPqrs TuvWxyz AbCdEfG AbcDefgHijK", None
    )  # 6+ mixed-case junctions
    assert _needs_full_tingkat_prompt("aaaaaaaaaaaaaaaaaaaaaaaaa", None)  # lc run >= 23
    assert _needs_full_tingkat_prompt("seminar", "UKM Robotika")
    assert not _needs_full_tingkat_prompt("SEMINAR NASIONAL BEM", None)
    known = {"penyelenggara_kegiatan": "BEM FEB UNAIR", "raw_role": "PESERTA"}
    prompt, mini = build_prompt_tingkat_adaptive(
        "SERTIFIKAT\nSEMINAR NASIONAL\nBEM FEB UNAIR\nPESERTA", known
    )
    assert "Departemen/Program Studi" in prompt
    assert "BEM fakultas" in prompt
    assert len(mini) <= BUDGET_NORMAL
    prompt_mid, mini_mid = build_prompt_tingkat_mid(
        "SERTIFIKAT\nSEMINAR NASIONAL\nBEM FEB UNAIR\nPESERTA", known
    )
    assert "HIMATESDA" in prompt_mid
    assert "paling mendekati" in prompt_mid
    assert "Internasional" in prompt_mid
    prompt_hyb, mini_hyb = build_prompt_tingkat_hybrid(
        "SERTIFIKAT\nSEMINAR NASIONAL\nBEM FEB UNAIR\nPESERTA", known
    )
    assert prompt_hyb == prompt  # normal cert -> compact
    prompt_hyb2, _ = build_prompt_tingkat_hybrid(
        "somebrokenwordsacrosstheline\nSEMINAR\nBEM FEB UNAIR\nPESERTA", known
    )
    assert prompt_hyb2 != prompt  # garble -> full
    prompt_bias, mini_bias = build_prompt_tingkat_bias(
        "SERTIFIKAT\nENGLISH SEMINAR\nBEM FEB UNAIR\nPESERTA", known
    )
    assert "TIDAK OTOMATIS" in prompt_bias
    assert len(mini_bias) <= BUDGET_NORMAL
    prompt_ev, mini_ev = build_prompt_tingkat_evidence(
        "SERTIFIKAT\nSEMINAR NASIONAL\nBEM FEB UNAIR\nPESERTA", known
    )
    assert "Evidence:" in prompt_ev and "Tingkat:" in prompt_ev
    ev, val = parse_evidence_response("Evidence: LOMBA NASIONAL\nTingkat: Nasional")
    assert ev == "LOMBA NASIONAL" and val == "Nasional", (ev, val)
    ev2, val2 = parse_evidence_response("Tingkat: Fakultas")
    assert ev2 == "" and val2 == "Fakultas", (ev2, val2)
    ev3, val3 = parse_evidence_response("Departemen/Program Studi")
    assert val3 == "Departemen/Program Studi", val3
    print("ok: adaptive builder")
