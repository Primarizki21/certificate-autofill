"""LLM tingkat inference (v8 Phase 2, f_bias) — port dari tests.

Pemanggilan Ollama lokal untuk field tingkat saat router tidak memutuskan.
Degradasi aman: bila Ollama tidak aktif / timeout / response invalid,
kembalikan None sehingga pipeline memakai nilai rule-based lama.

Prompt = e_hybrid f_bias (v4): instruksi tingkat + aturan bias bahasa Inggris
+ teks terseleksi (minimize_text) + konteks field yang sudah diketahui.
"""

import json
import re
import urllib.request
from urllib.error import URLError

from app.config import settings
from app.master_data import FORM_OPTIONS

TINGKAT_OPTIONS = [o for o in FORM_OPTIONS["tingkat"] if o not in ("", "--")]
_OLLAMA_HOST = settings.ollama_host

_MAX_CHARS = 300
_KEEP_SCORE = 2
_FALLBACK_SCORE = 1

_ORGANIZER_KW = [
    "BEM", "BADAN EKSEKUTIF", "HIMA", "HIMPUNAN", "UKM", "UNIT KEGIATAN",
    "REKTORAT", "DIREKTORAT", "KEMAHASISWAAN", "FAKULTAS", "DEPARTEMEN",
    "PRODI", "DEPT", "DEPARTMENT", "STUDY PROGRAM", "PROGRAM STUDI",
    "FACULTY", "SCHOOL OF", "SEMA", "SENAT", "LEMBAGA", "UNIVERSITAS",
    "ORGANIZING COMMITTEE", "ORGANIZER", "AIESEC",
]
_SCALE_KW = [
    "NASIONAL", "INTERNASIONAL", "INTERNATIONAL", "NATIONAL", "LOMBA",
    "KOMPETISI", "COMPETITION", "OLIMPIADE", "KONFERENSI", "CONFERENCE",
    "CHALLENGE", "FAIR",
]
_ROLE_KW = [
    "PESERTA", "PANITIA", "KETUA", "PRESIDEN", "PENGURUS", "ANGGOTA",
    "PARTISIPASI", "PARTICIPANT", "SEBAGAI",
]
_NOISE_RE = re.compile(r"\b(NIM|NIP|NIK)\s*[:.]?\s*\d")
_CERT_RE = re.compile(r"\b\d{2,4}/[A-Z0-9.]+/[A-Z0-9./]+/\d{4}\b")
_DATE_RE = re.compile(
    r"\d{1,2}[\s/-](JANUARI|FEBRUARI|MARET|APRIL|MEI|JUNI|JULI|AGUSTUS|SEPTEMBER"
    r"|OKTOBER|NOVEMBER|DESEMBER|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
    r"[\s/-]\d{2,4}",
    re.IGNORECASE,
)
_GARBLE_RE = re.compile(r"[a-z]{23,}")
_MIXED_CASE_RE = re.compile(r"[A-Z][a-z]{2,}[A-Z]")

# Instruksi tingkat (compact, ~v4 _INSTR).
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

# Instruksi lengkap untuk sertifikat berisiko (garble/UKM/conflict).
_INSTR_FULL = """Tentukan tingkat kegiatan dari sertifikat berikut.

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

# v8 Phase 2 f_bias: koreksi bias bahasa Inggris.
_BIAS_LINES = [
    "- NAMA ACARA ATAU TEKS BAHASA INGGRIS TIDAK OTOMATIS berarti Internasional",
    "- Internasional HANYA jika penyelenggara/lembaganya asing (di luar Indonesia)",
    "- aturan BEM/HIMA/fakultas/universitas di atas TETAP berlaku dan diutamakan",
    "- tanpa bukti skala sama sekali, JANGAN menebak Internasional;",
    "  pilih Fakultas atau Nasional yang paling masuk akal dari konteks",
]

_KNWN_LABELS = [
    ("nama_kegiatan_sertifikasi", "Nama Kegiatan"),
    ("penyelenggara_kegiatan", "Penyelenggara"),
    ("raw_role", "Peran"),
]


def score_line(line: str) -> int:
    upper = line.upper()
    score = 0
    if any(k in upper for k in _ORGANIZER_KW):
        score += 4
    if any(k in upper for k in ["DISELENGGARAKAN", "DIADAKAN", "ORGANIZED", "HELD BY"]):
        score += 3
    if any(k in upper for k in _SCALE_KW):
        score += 3
    if re.search(r"TINGKAT\s+[A-Z/ ]{3,}", upper):
        score += 5
    if any(k in upper for k in _ROLE_KW):
        score += 2
    if _DATE_RE.search(upper):
        score += 1
    if _CERT_RE.search(upper):
        score += 1
    if _NOISE_RE.search(upper):
        score -= 5
    if _GARBLE_RE.search(line):
        score -= 3
    return score


def minimize_text(raw_text: str, max_chars: int = _MAX_CHARS) -> str:
    lines = [l.strip() for l in (raw_text or "").split("\n") if l.strip()]
    selected = [l for l in lines if score_line(l) >= _KEEP_SCORE]
    if not selected:
        selected = [l for l in lines if score_line(l) >= _FALLBACK_SCORE]
    if not selected:
        return (raw_text or "").strip()[:max_chars]
    out, used = [], 0
    for line in selected:
        if used + len(line) + 1 > max_chars:
            continue
        out.append(line)
        used += len(line) + 1
    return "\n".join(out)


def _context_block(known_fields: dict[str, str]) -> list[str]:
    lines = ["Field yang sudah diketahui (dari pipeline):"]
    for key, label in _KNWN_LABELS:
        val = (known_fields or {}).get(key) or "tidak diketahui"
        lines.append(f"- {label}: {val}")
    return lines


def _needs_full_prompt(raw_text: str, organizer: str | None) -> bool:
    if _GARBLE_RE.search(raw_text or ""):
        return True
    if len(_MIXED_CASE_RE.findall(raw_text or "")) >= 6:
        return True
    if organizer and re.search(r"UKM", organizer.upper()):
        return True
    return False


def _difficulty(raw_text: str) -> str:
    if _GARBLE_RE.search(raw_text or ""):
        return "poor_ocr"
    if re.search(r"\b(nasional|internasional|national|international)\b", (raw_text or "").lower()):
        return "strong"
    return "normal"


def _budget_for(difficulty: str) -> int:
    return {"strong": 140, "normal": 200, "poor_ocr": 300}[difficulty]


def build_prompt_tingkat_bias(raw_text: str, known_fields: dict[str, str]) -> str:
    """Prompt f_bias — sama struktur dengan tests build_prompt_tingkat_bias."""
    organizer = (known_fields or {}).get("penyelenggara_kegiatan")
    if _needs_full_prompt(raw_text, organizer):
        minimized = minimize_text(raw_text)
        lines = [
            _INSTR_FULL.strip(),
            *("  " + b for b in _BIAS_LINES),
            "Teks sertifikat (bagian relevan):",
            minimized,
            "",
            *_context_block(known_fields),
            "",
            "Jawaban (satu opsi, tanpa penjelasan):",
        ]
    else:
        difficulty = _difficulty(raw_text)
        minimized = minimize_text(raw_text, max_chars=_budget_for(difficulty))
        lines = [
            _INSTR.format(options=" / ".join(TINGKAT_OPTIONS)),
            *_BIAS_LINES,
            "Teks sertifikat (bagian relevan):",
            minimized,
            "",
            *_context_block(known_fields),
            "",
            "Jawaban (satu opsi, tanpa penjelasan):",
        ]
    return "\n".join(lines)


def validate_tingkat(value: str | None) -> str | None:
    if not value:
        return None
    clean = value.strip().rstrip(".")
    if not clean:
        return None
    clean_upper = clean.upper()
    valid_upper = [o.upper() for o in TINGKAT_OPTIONS]
    if clean_upper in valid_upper:
        return TINGKAT_OPTIONS[valid_upper.index(clean_upper)]
    for opt in TINGKAT_OPTIONS:
        if opt.upper() in clean_upper or clean_upper in opt.upper():
            return opt
    if "DEPARTEMEN" in clean_upper or "PRODI" in clean_upper:
        return "Departemen/Program Studi"
    if "NASIONAL" in clean_upper:
        return "Nasional"
    if "UNIVERSITAS" in clean_upper:
        return "Universitas"
    return None


def call_ollama(prompt: str, timeout: float = 15.0) -> str | None:
    """Panggil Ollama /api/generate. None bila gagal/timeout."""
    host = _OLLAMA_HOST
    if host and not host.startswith("http"):
        host = "http://" + host
    payload = json.dumps({
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 30},
    }).encode()
    req = urllib.request.Request(
        f"{host}/api/generate", data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        return data.get("response")
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def infer_tingkat(raw_text: str, known_fields: dict[str, str]) -> str | None:
    """Infer tingkat via Ollama (f_bias). None bila gagal/invalid."""
    try:
        prompt = build_prompt_tingkat_bias(raw_text, known_fields)
        response = call_ollama(prompt)
        return validate_tingkat(response)
    except Exception:
        return None
