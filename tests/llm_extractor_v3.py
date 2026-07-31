"""Handoff v6 — token-minimized LLM extraction for tingkat (Variant A/B).

Calls the LLM ONLY for `tingkat` (the field the hybrid pipeline never
extracts), using context-only (A) or context + relevant lines (B).

Reuses the Ollama client, validators and token logger from llm_extractor.py.
"""

import json
import re
from typing import Any

from tests.llm_extractor import (
    TINGKAT_OPTIONS,
    call_ollama,
    log_call,
    validate_tingkat,
    build_token_usage_summary,
    TokenUsage,
)

PROMPT_VERSION = "v3_tingkat_only"

KNOWN_FIELD_LABELS = [
    ("nama_kegiatan_sertifikasi", "Nama Kegiatan"),
    ("penyelenggara_kegiatan", "Penyelenggara"),
    ("raw_role", "Peran"),
]

# ---------------------------------------------------------------------------
# minimize_text() — keep only lines relevant to tingkat determination.
# Data-driven scoring so it can be tuned per experiment and dumped to results.
# ---------------------------------------------------------------------------

MINIMIZE_CONFIG = {
    "max_chars": 300,
    "keep_score": 2,
    "fallback_score": 1,
    "weights": {
        "organizer": 4,
        "organizer_phrase": 3,
        "scale": 3,
        "tingkat_line": 5,
        "role": 2,
        "date": 1,
        "cert": 1,
        "noise": -5,
        "garbled": -3,
    },
    "organizer_keywords": [
        "BEM", "BADAN EKSEKUTIF", "HIMA", "HIMPUNAN", "UKM",
        "UNIT KEGIATAN", "AIESEC", "REKTORAT", "DIREKTORAT",
        "KEMAHASISWAAN", "FAKULTAS", "DEPARTEMEN", "PRODI",
        "SEMA", "SENAT", "LEMBAGA", "UNIVERSITAS",
        "ORGANIZING COMMITTEE", "ORGANIZER",
    ],
    "organizer_phrases": [
        "DISELENGGARAKAN", "DIADAKAN", "ORGANIZED", "HELD BY",
    ],
    "scale_keywords": [
        "NASIONAL", "INTERNASIONAL", "INTERNATIONAL", "NATIONAL",
        "LOMBA", "KOMPETISI", "COMPETITION", "OLIMPIADE",
        "KONFERENSI", "CONFERENCE",
    ],
    "tingkat_pattern": r"TINGKAT\s+[A-Z/ ]{3,}",
    "role_keywords": [
        "PESERTA", "PANITIA", "KETUA", "PRESIDEN", "PENGURUS",
        "ANGGOTA", "PARTISIPASI", "PARTICIPANT", "SEBAGAI",
    ],
    "date_pattern": (
        r"\d{1,2}[\s/-](JANUARI|FEBRUARI|MARET|APRIL|MEI|JUNI|JULI|"
        r"AGUSTUS|SEPTEMBER|OKTOBER|NOVEMBER|DESEMBER|JAN|FEB|MAR|"
        r"APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|[A-Z][a-z]+)[\s/-]\d{2,4}"
    ),
    "cert_pattern": r"\b\d{2,4}/[A-Z0-9.]+/[A-Z0-9./]+/\d{4}\b",
    "noise_patterns": [
        r"\b(NIM|NIP|NIK)\s*[:.]?\s*\d",
    ],
}

_DATE_RE = re.compile(MINIMIZE_CONFIG["date_pattern"], re.IGNORECASE)
_CERT_RE = re.compile(MINIMIZE_CONFIG["cert_pattern"])
_TINGKAT_RE = re.compile(MINIMIZE_CONFIG["tingkat_pattern"], re.IGNORECASE)
_NOISE_RES = [
    re.compile(p, re.IGNORECASE) for p in MINIMIZE_CONFIG["noise_patterns"]
]


def _looks_garbled(line: str) -> bool:
    s = line.strip()
    if not s or len(s) < 3:
        return True
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(c.isupper() for c in letters) / len(letters)
    if " " not in s:
        return upper_ratio > 0.5 and len(s) > 8
    return upper_ratio > 0.95 and len(s) > 20


def score_line(line: str, cfg: dict | None = None) -> int:
    """Relevance score of one line for tingkat determination."""
    cfg = cfg or MINIMIZE_CONFIG
    s = line.strip()
    if not s:
        return 0
    upper = s.upper()
    w = cfg["weights"]
    score = 0
    if any(kw in upper for kw in cfg["organizer_keywords"]):
        score += w["organizer"]
    if any(ph in upper for ph in cfg["organizer_phrases"]):
        score += w["organizer_phrase"]
    if any(kw in upper for kw in cfg["scale_keywords"]):
        score += w["scale"]
    if _TINGKAT_RE.search(s):
        score += w["tingkat_line"]
    if any(kw in upper for kw in cfg["role_keywords"]):
        score += w["role"]
    if _DATE_RE.search(s):
        score += w["date"]
    if _CERT_RE.search(s):
        score += w["cert"]
    if any(r.search(s) for r in _NOISE_RES):
        score += w["noise"]
    if _looks_garbled(s):
        score += w["garbled"]
    return score


def minimize_text(
    raw_text: str, cfg: dict | None = None, max_chars: int | None = None
) -> str:
    """Keep only lines relevant to tingkat, in original order, capped by budget.

    Falls back to looser scoring, then to a short prefix, so it never returns
    empty regardless of certificate format.
    """
    cfg = cfg or MINIMIZE_CONFIG
    max_chars = max_chars or cfg["max_chars"]
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]

    selected = [
        (score_line(l, cfg), l) for l in lines
        if score_line(l, cfg) >= cfg["keep_score"]
    ]
    if not selected:
        selected = [
            (score_line(l, cfg), l) for l in lines
            if score_line(l, cfg) >= cfg["fallback_score"]
        ]
    if not selected:
        return raw_text.strip()[:max_chars]

    out = []
    used = 0
    for _, line in sorted(selected, key=lambda x: lines.index(x[1])):
        if used + len(line) + 1 > max_chars:
            continue
        out.append(line)
        used += len(line) + 1
    return "\n".join(out)


def debug_minimize(raw_text: str, cfg: dict | None = None) -> list[dict]:
    """Per-line decisions — useful for tuning on new certificate variants."""
    cfg = cfg or MINIMIZE_CONFIG
    out = []
    for i, line in enumerate(raw_text.split("\n")):
        s = line.strip()
        if not s:
            continue
        score = score_line(s, cfg)
        out.append({
            "index": i,
            "score": score,
            "keep": score >= cfg["keep_score"],
            "line": s,
        })
    return out


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _context_block(known_fields: dict[str, str]) -> list[str]:
    lines = ["Field yang sudah diketahui (dari pipeline):"]
    for key, label in KNOWN_FIELD_LABELS:
        val = known_fields.get(key) or "tidak diketahui"
        lines.append(f"- {label}: {val}")
    return lines


def build_prompt_tingkat_context(known_fields: dict[str, str]) -> str:
    """Variant A — context-only, no raw text."""
    lines = [
        "Tentukan tingkat kegiatan dari informasi berikut.",
        "",
        "ATURAN WAJIB:",
        "- Jawaban HARUS persis salah satu dari opsi di bawah",
        "- JANGAN jawab selain opsi ini",
        "- Jika tidak yakin, pilih yang paling mendekati",
        "",
        "PETUNJUK TINGKAT:",
        "- Jika diselenggarakan oleh BEM/Badan Eksekutif Mahasiswa tingkat FAKULTAS (BEM FEB, BEM FKM, BEM FTMM), maka == Fakultas",
        "- Jika diselenggarakan oleh HIMA/Himpunan Mahasiswa (HIMATESDA, HIMANO), maka == Departemen/Program Studi",
        "- Jika diselenggarakan oleh BEM Universitas, Rektorat, Direktorat Kemahasiswaan, maka == Universitas",
        "- Jika kegiatan berskala nasional, maka == Nasional",
        "- Jika kegiatan berskala internasional, maka == Internasional",
        "- 'UNIVERSITAS AIRLANGGA' adalah institusi induk, BUKAN penentu tingkat",
        "",
        "Opsi yang diizinkan:",
    ]
    for opt in TINGKAT_OPTIONS:
        lines.append(f"- {opt}")
    lines.extend([
        "",
        *_context_block(known_fields),
        "",
        "Jawaban (hanya satu opsi dari daftar, tanpa penjelasan):",
    ])
    return "\n".join(lines)


def build_prompt_tingkat_minimized(
    raw_text: str, known_fields: dict[str, str]
) -> tuple[str, str]:
    """Variant B — context + minimize_text(raw_text).

    Returns (prompt, minimized_text) so the benchmark can log compression stats.
    """
    minimized = minimize_text(raw_text)
    lines = [
        "Tentukan tingkat kegiatan dari sertifikat berikut.",
        "",
        "ATURAN WAJIB:",
        "- Jawaban HARUS persis salah satu dari opsi di bawah",
        "- JANGAN jawab selain opsi ini",
        "- Jika tidak yakin, pilih yang paling mendekati",
        "",
        "PETUNJUK TINGKAT:",
        "- Jika diselenggarakan oleh BEM/Badan Eksekutif Mahasiswa tingkat FAKULTAS (BEM FEB, BEM FKM, BEM FTMM), maka == Fakultas",
        "- Jika diselenggarakan oleh HIMA/Himpunan Mahasiswa (HIMATESDA, HIMANO), maka == Departemen/Program Studi",
        "- Jika diselenggarakan oleh BEM Universitas, Rektorat, Direktorat Kemahasiswaan, maka == Universitas",
        "- Jika kegiatan berskala nasional, maka == Nasional",
        "- Jika kegiatan berskala internasional, maka == Internasional",
        "- 'UNIVERSITAS AIRLANGGA' adalah institusi induk, BUKAN penentu tingkat",
        "",
        "Opsi yang diizinkan:",
    ]
    for opt in TINGKAT_OPTIONS:
        lines.append(f"- {opt}")
    lines.extend([
        "",
        "Teks sertifikat (bagian yang relevan):",
        minimized,
        "",
        *_context_block(known_fields),
        "",
        "Jawaban (hanya satu opsi dari daftar, tanpa penjelasan):",
    ])
    return "\n".join(lines), minimized


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

_SAMPLE_RAW = """# Method: pymupdf_fast_path
SERTIFIKAT
FARUILIASIKONOMDANBSNES
UNIVERSITASAIRLANCCA
542/A.5/SOCIAL ACTION/BEM FEB UNAIR/XI/2023
Diberikan Kepada:
Raafa Agna Rasyada
Atas partisipasinya sebagai:
PESERTA
Dalam acara Economic Week 2023 yang diselenggarakan oleh Badan Eksekutif
Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga pada tanggal
4-5 November 2023
Dekan
Prof. Dr. Dian Agustia
NIP. 196202281989112001
"""


def _demo():
    minimized = minimize_text(_SAMPLE_RAW)
    kept = minimized.split("\n")
    assert any("diselenggarakan" in l.lower() for l in kept), "lost organizer phrase"
    assert any("BEM" in l or "Badan Eksekutif" in l for l in kept), "lost organizer"
    assert not any("UNIVERSITASAIRLANCCA" in l for l in kept), "garbled line kept"
    assert not any("NIP" in l for l in kept), "noise kept"
    assert len(minimized) <= MINIMIZE_CONFIG["max_chars"], "budget exceeded"

    known = {"penyelenggara_kegiatan": "BEM FEB UNAIR", "raw_role": "PESERTA"}
    prompt_a = build_prompt_tingkat_context(known)
    assert "BEM FEB UNAIR" in prompt_a
    prompt_b, mini = build_prompt_tingkat_minimized(_SAMPLE_RAW, known)
    assert "diselenggarakan oleh Badan Eksekutif" in prompt_b

    print("minimize_text kept lines:")
    for l in minimized.split("\n"):
        print(f"  | {l}")
    print("ok: minimize_text + prompt builders")
    return minimized, prompt_a, prompt_b


if __name__ == "__main__":
    _demo()
