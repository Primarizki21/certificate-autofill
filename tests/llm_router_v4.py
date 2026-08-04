"""Router tingkat untuk Phase 3 — rule-based decision, LLM fallback.

Empirically-validated ≥95% precision rules (74 certs, GT):
- lomba + (hima|univ|nasw|luar|fak|bem) -> Nasional       100% (n=17)
- dept + sem, tanpa lomba/nasw                              -> Departemen/Program Studi
- hima + luar                                               -> Nasional
- univ + luar, tanpa fak                                    -> Nasional
- dept + fak                                                -> Departemen/Program Studi
- dept + hima + univ                                        -> Departemen/Program Studi
- fak + univ, tanpa sem/nasw/lomba                          -> Fakultas
- bem + sem, tanpa lomba/hima/nasw                          -> Fakultas

Signal = kehadiran keyword di raw text / organizer (bukan lokasi fisik).
"""

import re


_LOMBA_MERGED = re.compile(
    r"LOMBA|PERLOMBAAN|COMPETITI|CHAMPIONSHIP|KEJUARAAN|OLIMPIADE"
    r"|KONTES|CHALLENGE|FESTIVAL|SPORT"
)


def _sig(raw_text: str, organizer: str) -> dict:
    u = raw_text.upper()
    o = (organizer or "").upper()
    o2 = re.sub(r"\bKAPRODI\b|\bKETUA PROGRAM STUDI\b", "", o)
    # Contains-based matching (v8 Phase 1): OCR menggabungkan kata
    # (BEMFKM, BEMFEBUNAIR, SERT2128BEM2026, HIMATESDA) yang lolos dari
    # word-boundary. Guard: BEM/HIMA hanya dianggap org bila berupa run
    # alnum huruf besar (bukan substring kata acak seperti PROBLEMATIC).
    bem_raw = re.search(r"\bBEM\b|(?<![A-Z])BEM(?=[A-Z0-9])", u)
    hima_raw = re.search(r"\bHIMA\b|(?<![A-Z])HIMA(?=[A-Z0-9])|HIMPUNAN", u)
    # Contains-based lomba: menangkap kata tergabung (OCRunion) tanpa spasi,
    # mis. "ACADEMICWEEKS2026", "INFographicCompetition". CUP word-boundary
    # saja, karena "DEKANCUPFTMM" (fakultas) bukan kompetisi.
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
        "hima": bool(
            re.search(r"HIMPUNAN|HIMA", o) or hima_raw
        ),
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
        "bem": bool(
            re.search(r"\bBEM\b", o) or bem_raw
        ),
    }


def _decide(s: dict) -> tuple[str | None, str]:
    """Return (rule_decision, rule_name). None -> route ke LLM."""
    # Teks eksplisit 'TINGKAT NASIONAL/LOMBA NASIONAL' menang (v8 Phase 1).
    # Hanya diaktifkan setelah GT audit: di v8 GT tidak ada cert dengan teks
    # eksplisit ini tapi GT != Nasional.
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
    """Return rule decision, or None untuk route ke LLM."""
    value, _ = _decide(_sig(raw_text, organizer))
    return value


def route_tingkat_trace(raw_text: str, organizer: str) -> tuple[str | None, str]:
    """Return (rule decision, rule name) untuk traceability benchmark."""
    return _decide(_sig(raw_text, organizer))


if __name__ == "__main__":
    cases = [
        ("LOMBA CIKAL 2024", "Himpunan Mahasiswa Teknik", "Nasional"),
        ("Seminar Nasional", "Departemen Matematika", None),
    ]
    for text, org, want in cases:
        got = route_tingkat(text, org)
        assert got == want, (text, org, got, want)
        got_t, rule = route_tingkat_trace(text, org)
        assert got_t == want and (rule or want is None), (text, org, got_t, rule)
    print("self-check ok")
