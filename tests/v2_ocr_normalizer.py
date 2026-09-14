"""Regional OCR cleanup for date and certificate-number evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class OcrNormalizationResult:
    text: str
    changed: bool
    changed_lines: int
    replacements: int
    reasons: tuple[str, ...]


_REGION_HINT_RE = re.compile(
    r"(?:\b(?:no|nomor|number|nom0r)\b|\b(?:sertif|certificate)\b|/|"
    r"\b(?:januari|februari|maret|april|mei|juni|juli|agustus|september|"
    r"oktober|november|desember|january|february|march|may|june|july|"
    r"august|october|december)\b)",
    re.IGNORECASE,
)
_DATE_HINT_RE = re.compile(
    r"(?:\d{1,2}\s*[/-]\s*[\dOoIlSＢB]{1,2}\s*[/-]|"
    r"\b(?:januari|februari|maret|april|mei|juni|juli|agustus|september|"
    r"oktober|november|desember|january|february|march|may|june|july|"
    r"august|october|december)\b)",
    re.IGNORECASE,
)
_STRUCTURE_REPAIRS = (
    (r"dalamrangkaian", "dalam rangkaian"),
    (r"dalamrangka", "dalam rangka"),
    (r"dalamacara", "dalam acara"),
    (r"dalamkegiatan", "dalam kegiatan"),
    (r"padakegiatan", "pada kegiatan"),
    (r"padaajang", "pada ajang"),
    (r"padaperlombaan", "pada perlombaan"),
    (r"yangdiselenggarakan", "yang diselenggarakan"),
    (r"yangdiadakan", "yang diadakan"),
    (r"yangdilaksanakan", "yang dilaksanakan"),
    (r"diselenggarakanoleh", "diselenggarakan oleh"),
    (r"diadakanoleh", "diadakan oleh"),
    (r"dilaksanakanoleh", "dilaksanakan oleh"),
    (r"dengantema", "dengan tema"),
    (r"subacara", "sub acara"),
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _normalize_token(token: str) -> tuple[str, int]:
    if not any(char.isdigit() for char in token):
        return token, 0
    chars = list(token)
    replacements = 0
    for index, char in enumerate(chars):
        previous = chars[index - 1] if index else ""
        following = chars[index + 1] if index + 1 < len(chars) else ""
        adjacent_digit = previous.isdigit() or following.isdigit()
        if adjacent_digit and char.upper() == "O":
            chars[index] = "0"
            replacements += 1
        elif adjacent_digit and char.upper() == "S":
            chars[index] = "5"
            replacements += 1
        elif adjacent_digit and char.upper() == "B":
            chars[index] = "8"
            replacements += 1
        elif adjacent_digit and char.upper() in {"I", "L"}:
            chars[index] = "1"
            replacements += 1
    normalized = "".join(chars)
    if re.fullmatch(r"[IVXLCDM0-9]+", normalized, re.IGNORECASE):
        if re.search(r"[IVXLCDM]", normalized, re.IGNORECASE) and re.search(r"\d", normalized):
            romanized = re.sub(r"(?<=[IVXLCDM])1(?=[IVXLCDM]|$)", "I", normalized, flags=re.IGNORECASE)
            replacements += normalized != romanized
            normalized = romanized
    return normalized, replacements


def _normalize_line(line: str) -> tuple[str, int, str | None]:
    if "http://" in line.lower() or "https://" in line.lower():
        return line, 0, None
    if not _REGION_HINT_RE.search(line):
        return line, 0, None
    is_date = bool(_DATE_HINT_RE.search(line))
    replacements = 0

    def replace_token(match: re.Match[str]) -> str:
        nonlocal replacements
        before = line[: match.start()].rstrip()
        after = line[match.end() :].lstrip()
        has_separator_context = before.endswith("/") or after.startswith("/")
        digit_count = sum(char.isdigit() for char in match.group(0))
        if not has_separator_context and digit_count < 2:
            return match.group(0)
        normalized, count = _normalize_token(match.group(0))
        replacements += count
        return normalized
    normalized = _TOKEN_RE.sub(replace_token, line)
    reason = "date_region" if is_date else "number_region"
    return normalized, replacements, reason if replacements else None


def normalize_raw_ocr(raw_text: str) -> OcrNormalizationResult:
    normalized_lines: list[str] = []
    changed_lines = 0
    replacements = 0
    reasons: set[str] = set()
    for line in (raw_text or "").splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        content = line[:-1] if newline else line
        normalized_line, count, reason = _normalize_line(content)
        normalized_lines.append(normalized_line + newline)
        if count:
            changed_lines += 1
            replacements += count
            if reason:
                reasons.add(reason)
    normalized = "".join(normalized_lines)
    for pattern, replacement in _STRUCTURE_REPAIRS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    if normalized != raw_text:
        reasons.add("structural_glue")
    return OcrNormalizationResult(
        text=normalized,
        changed=normalized != (raw_text or ""),
        changed_lines=changed_lines,
        replacements=replacements,
        reasons=tuple(sorted(reasons)),
    )
