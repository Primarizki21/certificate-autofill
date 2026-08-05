"""Exp 5 — multi-field LLM: tingkat + penyelenggara dalam SATU call.

Berbasis f_bias (pemenang v9) + instruksi ekstraksi penyelenggara. Dipakai
variant C: prompt ini HANYA untuk cert yang pipeline organizer-nya MISS
(tidak exact & tidak fuzzy pasca matcher v2) — set target menyusut, hemat
token. Cert yang sudah exact/fuzzy tetap pakai f_bias (no-regress).

Experiment only — produksi tidak disentuh.
"""

import re

from tests.llm_extractor import TINGKAT_OPTIONS, validate_free_text, validate_tingkat
from tests.llm_extractor_v4 import _bias_instr, _needs_full_tingkat_prompt
from tests.llm_extractor_v3 import (
    KNOWN_FIELD_LABELS,
    build_prompt_tingkat_minimized,
    minimize_text,
)

PROMPT_VERSION = "v5_multi"

# Compact (Exp 5 optimasi token): instruksi organizer 109 -> ~35 tok/call.
# Instruksi detail lama (4 baris) dibuang — isi penting tetap: "org/instansi
# yang menyelenggarakan, bukan nama penerima". Output 2 baris.
_ORGANIZER_LINE = "Tentukan PENYELENGGARA (org/instansi yang menyelenggarakan, bukan nama penerima)."
_OUTPUT_INSTR = """Jawab persis 2 baris:
Tingkat: <satu opsi>
Penyelenggara: <nama org atau TIDAK_ADA>"""


def _context_block_without_organizer(known_fields: dict[str, str]) -> list[str]:
    """Context block yang TIDAK menyertakan penyelenggara.

    Untuk cert miss, nilai pipeline penyelenggara = salah → menyertakannya
    justru membiaskan LLM menyalin nilai yang keliru. Selalu 'tidak diketahui'.
    """
    lines = ["Field yang sudah diketahui (dari pipeline):"]
    for key, label in KNOWN_FIELD_LABELS:
        if key == "penyelenggara_kegiatan":
            lines.append(f"- {label}: tidak diketahui")
            continue
        val = known_fields.get(key) or "tidak diketahui"
        lines.append(f"- {label}: {val}")
    return lines


def build_prompt_multi(
    raw_text: str, known_fields: dict[str, str]
) -> tuple[str, str]:
    """Variant C multi-field: satu call minta tingkat + penyelenggara.

    Returns (prompt, minimized_text).
    """
    organizer = (known_fields or {}).get("penyelenggara_kegiatan")
    if _needs_full_tingkat_prompt(raw_text, organizer):
        prompt, minimized = build_prompt_tingkat_minimized(raw_text, known_fields)
        prompt = prompt.replace(
            "Jawaban (hanya satu opsi dari daftar, tanpa penjelasan):",
            "\n".join([_ORGANIZER_LINE, "", _OUTPUT_INSTR]),
        )
        return prompt, minimized

    from tests.llm_extractor_v4 import _INSTR, _budget_for, _difficulty

    minimized = minimize_text(raw_text, max_chars=_budget_for(_difficulty(raw_text)))
    lines = [
        _INSTR.format(options=" / ".join(TINGKAT_OPTIONS)),
        _bias_instr(),
        _ORGANIZER_LINE,
        "Teks sertifikat (bagian relevan):",
        minimized,
        "",
        *_context_block_without_organizer(known_fields),
        "",
        _OUTPUT_INSTR,
    ]
    return "\n".join(lines), minimized


_TINGKAT_RE = re.compile(r"Tingkat\s*[:\-]\s*([^\n]+)", re.IGNORECASE)
_PENYELENGGARA_RE = re.compile(r"Penyelenggara\s*[:\-]\s*([^\n]+)", re.IGNORECASE)


def parse_multi_response(response: str) -> tuple[str | None, str | None]:
    """Parse 'Tingkat: X' + 'Penyelenggara: Y'. Returns (tingkat, organizer)."""
    response = (response or "").strip()
    tingkat = None
    organizer = None
    m = _TINGKAT_RE.search(response)
    if m:
        tingkat = validate_tingkat(m.group(1).strip())
    p = _PENYELENGGARA_RE.search(response)
    if p:
        organizer = validate_free_text(p.group(1).strip())
    if tingkat is None:
        tingkat = validate_tingkat(response)
    # Tanpa label Penyelenggara, tapi ada struktur Tingkat: sisa baris non-tingkat
    # adalah organizer. Response bare value (tanpa struktur) = organizer None.
    if organizer is None and _TINGKAT_RE.search(response):
        rest = "\n".join(
            l for l in response.splitlines()
            if not _TINGKAT_RE.search(l) and not _PENYELENGGARA_RE.search(l)
        )
        if rest.strip():
            organizer = validate_free_text(rest.strip())
    return tingkat, organizer


if __name__ == "__main__":
    known = {"nama_kegiatan_sertifikasi": "SEMINAR NASIONAL", "raw_role": "PESERTA"}
    prompt, mini = build_prompt_multi(
        "SERTIFIKAT\nSEMINAR NASIONAL\nBEM FEB UNAIR\nPESERTA", known
    )
    assert "Penyelenggara:" in prompt
    assert "Tingkat:" in prompt
    assert "tidak diketahui" in prompt  # organizer tidak dibocorkan
    t, o = parse_multi_response("Tingkat: Nasional\nPenyelenggara: BEM FEB UNAIR")
    assert t == "Nasional" and o == "BEM FEB UNAIR", (t, o)
    t2, o2 = parse_multi_response("Tingkat: Fakultas\nPenyelenggara: TIDAK_ADA")
    assert t2 == "Fakultas" and o2 is None, (t2, o2)
    t3, o3 = parse_multi_response("Departemen/Program Studi")
    assert t3 == "Departemen/Program Studi" and o3 is None, (t3, o3)
    print("ok: llm_extractor_v5")
