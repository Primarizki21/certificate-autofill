"""Handoff v7 Phase 2 — targeted OCR dedup experiment (experiment only).

Production `ocr_fallback.merge_unique_lines` drops only exact duplicate lines.
OCR engines emit the same logical line with small variations (case, spacing,
punct), so near-duplicates survive and bloat the LLM prompt.

This experiment dedups by a normalized key (case/punct/space stripped),
keeping the first occurrence and its original text, preserving line order.
Production ocr_fallback.py stays untouched until the ship gate.
"""

import re


def _norm_key(line: str) -> str:
    return re.sub(r"[^a-z0-9]", "", line.lower())


def dedup_lines(text: str) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        key = _norm_key(clean)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(clean)
    return "\n".join(out)


def _dedup_stats(text: str) -> tuple[int, int]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    dup = len(lines) - len({_norm_key(l) for l in lines if _norm_key(l)})
    return dup, len(lines)


def demo() -> None:
    sample = "UNIVERSITAS AIRLANGGA\nUniversitas Airlangga\nBEM FKM UNAIR\n"
    deduped = dedup_lines(sample)
    assert deduped == "UNIVERSITAS AIRLANGGA\nBEM FKM UNAIR", repr(deduped)
    dup, total = _dedup_stats(sample)
    assert dup == 1 and total == 3, (dup, total)
    print("ok: ocr_cleanup_v4")


if __name__ == "__main__":
    demo()
