"""B4 — Pengerasan Router Disambiguasi v7 (hardened copy, ROUTER-006 family).

Salinan TERHARDEN dari `_DISAMBIG_RULES` (`backend/app/services/combined_extractor.py`)
dengan substring landmine dihilangkan (audit QA B4):

  - `kim_unair`            : `"KIM" in a` -> `\\bKIM\\b` + tolak KIMIA/KIMIAWI
                             (cegah "Olimpiade KIMIA" -> Universitas).
  - `intl_explicit`        : `"OF INFORMATICS ENGINEERING" in u` -> guard
                             `FACULTY OF`/`DEPARTMENT OF`/`FAKULTAS` + daftar
                             institusi asing eksplisit (INSTITUT FRANÇAIS,
                             PARIS-SACLAY, EMBASSY OF FRANCE).
  - `ub_external_event`    : `"UB" in o` -> `\\bUB\\b|\\bBRAWIJAYA\\b|\\bFILKOM\\b`
                             (cegah "CLUB"/"HUBUNGAN").
  - `bem_nasional_act`     : `"HARI ANAK" in u` -> `"HARI ANAK NASIONAL"` utuh
                             (cegah "Hari Anak Kampus" tanpa NASIONAL).
  - `direktur_kemahasiswaan_unair` : rule formal #8 (guard Airlangga eksplisit).

Urutan aturan dan tata-cara (base router dulu, lalu rules) MENGIKUTI produksi.
Produksi `backend/` TIDAK disentuh — promosi menunggu keputusan user.
"""

from __future__ import annotations

import re
from typing import Callable

from app.services.tingkat_router import route_tingkat_trace

# --- Rule hardened -----------------------------------------------------------

# 1. aphsa_fkm — tanpa perubahan (sudah word-boundary).
# 2. bem_nasional_act — "HARI ANAK" substring dihilangkan.
# 3. kim_unair — word-boundary + negasi KIMIA.
# 4. dpkka_unair — tanpa perubahan.
# 5. intl_explicit — institusi asing eksplisit + guard faculty/dept.
# 6. literasi_psikologi — tanpa perubahan.
# 7. ub_external_event — word-boundary UB.
# 8. direktur_kemahasiswaan_unair — formal (dari apply_combined_v4_2 inline).

_FOREIGN_EXPLICIT = re.compile(
    r"INSTITUT\s+FRANÇAIS|INSTITUT\s+FRANCAIS|FRANCAIS|PARIS\s*-?\s*SACLAY|"
    r"EMBASSY\s+OF\s+FRANCE|UNIVERSITÉ\s*PARIS",
    re.IGNORECASE,
)
_OF_INF_ENG_GUARD = re.compile(r"\bFACULTY\s+OF\b|\bDEPARTMENT\s+OF\b|\bFAKULTAS\b", re.IGNORECASE)
_UB_BOUNDED = re.compile(r"\bUB\b|\bBRAWIJAYA\b|\bFILKOM\b", re.IGNORECASE)
_KIM_BOUNDED = re.compile(r"\bKIM\b")
_KIMIA_BLOCK = re.compile(r"\bKIMIA\b|\bKIMIAWI\b", re.IGNORECASE)
_HARI_ANAK_NASIONAL = re.compile(r"\bHARI\s+ANAK\s+NASIONAL\b", re.IGNORECASE)


def _cond_aphsa_fkm(u: str, o: str, a: str) -> bool:
    return bool(re.search(r"\bAPHSA\b", o))


def _cond_bem_nasional_act(u: str, o: str, a: str) -> bool:
    return bool(
        ("BEM" in o or "BEM" in u)
        and (_HARI_ANAK_NASIONAL.search(a) or "WEBINAR NASIONAL" in a or _HARI_ANAK_NASIONAL.search(u))
    )


def _cond_kim_unair(u: str, o: str, a: str) -> bool:
    return bool(
        "KOMPETISI ILMIAH MAHASISWA" in u
        or "KIM UNAIR" in u
        or (_KIM_BOUNDED.search(a) and not _KIMIA_BLOCK.search(a))
    )


def _cond_dpkka_unair(u: str, o: str, a: str) -> bool:
    return bool("DPKKA" in u or "DIREKTORAT PENGEMBANGAN KARIR" in u)


def _cond_intl_explicit(u: str, o: str, a: str) -> bool:
    if _FOREIGN_EXPLICIT.search(u):
        return True
    # "OF INFORMATICS ENGINEERING" hanya bermakna bila BUKAN fakultas lokal.
    if "OF INFORMATICS ENGINEERING" in u:
        return not bool(_OF_INF_ENG_GUARD.search(u))
    return False


def _cond_literasi_psikologi(u: str, o: str, a: str) -> bool:
    return bool("LITERASI PSIKOLOGI" in u)


def _cond_ub_external_event(u: str, o: str, a: str) -> bool:
    return bool(
        _UB_BOUNDED.search(o)
        and ("HOLOGY" in u or "GELAR RASA" in u or "HIMASADA" in o)
    )


def _cond_direktur_kemahasiswaan_unair(u: str, o: str, a: str) -> bool:
    return bool(
        ("DIREKTUR KEMAHASISWAAN" in u or "DIREKTURKEMAHASISWAAN" in u)
        and ("UNIVERSITAS AIRLANGGA" in u or "UNIVERSITASAIRLANGGA" in u or "UNAIR" in u)
    )


DISAMBIG_RULES_V7: list[tuple[str, str, Callable[[str, str, str], bool]]] = [
    ("aphsa_fkm", "Fakultas", _cond_aphsa_fkm),
    ("bem_nasional_act", "Nasional", _cond_bem_nasional_act),
    ("kim_unair", "Universitas", _cond_kim_unair),
    ("dpkka_unair", "Universitas", _cond_dpkka_unair),
    ("intl_explicit", "Internasional", _cond_intl_explicit),
    ("literasi_psikologi", "Nasional", _cond_literasi_psikologi),
    ("ub_external_event", "Nasional", _cond_ub_external_event),
    ("direktur_kemahasiswaan_unair", "Universitas", _cond_direktur_kemahasiswaan_unair),
]


def route_with_disambiguation_v7(
    raw_text: str, organizer: str, activity: str
) -> tuple[str | None, str]:
    """Router disambiguasi v7: base router dulu (produksi), lalu rules hardened."""
    base_val, base_rule = route_tingkat_trace(raw_text, organizer)
    if base_val is not None:
        return base_val, base_rule

    u = (raw_text or "").upper()
    o = (organizer or "").upper()
    a = (activity or "").upper()
    for rname, rtingkat, rcond in DISAMBIG_RULES_V7:
        if rcond(u, o, a):
            return rtingkat, f"disambig_{rname}"
    return None, ""
