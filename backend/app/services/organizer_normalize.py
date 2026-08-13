"""Normalisasi organizer & nomor pasca-organizer_v2 — PRODUCTION (PROD-002).

Port produksi lapisan eksperimen offline (0 LLM), keputusan user handoff v29:
- KEEP:  R0 (bug fix `_TRAILING_ORG` -> `r"\1"` + `_UNIV_TRAIL`), PREFIX_HELD,
         R2 (Library Class), R3 (strip sampai "oleh" — KOREKSI: membuka alias
         F1 APHSA, 2 fix 1952296/2030335; OOD ablation "R3 = NO_FIX" diukur
         pre-ORG-004 tanpa lapisan alias, handoff v29 awalnya bilang "R3
         hapus" = salah konteks), R6 (enrich kurang_lengkap), F1 alias
         canonical, F3 suffix "BEM FKM", nomor D/E (SERT + dot/space + fallback raw).
- SKIP:  R1 (suffix faculty/dept), R4 (date suffix) — GUARD ditunda (skip),
         fix 2 cert dikorbankan, 0 risiko (keputusan user).
- DROP:  R5 (dash S-1, DEAD).

Aktif hanya bila `settings.enable_organizer_normalization` (default false).
Sumber: tests/benchmark_organizer_v3.py (v3/R6), tests/benchmark_org_format.py
(F1/F3), tests/benchmark_org_norm.py (nomor) — diport verbatim, urutan sama
dengan offline_v4 (v3 -> format -> nomor).
"""

import re

from app.services.field_extractor import extract_certificate_number

# --- Lapisan v3: prefix junk & R0 (dari benchmark_org_norm) ------------------
_PREFIX_JUNK = re.compile(
    r"^which\s+was?\s+held\s+from\s+.+?\s+to\s+.+?\s+by\s+",
    re.IGNORECASE,
)
# R0: trailing HIMA/BEM setelah org berkonteks universitas/fakultas/prodi.
# Bug lama: sub("", v) menghapus SELURUH string; fix: `r"\1"` (ORG-003).
_TRAILING_ORG = re.compile(
    r"^(?=.*(?:universitas|fakultas|program studi))(.+?)\s+"
    r"(?:himpunan\s+mahasiswa\s+\S+|bem\s+\S+|him[a-z0-9]*)\s*$",
    re.IGNORECASE,
)
_UNIV_TRAIL = re.compile(r"\s+universitas\s*$", re.IGNORECASE)
# --- R2: prefix junk kata tetap ----------------------------------------------
_PREFIX_JUNK_WORDS = re.compile(r"^(?:library\s+class\s+)", re.IGNORECASE)
# --- R3: prefix sampai kata "oleh" -------------------------------------------
# KOREKSI handoff v29 (flaw): ablation "R3 = NO_FIX" diukur pre-ORG-004; pada
# port final R3 justru membuka alias F1 APHSA (1952296/2030335 = 2 fix).
_UP_TO_OLEH = re.compile(r"^.*?\s*oleh\s+", re.IGNORECASE)
# --- prefix junk "Which [was] Held From <tgl> to <tgl> by" --------------------
# Fix regex benchmark_org_norm: `\s+was?` butuh 2 whitespace-run, jadi
# "Which Held From" (1 spasi) tak pernah match — diperbaiki di lapisan v3.
_PREFIX_HELD = re.compile(r"^which\s+(?:was\s+)?held\s+from\s+.+?\s+to\s+.+?\s+by\s+", re.IGNORECASE)
# --- R6: enrich konteks `kurang_lengkap` (F1C-001) ---------------------------
# Guard keras: hanya kasus yang konteksnya terverifikasi ada di teks.
_R6_KEYWORDS = re.compile(r"(?:fakultas|faculty|dept|department|study\s*program|program\s*studi|universitas|university)", re.IGNORECASE)
_R6_FACULTY_TOKEN = re.compile(r"(?:faculty|fakultas|university|universitas|dept|department)", re.IGNORECASE)
_R6_TYPOS = {"llmu": "ilmu"}
_R6_DEPT_SUFFIX = {
    ("FACULTYOFSCIENCEANDTECHNOLOGY", "INFORMATIONSYSTEMSSTUDYPROGRAM"): "Information System Dept.",
}
_R6_IRIS = ("FACULTYOFADVANCEDTECHNOLOGYANDMULTIDISCIPLINARY",
            "INNOVATIVERESEARCHOFINTELLIGENTSYSTEMIRIS",
            "Innovative Research of Intelligent System (IRIS) ")
_R6_HIMASADA = ("HIMASADA", "FAKUETASILMU", "Fakultas Ilmu Komputer")
# --- F1: alias canonical (compact value -> bentuk canonical, ORG-004) --------
_ORG_ALIASES = {
    "FACULTYOFSCIENCEANDTECHNOLOGYINFORMATIONSYSTEMSDEPT": (
        "Faculty of Science and Technology Information System Dept."
    ),
    "PROGRAMSTUDISLTEKNOLOGISAINSDATA": "Program Studi S1 Teknologi Sains Data",
    "DIVISIKAPROFAPHSABEMFKMUNIVERSITASAIRLANGGA": "Divisi Kaprof APHSA BEM FKM Universitas Airlangga",
    "FACULTYOFCOMPUTERSCIENCEUB": "Faculty of Computer Science Brawijaya University",
    "FAKULTASTEKNOLOGIMAJUDANMULTIDISIPLINUNIVERSITASAIRLANGGA": (
        "Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga"
    ),
}
# --- F3: suffix univ utk "BEM FKM" (konteks UNAIR) ----------------------------
_BEM_FKM_SUFFIX = re.compile(r"\bBEM\s+FKM\s*$", re.IGNORECASE)
# --- Nomor D/E: SERT prefix, titik, spasi internal, fallback raw text --------
_SERT_PATTERN = re.compile(
    r"\b(SERT\s*[-.]?\s*[0-9]{2,6}\s*/\s*[A-Z0-9][A-Z0-9.\-/ ]+?/?\s*[0-9]{4})\b",
    re.IGNORECASE,
)
_DOT_PATTERN = re.compile(
    r"\b([0-9]{2,6}\.[0-9]{2,6}\s*/\s*[A-Z0-9][A-Z0-9.\-/ ]+?/?\s*[0-9]{4})\b",
    re.IGNORECASE,
)
_SPACE_PATTERN = re.compile(
    r"\b([0-9]{2,6}\s*/\s*[A-Z0-9][A-Z0-9.\-/ ]+?/?\s*[0-9]{4})\b",
    re.IGNORECASE,
)


def _compact(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _camel_split(s: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)


def _enrich_join(v: str, raw_text: str) -> str:
    """Join baris beruntun berkata-kunci org di bawah baris yang = v persis."""
    if _R6_FACULTY_TOKEN.search(v):
        return v
    cv = _compact(v)
    if len(cv) < 5:
        return v
    lines = raw_text.splitlines()
    for i, line in enumerate(lines):
        if _compact(line) != cv:
            continue
        parts = []
        for nxt in lines[i + 1: i + 3]:
            nxt = nxt.strip()
            if not nxt or _compact(nxt) == cv:
                break
            if not _R6_KEYWORDS.search(nxt):
                break
            for typo, fix in _R6_TYPOS.items():
                nxt = nxt.replace(typo, fix)
            parts.append(_camel_split(nxt))
        if parts:
            return v + " " + " ".join(parts)
    return v


def _enrich_organizer(v: str | None, raw_text: str) -> str | None:
    """R6: lengkapi `kurang_lengkap` dari konteks teks (0 LLM)."""
    if not v:
        return v
    if re.search(r"\bBiro\b\s*(?:\n\s*)*Penelitian\s+dan\s+Pengembangan", raw_text, re.IGNORECASE) and v.startswith("Penelitian dan Pengembangan"):
        v = "Biro " + v
    ct = _compact(raw_text)
    if _compact(v) == _R6_HIMASADA[0] and _R6_HIMASADA[1] in ct:
        v = f"{v}, {_R6_HIMASADA[2]}"
    if _compact(v) == _R6_IRIS[0] and _R6_IRIS[1] in ct:
        v = _R6_IRIS[2] + v
    for (org, sig), suffix in _R6_DEPT_SUFFIX.items():
        if _compact(v) == org and sig in ct:
            v = f"{v} {suffix}"
            break
    return _enrich_join(v, raw_text)


def _norm_organizer_v3(value: str | None, raw_text: str) -> str | None:
    """Lapisan v3 final produksi: R0/PREFIX_HELD/R2/R3/R6 (R1/R4 skip, R5 drop)."""
    v = value or ""
    v = _PREFIX_JUNK.sub("", v).strip()
    upper_raw = (raw_text or "").upper()
    has_unair = bool(re.search(r"UNAIR|UNIVERSITAS\s*AIRLANGGA|AIRLANGGA", upper_raw))
    if has_unair:
        v = _TRAILING_ORG.sub(r"\1", v).strip()  # R0: bug fix ORG-003
        v = _UNIV_TRAIL.sub(" Universitas Airlangga", v).strip()
    v = _PREFIX_HELD.sub("", v).strip()
    v = _PREFIX_JUNK_WORDS.sub("", v).strip()
    v = _UP_TO_OLEH.sub("", v).strip()
    return _enrich_organizer(v, raw_text)


def _norm_org_format(value: str | None, raw_text: str) -> str | None:
    """Lapisan ORG-004: F1 alias canonical + F3 suffix BEM FKM."""
    v = value or ""
    c = _compact(v)
    if c in _ORG_ALIASES:
        v = _ORG_ALIASES[c]
    has_unair = bool(re.search(r"UNAIR|UNIVERSITAS\s*AIRLANGGA|AIRLANGGA", (raw_text or "").upper()))
    if has_unair and _BEM_FKM_SUFFIX.search(v) and "UNIVERSITAS AIRLANGGA" not in v.upper():
        v = v + " Universitas Airlangga"
    return v or None


def normalize_organizer(value: str | None, raw_text: str) -> str | None:
    """Normalisasi organizer pasca-organizer_v2 (v3 + format), urutan offline_v4."""
    v = _norm_organizer_v3(value, raw_text)
    return _norm_org_format(v, raw_text)


def normalize_nomor(raw_text: str) -> str | None:
    """Normalisasi nomor: SERT pattern duluan, lalu pattern 1-3, lalu titik/spasi.

    Berjalan pada RAW text (bukan normalize_text) — normalize_text memecah
    "UN27"/"NACOESTA4.0" sehingga regex nomor gagal (ORG-002).
    """
    m = _SERT_PATTERN.search(raw_text)
    if m:
        return re.sub(r"\s+", "", m.group(1)).strip(" .,:;-")
    found = extract_certificate_number(raw_text)
    if found:
        return found
    for pat in (_DOT_PATTERN, _SPACE_PATTERN):
        m = pat.search(raw_text)
        if m:
            return re.sub(r"\s+", "", m.group(1)).strip(" .,:;-")
    return None
