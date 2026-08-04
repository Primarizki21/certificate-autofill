"""Router tingkat rule-based (v8 Phase 1) — port dari tests/llm_router_v4.py.

Keputusan rule-based tingkat dengan precision >=95% (diukur pada 74 cert, GT
v8). None artinya serahkan ke LLM/fallback. Empirically-validated rules:
- lomba + (hima|univ|nasw|luar|fak|bem) -> Nasional
- dept + sem, tanpa lomba/nasw -> Departemen/Program Studi
- hima + luar -> Nasional; univ + luar tanpa fak -> Nasional
- dept + fak -> Departemen/Program Studi
- fak + univ, tanpa sem/nasw/lomba -> Fakultas
- bem + sem, tanpa lomba/hima/nasw -> Fakultas
"""

import re

_LOMBA_MERGED = re.compile(
    r"LOMBA|PERLOMBAAN|COMPETITI|CHAMPIONSHIP|KEJUARAAN|OLIMPIADE"
    r"|KONTES|CHALLENGE|FESTIVAL|SPORT"
)


def _sig(raw_text: str, organizer: str) -> dict:
    u = (raw_text or "").upper()
    o = (organizer or "").upper()
    o2 = re.sub(r"\bKAPRODI\b|\bKETUA PROGRAM STUDI\b", "", o)
    # Contains-based matching: OCR menggabungkan kata (BEMFKM, BEMFEBUNAIR,
    # SERT2128BEM2026, HIMATESDA) yang lolos dari word-boundary. Guard agar
    # bukan substring kata acak (PROBLEMATIC).
    bem_raw = re.search(r"\bBEM\b|(?<![A-Z])BEM(?=[A-Z0-9])", u)
    hima_raw = re.search(r"\bHIMA\b|(?<![A-Z])HIMA(?=[A-Z0-9])|HIMPUNAN", u)
    lomba_merged = (
        bool(re.search(r"\bCUP\b", u))
        or bool(_LOMBA_MERGED.search(re.sub(r"\bCUP\b", "", u)))
    ) and not re.search(r"PANITIA", u)
    return {
        "lomba": bool(re.search(
            r"\bLOMBA\b|\bKOMPETISI\b|\bCOMPETITION\b|\bOLIMPIADE\b"
            r"|\bCHALLENGE\b|\bTOURNAMENT\b|\bJUARA\b|\bCUP\b"
            r"|\bCHAMPIONSHIP\b|\bOLYMPIAD\b|\bHACKATHON\b", u)),
        "lomba_merged": lomba_merged,
        "hima": bool(re.search(r"HIMPUNAN|HIMA", o) or hima_raw),
        "dept": bool(re.search(
            r"\bDEPT\b|DEPARTMENT|STUDY PROGRAM|\bPRODI\b|PROGRAM STUDI", o2)),
        "univ": bool(re.search(
            r"UNIVERSITAS|UNIVERSITY|REKTORAT|DIREKTORAT|KEMAHASISWAAN", o)),
        "luar": bool(re.search(
            r"AIESEC|UNIMUS|UNISBA|UNS|USU|POLTEK|TELKOM|BRAWIJAYA|UGM|IPB"
            r"|PELITA HARAPAN|CALTEK|STAN|SACLAY|IRIS|BINUS|SRIWIJAYA|UNY|UNESA|PCR", o)),
        "nasw": bool(re.search(r"\bNASIONAL\b|\bNATIONAL\b", u)),
        "nasw_explicit": bool(re.search(
            r"TINGKAT\s+NASIONAL|LOMBA\s+NASIONAL|KOMPETISI\s+NASIONAL", u)),
        "sem": bool(re.search(
            r"\bSEMINAR\b|\bWORKSHOP\b|\bWEBINAR\b|\bGUEST LECTURE\b"
            r"|\bTALKSHOW\b|\bLECTURE\b|\bCOURSE\b|\bTRAINING\b|\bPELATIHAN\b", u)),
        "fak": bool(re.search(r"FAKULTAS|FACULTY", o)),
        "bem": bool(re.search(r"\bBEM\b", o) or bem_raw),
    }


def _decide(s: dict) -> tuple[str | None, str]:
    if s["nasw_explicit"]:
        return "Nasional", "tingkat_nasional"
    if s["lomba"] and (s["hima"] or s["univ"] or s["nasw"] or s["luar"] or s["fak"] or s["bem"]):
        return "Nasional", "lomba+org"
    if s["lomba_merged"] and (s["hima"] or s["univ"] or s["fak"] or s["bem"]):
        return "Nasional", "lomba_merged+org"
    if s["dept"] and s["sem"] and not s["lomba"] and not s["nasw"]:
        return "Departemen/Program Studi", "dept+sem"
    if s["hima"] and s["luar"]:
        return "Nasional", "hima+luar"
    if s["univ"] and s["luar"] and not s["fak"]:
        return "Nasional", "univ+luar"
    if s["dept"] and s["fak"]:
        return "Departemen/Program Studi", "dept+fak"
    if s["dept"] and s["hima"] and s["univ"]:
        return "Departemen/Program Studi", "dept+hima+univ"
    if s["fak"] and s["univ"] and not s["sem"] and not s["nasw"] and not s["lomba"]:
        return "Fakultas", "fak+univ"
    if s["bem"] and s["sem"] and not s["lomba"] and not s["hima"] and not s["nasw"]:
        return "Fakultas", "bem+sem"
    return None, ""


def route_tingkat(raw_text: str, organizer: str) -> str | None:
    value, _ = _decide(_sig(raw_text, organizer))
    return value


def route_tingkat_trace(raw_text: str, organizer: str) -> tuple[str | None, str]:
    return _decide(_sig(raw_text, organizer))
