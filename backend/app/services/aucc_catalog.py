from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import settings


@dataclass(frozen=True, slots=True)
class Kegiatan2LookupRow:
    id_kegiatan_2: int
    id_kegiatan_1: int
    id_tingkat: int | None
    id_jabatan_prestasi: int | None


@dataclass(frozen=True, slots=True)
class MasterKegiatanRule:
    source_no: int
    id_kelompok_kegiatan: int
    id_kegiatan_1: int
    id_tingkat: int | None
    id_jabatan_prestasi: int | None
    dasar_penilaian: str
    id_kegiatan_2: int
    is_active: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "source_no": self.source_no,
            "id_kelompok_kegiatan": self.id_kelompok_kegiatan,
            "id_kegiatan_1": self.id_kegiatan_1,
            "id_tingkat": self.id_tingkat,
            "id_jabatan_prestasi": self.id_jabatan_prestasi,
            "dasar_penilaian": self.dasar_penilaian,
            "id_kegiatan_2": self.id_kegiatan_2,
            "is_active": self.is_active,
        }


@dataclass(frozen=True, slots=True)
class AuccCatalog:
    kegiatan2_rows: tuple[Kegiatan2LookupRow, ...]
    master_rules: tuple[MasterKegiatanRule, ...]


_INSERT_RE = re.compile(
    r'^INSERT INTO "?aucc"?\."?(kegiatan_2|master_kegiatan_rule)"? VALUES \((.*)\);$'
)
logger = logging.getLogger(__name__)


def _split_sql_values(value_text: str) -> tuple[str, ...]:
    values: list[str] = []
    token: list[str] = []
    in_string = False
    index = 0
    while index < len(value_text):
        character = value_text[index]
        if character == "'":
            token.append(character)
            if in_string and index + 1 < len(value_text) and value_text[index + 1] == "'":
                token.append("'")
                index += 2
                continue
            in_string = not in_string
        elif character == "," and not in_string:
            values.append("".join(token).strip())
            token = []
        else:
            token.append(character)
        index += 1
    if in_string:
        raise ValueError("unterminated SQL string")
    values.append("".join(token).strip())
    return tuple(values)


def _parse_text(token: str) -> str | None:
    if token == "NULL":
        return None
    if token.startswith("E'") and token.endswith("'"):
        token = token[1:]
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1].replace("''", "'")
    return token


def _parse_int(token: str, *, nullable: bool = False) -> int | None:
    if token == "NULL":
        if nullable:
            return None
        raise ValueError("unexpected NULL integer")
    return int(token)


def _parse_bool(token: str) -> bool:
    normalized = (_parse_text(token) or "").casefold()
    if normalized in {"t", "true", "1"}:
        return True
    if normalized in {"f", "false", "0"}:
        return False
    raise ValueError("invalid boolean")


def load_aucc_catalog(path: str | Path) -> AuccCatalog:
    source_path = Path(path).expanduser()
    text = source_path.read_text(encoding="utf-8")
    kegiatan2_rows: list[Kegiatan2LookupRow] = []
    master_rules: list[MasterKegiatanRule] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _INSERT_RE.match(line.strip())
        if match is None:
            continue
        table_name, value_text = match.groups()
        values = _split_sql_values(value_text)
        try:
            if table_name == "kegiatan_2":
                if len(values) != 4:
                    raise ValueError("unexpected kegiatan_2 column count")
                kegiatan2_rows.append(
                    Kegiatan2LookupRow(
                        id_kegiatan_2=_parse_int(values[0]),
                        id_kegiatan_1=_parse_int(values[1]),
                        id_tingkat=_parse_int(values[2], nullable=True),
                        id_jabatan_prestasi=_parse_int(values[3], nullable=True),
                    )
                )
            else:
                if len(values) != 11:
                    raise ValueError("unexpected master rule column count")
                dasar_penilaian = _parse_text(values[6])
                if dasar_penilaian is None:
                    raise ValueError("missing evidence requirement")
                master_rules.append(
                    MasterKegiatanRule(
                        source_no=_parse_int(values[1]),
                        id_kelompok_kegiatan=_parse_int(values[2]),
                        id_kegiatan_1=_parse_int(values[3]),
                        id_tingkat=_parse_int(values[4], nullable=True),
                        id_jabatan_prestasi=_parse_int(values[5], nullable=True),
                        dasar_penilaian=dasar_penilaian,
                        id_kegiatan_2=_parse_int(values[7]),
                        is_active=_parse_bool(values[8]),
                    )
                )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid {table_name} row at line {line_number}") from exc
    if not kegiatan2_rows:
        raise ValueError("AUCC snapshot has no kegiatan_2 rows")
    kegiatan2_ids = [row.id_kegiatan_2 for row in kegiatan2_rows]
    if len(kegiatan2_ids) != len(set(kegiatan2_ids)):
        raise ValueError("AUCC snapshot has duplicate kegiatan_2 IDs")
    source_numbers = [rule.source_no for rule in master_rules]
    if len(source_numbers) != len(set(source_numbers)):
        raise ValueError("AUCC snapshot has duplicate master rule source numbers")
    return AuccCatalog(tuple(kegiatan2_rows), tuple(master_rules))


@lru_cache(maxsize=8)
def _load_cached(path: str, mtime_ns: int, size: int) -> AuccCatalog | None:
    try:
        return load_aucc_catalog(path)
    except (OSError, ValueError):
        logger.warning("Unable to load AUCC master snapshot: %s", path)
        return None


def get_aucc_catalog(path: str | Path) -> AuccCatalog | None:
    source_path = Path(path).expanduser()
    try:
        metadata = source_path.stat()
    except OSError:
        return None
    return _load_cached(str(source_path), metadata.st_mtime_ns, metadata.st_size)


def get_default_aucc_catalog() -> AuccCatalog | None:
    return get_aucc_catalog(settings.khp_aucc_sql_path)


def warm_aucc_catalog() -> AuccCatalog | None:
    return get_default_aucc_catalog()
