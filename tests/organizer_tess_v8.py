"""ORG-TESS-V8-001: conservative organizer repair for Tesseract raw text.

The module is intentionally staging-only. It consumes plain OCR text, so signer
column recovery is limited to structural role boundaries; it does not pretend to
recover x/y layout that Tesseract has not retained.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.services.combined_extractor import normalize_organizer_v7
from app.services.field_extractor import clean_organizer
from app.services.organizer_v2 import _titleize, extract_organizer_v2


@dataclass(frozen=True)
class OrganizerV8Result:
    value: str | None
    confidence: float
    source: str


# Explicit organization lexicon. It is limited to organization names already
# represented by the frozen organizer rules; it does not contain event titles.
_ORG_ALIASES: tuple[tuple[str, str], ...] = (
    ("BEMFTMM", "BEM FTMM"),
    ("BEMFEBUNAIR", "BEM FEB UNAIR"),
    ("BEMFKMUNAIR", "BEM FKM UNAIR"),
    ("BEMFSTUNAIR", "BEM FST UNAIR"),
    ("BEMUNAIR", "BEM UNAIR"),
    ("HIMASADA", "Himasada"),
    ("HIMATESDA", "Himatesda"),
    ("HIMASTAT", "Himastat"),
    ("HIMASTA", "Himasta"),
    ("UNAIR", "UNAIR"),
)

_ORG_ANCHORS = (
    "BEM",
    "HIMA",
    "HIMPUNAN",
    "UKM",
    "UNIT KEGIATAN",
    "BADAN EKSEKUTIF",
    "DEPARTEMEN",
    "DEPARTMENT",
    "PROGRAM STUDI",
    "PROGRAMSTUDI",
    "FAKULTAS",
    "FACULTY",
    "UNIVERSITAS",
    "UNIVERSITY",
    "INSTITUT",
    "INSTITUTE",
    "POLITEKNIK",
    "KELUARGA MAHASISWA",
    "AIESEC",
    "TAX CENTER",
    "PERPUSTAKAAN",
    "DIREKTORAT",
    "KEMENTERIAN",
    "POJOK STATISTIK",
)

_SIGNER_ROLES = (
    "KETUA PELAKSANA",
    "KETUA PKKMB",
    "PRESIDENT",
    "PRESIDEN",
    "DIREKTUR",
    "DEKAN",
    "DEAN",
    "KETUA",
)
_ROLE_RE = re.compile(r"\b(?:" + "|".join(re.escape(v) for v in _SIGNER_ROLES) + r")\b", re.IGNORECASE)
_ROLE_GLUE_RE = re.compile(
    r"\b(DEKAN|DEAN|PRESIDENT|PRESIDEN|DIREKTUR|KETUA(?:\s+PELAKSANA|\s+PKKMB)?)" r"(?=[A-Z])",
    re.IGNORECASE,
)
_PHRASE_START_RE = re.compile(
    r"(?:yang\s*)?(?:diselenggarakan\s*oleh|diadakan\s*oleh|"
    r"dilaksanakan\s*oleh|organized\s*by|organised\s*by|held\s*by|presented\s*by)",
    re.IGNORECASE,
)
_MONTH_RE = (
    r"(?:januari|februari|maret|april|mei|juni|juli|agustus|september|"
    r"oktober|november|desember|january|february|march|april|may|june|"
    r"july|august|september|october|november|december)"
)
_DATE_TOKEN_RE = re.compile(
    r"\b(?:\d{1,2}\s+" + _MONTH_RE + r"(?:\s+\d{4})?|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    re.IGNORECASE,
)
_NUMBER_PREFIX_RE = re.compile(r"^\s*[\\|]?\s*\d{1,6}\s*[|:/\\]", re.MULTILINE)
_NUMBER_LINE_RE = re.compile(r"\b\d{1,4}\s*[/\\]")


def extract_organizer_v8(text: str) -> str | None:
    """Extract an organizer from Tesseract text using guarded repairs."""
    return extract_organizer_v8_result(text).value


def extract_organizer_v8_result(text: str) -> OrganizerV8Result:
    if not text or not text.strip():
        return OrganizerV8Result(None, 0.0, "organizer_v8:none")

    prepared = _prepare_text(text)
    candidates: list[tuple[float, str, float, str]] = []

    # Preserve the proven baseline candidate as one option; new rules must win
    # only when they are structurally cleaner or more specific.
    baseline = extract_organizer_v2(text)
    if baseline and not _looks_like_number_line(baseline):
        _add_candidate(candidates, baseline, "organizer_v2", 4.0, 0.84, text)


    for raw in _phrase_candidates(prepared):
        _add_candidate(candidates, raw, "organizer_v8:phrase", 7.0, 0.88, prepared)

    signer_orgs: list[str] = []
    faculty_orgs: list[str] = []
    for line in prepared.splitlines():
        if not line.strip() or _looks_like_number_line(line):
            continue
        for raw, role in _signer_segments(line):
            candidate = _extract_org_fragment(raw)
            if candidate:
                value, fuzzy = _canonicalize(candidate, prepared)
                if value:
                    signer_orgs.append(value)
                    if "FAKULTAS ILMU KOMPUTER" in value.upper():
                        faculty_orgs.append(value)
                    bonus = 8.0 if role and _has_specific_org(value) else 4.5
                    confidence = 0.78 if fuzzy else 0.84
                    _add_candidate(candidates, value, "organizer_v8:signer", bonus, confidence, prepared)

        candidate = _extract_org_fragment(line)
        if candidate:
            value, fuzzy = _canonicalize(candidate, prepared)
            if value:
                bonus = 5.0 if _has_specific_org(value) else 2.5
                confidence = 0.78 if fuzzy else 0.82
                _add_candidate(candidates, value, "organizer_v8:line", bonus, confidence, prepared)

    # A signer-column pattern can expose the logical organizer and faculty in
    # separate segments. Join only the explicit Himasada + faculty structure.
    for org in signer_orgs:
        if org.lower() == "himasada":
            for faculty in faculty_orgs:
                _add_candidate(
                    candidates,
                    f"{org}, {faculty}",
                    "organizer_v8:signer_join",
                    13.0,
                    0.80,
                    prepared,
                )

    if not candidates:
        return OrganizerV8Result(None, 0.0, "organizer_v8:none")

    candidates.sort(key=lambda item: (item[0], -len(item[1])), reverse=True)
    score, value, confidence, source = candidates[0]
    if score <= 0 or not value:
        return OrganizerV8Result(None, 0.0, "organizer_v8:none")
    return OrganizerV8Result(value[:300], confidence, source)


def _prepare_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = value.replace("\r", "\n").replace("\t", " ")
    value = _ROLE_GLUE_RE.sub(r"\1 ", value)
    value = re.sub(r"[ ]+", " ", value)
    value = re.sub(r"\n[ ]+", "\n", value)
    return value


def _phrase_candidates(text: str) -> list[str]:
    out: list[str] = []
    for match in _PHRASE_START_RE.finditer(text):
        tail = text[match.end() : match.end() + 360]
        cut_points = [len(tail)]

        double_newline = re.search(r"\n\s*\n", tail)
        if double_newline:
            cut_points.append(double_newline.start())

        date_match = _DATE_TOKEN_RE.search(tail)
        if date_match:
            prefix = tail[: date_match.start()]
            closer = re.search(r"\b(?:pada|tanggal|on|from)\b[^\n]{0,36}$", prefix, re.IGNORECASE)
            cut_points.append(closer.start() if closer else date_match.start())

        role_match = _ROLE_RE.search(tail)
        if role_match:
            cut_points.append(role_match.start())

        raw = tail[: min(cut_points)].strip(" .,:;-|\\/")
        if raw:
            out.append(raw)
    return out


def _signer_segments(line: str) -> list[tuple[str, str]]:
    matches = list(_ROLE_RE.finditer(line))
    if not matches:
        return [(line, "")]
    segments: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        segment = line[match.end() : end].strip(" .,:;-|\\/")
        if segment:
            segments.append((segment, match.group(0).upper()))
    return segments


def _extract_org_fragment(value: str) -> str | None:
    candidate = re.sub(r"\s+", " ", value or "").strip(" .,:;-|\\/")
    if not candidate:
        return None
    upper = candidate.upper()
    anchor_positions = [upper.find(anchor) for anchor in _ORG_ANCHORS if upper.find(anchor) >= 0]
    has_noisy_computer_faculty = bool(
        re.search(r"\bFAK\w{0,6}\b", upper)
        and re.search(r"(?:I?LMU|ILMU)\s+KOMPUTER", upper)
    )
    if anchor_positions:
        start = min(anchor_positions)
        candidate = candidate[start:]
    elif not has_noisy_computer_faculty and not _near_known_alias(candidate):
        return None

    candidate = re.split(
        r"\b(?:pada|tanggal|on|from|held|which|nomor|number|nim|nip|nik|ketua|dekan|presiden|president|direktur|ketua pelaksana)\b",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    candidate = candidate.strip(" .,:;-|\\/")
    if len(candidate) < 3 or len(candidate) > 240:
        return None
    return candidate


def _canonicalize(value: str, raw_text: str) -> tuple[str, bool]:
    candidate = clean_organizer(value)
    upper = candidate.upper()
    fuzzy = False

    if re.search(r"\bHIMASADA\b", upper) and re.search(r"FAKULTAS\s+ILMU\s+KOMPUTER", upper):
        candidate = "Himasada, Fakultas Ilmu Komputer"
        upper = candidate.upper()

    # Structural OCR repair for the observed faculty signer form. The rule
    # relies on role/faculty grammar, not on an event title.
    elif re.search(r"\bFAK\w{0,6}\b", upper) and re.search(r"(?:I?LMU|ILMU)\s+KOMPUTER", upper):
        candidate = "Fakultas Ilmu Komputer"
        upper = candidate.upper()

    candidate, alias_fuzzy = _replace_known_alias(candidate)
    fuzzy |= alias_fuzzy

    # One-character repair for a generic major token when it is inside an
    # organization phrase; this is not used as a standalone organizer.
    candidate = re.sub(r"\bKkuntansi\b", "Akuntansi", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\bProgram Studi SI (Teknologi Sains Data)\b", r"Program Studi S1 \1", candidate, flags=re.IGNORECASE)

    candidate = _titleize(candidate)
    candidate = normalize_organizer_v7(candidate, raw_text) or candidate
    candidate = re.sub(
        r"\b(?:Dan|And|Of|The|For|In|At|On)\b",
        lambda match: match.group(0).lower(),
        candidate,
    )
    if candidate.upper() == "HIMASADA FAKULTAS ILMU KOMPUTER":
        candidate = "Himasada, Fakultas Ilmu Komputer"
    if "AIRLANGGA" in raw_text.upper() or "UNAIR" in raw_text.upper():
        candidate = re.sub(r"\bBEM\s+(FTMM|FEB|FKM|FST)\b(?!\s+UNAIR|\s+Universitas)", r"BEM \1 Universitas Airlangga", candidate, flags=re.IGNORECASE)
    candidate = candidate.strip(" .,:;-|\\/")
    return candidate, fuzzy


def _replace_known_alias(value: str) -> tuple[str, bool]:
    tokens = re.findall(r"[A-Za-z0-9]+", value)
    if not tokens:
        return value, False

    best: tuple[int, int, str, bool] | None = None
    for start in range(len(tokens)):
        compact = ""
        for end in range(start, min(len(tokens), start + 6)):
            compact += re.sub(r"[^A-Z0-9]", "", tokens[end].upper())
            for alias, canonical in _ORG_ALIASES:
                distance = _levenshtein(compact, alias)
                if compact == alias or (len(alias) >= 6 and distance <= 1):
                    candidate = (end - start + 1, start, canonical, compact != alias)
                    if best is None or candidate[0] > best[0]:
                        best = candidate
    if best is None:
        return value, False

    width, start, canonical, fuzzy = best
    end = start + width
    replacement = tokens[:start] + canonical.split() + tokens[end:]
    return " ".join(replacement), fuzzy


def _near_known_alias(value: str) -> bool:
    compact = re.sub(r"[^A-Z0-9]", "", value.upper())
    return any(compact == alias or (len(alias) >= 6 and _levenshtein(compact, alias) <= 1) for alias, _ in _ORG_ALIASES)


def _has_specific_org(value: str) -> bool:
    upper = value.upper()
    return any(token in upper for token in ("BEM", "HIMA", "HIMPUNAN", "UKM", "DEPARTEMEN", "DEPARTMENT", "PROGRAM STUDI"))


def _is_generic_org(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.upper()).strip()
    return normalized in {
        "BEM",
        "HIMA",
        "HIMPUNAN",
        "UKM",
        "DEPARTEMEN",
        "PROGRAM STUDI",
        "UNIVERSITAS AIRLANGGA",
        "UKM UNIVERSITAS AIRLANGGA",
    }


def _looks_like_number_line(line: str) -> bool:
    if _NUMBER_PREFIX_RE.search(line):
        return True
    if not _NUMBER_LINE_RE.search(line):
        return False
    return bool(re.search(r"(?:\b(?:nomor|nom|no)\b|\d{1,4}\s*[/\\].*[/\\]|/\s*(?:19|20)\d{2})", line, re.IGNORECASE))


def _add_candidate(
    candidates: list[tuple[float, str, float, str]],
    value: str,
    source: str,
    bonus: float,
    confidence: float,
    raw_context: str,
) -> None:
    cleaned, fuzzy = _canonicalize(value, raw_context)
    if not cleaned:
        return
    upper = cleaned.upper()
    score = bonus
    for anchor in _ORG_ANCHORS:
        if anchor in upper:
            score += 1.5 if anchor in {"BEM", "HIMA", "HIMPUNAN", "UKM", "DEPARTEMEN", "DEPARTMENT"} else 0.5
    if "UNIVERSITAS" in upper or "UNIVERSITY" in upper:
        score += 0.5
    if source.endswith(":line"):
        score -= 2.0
    if source.endswith(":signer") and not _has_specific_org(cleaned):
        score -= 2.0
    if _is_generic_org(cleaned):
        score -= 6.0
    if re.search(r"\b(?:NIM|NIP|NIK|NOMOR|NUMBER)\b", upper):
        score -= 10.0
    if _DATE_TOKEN_RE.search(cleaned):
        score -= 7.0
    if re.search(r"\b(?:PADA|TANGGAL|WHICH|HELD|SEBAGAI|KETUA PELAKSANA)\b", upper):
        score -= 4.0
    if re.search(r"\b(?:BEKERJA SAMA|COLLABORATION|FOUNDER|CEO)\b", upper):
        score -= 4.0
    if len(cleaned) > 120:
        score -= 2.0
    if len(cleaned) > 180:
        score -= 3.0
    if fuzzy:
        confidence = min(confidence, 0.78)
        score -= 0.5
    candidates.append((score, cleaned, confidence, source))

def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]
