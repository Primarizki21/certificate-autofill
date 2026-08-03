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


def _sig(raw_text: str, organizer: str) -> dict:
    u = raw_text.upper()
    o = (organizer or "").upper()
    o2 = re.sub(r"\bKAPRODI\b|\bKETUA PROGRAM STUDI\b", "", o)
    return {
        "lomba": bool(re.search(
            r"\bLOMBA\b|\bKOMPETISI\b|\bCOMPETITION\b|\bOLIMPIADE\b"
            r"|\bCHALLENGE\b|\bTOURNAMENT\b|\bJUARA\b|\bCUP\b"
            r"|\bCHAMPIONSHIP\b|\bOLYMPIAD\b|\bHACKATHON\b", u)),
        "hima": bool(re.search(r"HIMPUNAN|HIMA", o)),
        "dept": bool(re.search(
            r"\bDEPT\b|DEPARTMENT|STUDY PROGRAM|\bPRODI\b|PROGRAM STUDI", o2)),
        "univ": bool(re.search(
            r"UNIVERSITAS|UNIVERSITY|REKTORAT|DIREKTORAT|KEMAHASISWAAN", o)),
        "luar": bool(re.search(
            r"AIESEC|UNIMUS|UNISBA|UNS|USU|POLTEK|TELKOM|BRAWIJAYA|UGM|IPB"
            r"|PELITA HARAPAN|CALTEK|STAN|SACLAY|IRIS|BINUS|SRIWIJAYA|UNY|UNESA|PCR", o)),
        "nasw": bool(re.search(r"\bNASIONAL\b|\bNATIONAL\b", u)),
        "sem": bool(re.search(
            r"\bSEMINAR\b|\bWORKSHOP\b|\bWEBINAR\b|\bGUEST LECTURE\b"
            r"|\bTALKSHOW\b|\bLECTURE\b|\bCOURSE\b|\bTRAINING\b|\bPELATIHAN\b", u)),
        "fak": bool(re.search(r"FAKULTAS|FACULTY", o)),
        "bem": bool(re.search(r"\bBEM\b", o)),
    }


def route_tingkat(raw_text: str, organizer: str) -> str | None:
    """Return rule decision, or None untuk route ke LLM."""
    s = _sig(raw_text, organizer)
    if s["lomba"] and (s["hima"] or s["univ"] or s["nasw"] or s["luar"] or s["fak"] or s["bem"]):
        return "Nasional"
    if s["dept"] and s["sem"] and not s["lomba"] and not s["nasw"]:
        return "Departemen/Program Studi"
    if s["hima"] and s["luar"]:
        return "Nasional"
    if s["univ"] and s["luar"] and not s["fak"]:
        return "Nasional"
    if s["dept"] and s["fak"]:
        return "Departemen/Program Studi"
    if s["dept"] and s["hima"] and s["univ"]:
        return "Departemen/Program Studi"
    if s["fak"] and s["univ"] and not s["sem"] and not s["nasw"] and not s["lomba"]:
        return "Fakultas"
    if s["bem"] and s["sem"] and not s["lomba"] and not s["hima"] and not s["nasw"]:
        return "Fakultas"
    return None


if __name__ == "__main__":
    cases = [
        ("LOMBA CIKAL 2024", "Himpunan Mahasiswa Teknik", "Nasional"),
        ("Seminar Nasional", "Departemen Matematika", None),
    ]
    for text, org, want in cases:
        got = route_tingkat(text, org)
        assert got == want, (text, org, got, want)
    print("self-check ok")
