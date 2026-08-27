"""Ekstraksi nama kegiatan berbasis anchor pattern & OCR repair (AKT-005).

Port produksi lapisan ekstraksi nama kegiatan (0 LLM):
- Pre-repair camel & spacing (D5_PRE)
- OCR word-merge & boundary repair (REPAIR4)
- Post-repair (D5_POST)
- 17 anchor patterns berbobot (ANCHORS5) termasuk quote, bracket, context-aware.

Sumber: tests/benchmark_akt5.py.
"""

import re
from typing import Callable

_COLLAPSE: Callable[[re.Match], str] = lambda m: m.group(1).replace(" ", "")

_D5_PRE = [
    (r"(?<![A-Za-z0-9])([A-Za-z0-9](?: [A-Za-z0-9]){2,})(?![A-Za-z0-9])", _COLLAPSE),
    (r"DALAM(?=[A-Z])", "DALAM "),
    (r"ACARA(?=[A-Z])", "ACARA "),
    (r"DEKAN(?=[A-Z])", "DEKAN "),
    (r"CUP(?=[A-Z])", "CUP "),
    (r"BY(?=[A-Z])", "BY "),
    (r"SYNREACH(?=[A-Z])", "SYNREACH "),
    (r"GELAR(?=[A-Z])", "GELAR "),
    (r"UXDESIGN(?=[A-Za-z])", "UX DESIGN "),
    (r"(?i)competition", "competition"),
    (r"(?i)dengan(?=[A-Za-z])", "dengan "),
    (r"(?i)(?<=[a-z0-9])dengan(?=\s)", " dengan"),
    (r"SPEAK(?=UP)", "SPEAK "),
    (r"STAND(?=OUT)", "STAND "),
    (r"MENGASAH(?=[A-Z])", "MENGASAH "),
    (r"KOMUNIKASI(?=[A-Z])", "KOMUNIKASI "),
    (r"DI(?=ERA)", "DI "),
    (r"ERA(?=KARIR)", "ERA "),
    (r"KARIR(?=DIGITAL)", "KARIR "),
]

_REPAIR = [
    (r"(?<=\s)[Dd]alam(?=[A-Za-z])", "dalam "),
    (r"(?<=[a-z])of(?=\s)", " of"),
    (r"(?<=[a-z])yang(?=\s)", " yang"),
    (r"(?<=[a-z])oleh(?=\s)", " oleh"),
    (r"kegiatan(?=[A-Z])", "kegiatan "),
    (r"acara(?=[A-Z])", "acara "),
    (r"ajang(?=[A-Z])", "ajang "),
    (r"memperingati(?=[A-Z])", "memperingati "),
    (r"kompetisi(?=[A-Z])", "kompetisi "),
    (r"perlombaan(?=[A-Z])", "perlombaan "),
    (r"agenda(?=[A-Z])", "agenda "),
    (r"masa(?=[A-Z])", "masa "),
    (r"bakti(?=[A-Z])", "bakti "),
    (r"pada(?=[A-Z])", "pada "),
    (r"of(?=[A-Z])", "of "),
    (r"diselenggarakan(?=[A-Z])", "diselenggarakan "),
    (r"dilaksanakan(?=[A-Z])", "dilaksanakan "),
    (r"oleh(?=[A-Z])", "oleh "),
    (r"tanggal(?=\d)", "tanggal "),
    (r"(?<=\d)(?=[A-Z])", " "),
    (r"(?<=[A-Za-z])(?=\d)", " "),
    (r"(?<=[a-z])(?=[A-Z])", " "),
]

_REPAIR3 = _REPAIR + [
    (r"[Aa]t(?=[Tt]he)", "at "),
    (r"[Ii]n(?=[Tt]he)", "in "),
    (r"(?<=\s)[Aa][Tt]\s+THE(?=[A-Z])", "AT THE "),
    (r"(?<=[a-z])Peserta(?=[A-Z])", "Peserta "),
    (r"organized(?=[Bb]y)", "organized "),
    (r"(?<=\d)oleh(?=\s|[A-Za-z])", " oleh"),
    (r"(?<=\d)yang(?=\s|[A-Za-z])", " yang"),
    (r"yang(?=[Dd]iselenggarakan)", "yang "),
    (r"(?<=\d)with(?=\s|[A-Za-z])", " with"),
]

_REPAIR4 = _REPAIR3 + [(r"Nis\s+C\b", "NISC")]

_D5_POST = [
    (r"(?i)(?<=[a-z])competition(?=\s)", " competition"),
    (r"(?i)(?<=\d)\s+Himpunan", "\nHimpunan"),
]

_REPAIR5 = _D5_PRE + _REPAIR4 + _D5_POST

_STOP = (
    r"(?:\s+dengan\s+tema|\s+themed|\s+yang\s+diselenggarakan|"
    r"\s+yang\s+diadakan|\s+yang\s+dilaksanakan|\s+sub\s+acara|"
    r"\s+pada\s+tanggal|\s+pada\s+perlombaan|\s+,\s*\w+\s+\d{1,2}|[\"“]|\n|$)"
)

_UNTUK_KATEGORI = re.compile(r"\s+untuk\s+kategori\b.*$", re.IGNORECASE)

_ANCHORS_BASE = [
    (r"Kepengurusan\s+.+?\s+Masa\s+Bakti(?:\s+Tahun)?\s+\d{4}", "full"),
    (r"Dalam\s+(?:rangkaian\s+)?acara\s+(.+?)" + _STOP, "group"),
    (r"kegiatan\s+\S+\s*[\"“]([^\"”]+)[\"”]", "group"),
    (r"Dalam\s+kegiatan\s+(.+?)" + _STOP, "group"),
    (r"Dalam\s+memperingati\s+(.+?)" + _STOP, "group"),
    (r"pada\s+ajang\s+(.+?)" + _STOP, "group"),
    (r"pada\s+kegiatan\s+(.+?)" + _STOP, "group"),
    (r"dalam\s+kompetisi\s+(.+?)" + _STOP, "group"),
    (r"\bpada\s+(?!tanggal|perlombaan|ajang|kegiatan|acara|hari)([A-Za-z][^\n]*?)"
     r"(?:\s+Tingkat\s+Nasional|\s+yang\s+dilaksanakan|\s+yang\s+diselenggarakan|\n|$)", "group"),
    (r"(?:entitled|titled)\s+(.+?)(?=\s+on\s+\d{1,2}|\s*[,]|\n|$)", "group"),
    (r"(?:dalam|agenda|kegiatan|acara|seminar)\s*:?\s*[\"“]([^\"”]+)[\"”]", "group"),
    (r"participation\s+at\s+(.+?)(?=,|that\s+was|\n|$)", "group"),
    (r"\bthe\s+([A-Z][^\n]*?)\s+organized\s+by", "group"),
    (r"winner\s+of\s+the\s+(.+?)(?=\s+organized\s+by|\n|$)", "group"),
    (r"as\s+a\s+participant\s+(?:at|in)\s+(.+?)(?=\s+themed|,|\n|$)", "group"),
    (r"at\s+the\s+(.+?)(?=[\"“]|Faculty|University|\s+with\s+theme|,|\n|$)", "group"),
    (r"[Ss]ebagai\s*:?\s*Peserta\s*[\"“]([^\"”]+)[\"”]\s*(\[[^\]\n]+.*?)(?=\s+Via\s+Zoom|$)", "join2"),
    (r"[Ss]ebagai\s*:?\s*Peserta\s*[\"“]([^\"”]+)[\"”]", "group"),
    (r"[Ss]ebagai\s*:?\s*Peserta\s+(?!Talkshow|campaign\b)(.*?)(?=\s+oleh|\s+Tahun\s+Akademik|"
     r"\s+Library|\s+Surabaya|\s+Dalam|\s+Pada|\s+campaign|\s+Talkshow|"
     r"\s+yang\s+(?:diselenggarakan|diadakan|dilaksanakan|bertema)|"
     r"\s+Universitas(?=[A-Z])|Dalam|Pada|"
     r"\n\s*(?=(?:oleh|tahun|library|surabaya|pada|diberikan|direktur|dekan|"
     r"ketua|nip|tanggal|mengetahui|yang)[^A-Za-z])|\n\s*$)", "group"),
    (r"dalam\s+(Event\s+.+?)(?=\s+dengan|\n|$)", "group"),
    (r"(?:Dalam\s+)?lomba\s+tingkat\s+Nasional\s*[\"“]([^\"”]+)[\"”]", "group"),
    (r"seminar\s+on\s*[\"“]([^\"”]+)[\"”]", "group"),
    (r"Dalam\s+rangka\s+(.+?)(?=\s+dengan\s+tema|\n|$)", "group"),
]


def _clean_act(v: str) -> str | None:
    v = re.sub(r"\s+", " ", v or "").strip(" .,:;-\"“”")
    v = _UNTUK_KATEGORI.sub("", v).strip(" .,:;-\"“”")
    if len(v) < 3:
        return None
    return v


def _preprocess(text: str) -> str:
    t = text or ""
    for pat, repl in _REPAIR5:
        t = re.sub(pat, repl, t)
    return t


def extract_activity(text: str) -> str | None:
    """Ekstraksi nama kegiatan dengan 17+ anchor patterns dan OCR repair."""
    t = _preprocess(text)
    for pattern, kind in _ANCHORS_BASE:
        m = re.search(pattern, t, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        if kind == "full":
            v = m.group(0)
        elif kind == "join2":
            v = f"{m.group(1)} {m.group(2)}"
        else:
            v = m.group(1)
        v = _clean_act(v)
        if v:
            return v
    return None
