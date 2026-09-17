#!/usr/bin/env python3
"""Seed KHP master tables in PostgreSQL/SQLite from khp/aucc.sql snapshot.

Usage:
    python scripts/seed_khp_master.py [--force] [--path PATH]
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

# Ensure backend root is on sys.path
_repo_root = Path(__file__).resolve().parent.parent
_backend_dir = _repo_root / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from sqlalchemy.orm import Session
from app.config import settings
from app.database import Base, engine, SessionLocal
from app.models import (
    KHPKelompokKegiatan,
    KHPKegiatan1,
    KHPTingkat,
    KHPJabatanPrestasi,
    KHPKegiatan2,
    KHPMasterRule,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_khp_master")

_INSERT_RE = re.compile(
    r'^INSERT INTO "?aucc"?\."?([a-zA-Z0-9_]+)"? VALUES \((.*)\);$'
)


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
    return True


def parse_aucc_sql(sql_path: str | Path) -> dict[str, list[dict]]:
    path = Path(sql_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Snapshot AUCC SQL tidak ditemukan: {path}")

    logger.info("Membaca file SQL: %s", path)
    text = path.read_text(encoding="utf-8")

    data: dict[str, list[dict]] = {
        "kelompok_kegiatan": [],
        "kegiatan_1": [],
        "tingkat": [],
        "jabatan_prestasi": [],
        "kegiatan_2": [],
        "master_kegiatan_rule": [],
    }

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("INSERT INTO"):
            continue
        match = _INSERT_RE.match(line)
        if match is None:
            continue
        table_name, value_text = match.groups()
        if table_name not in data:
            continue
        vals = _split_sql_values(value_text)

        if table_name == "kelompok_kegiatan":
            # VALUES (1, 'Kegiatan Wajib Universitas', 't');
            data["kelompok_kegiatan"].append({
                "id_kelompok_kegiatan": _parse_int(vals[0]),
                "nm_kelompok_kegiatan": _parse_text(vals[1]) or "",
                "is_aktif": _parse_bool(vals[2]) if len(vals) > 2 else True,
            })
        elif table_name == "kegiatan_1":
            # VALUES (41, 'PKKMB', 1, 't');
            data["kegiatan_1"].append({
                "id_kegiatan_1": _parse_int(vals[0]),
                "nm_kegiatan_1": _parse_text(vals[1]) or "",
                "id_kelompok_kegiatan": _parse_int(vals[2]),
                "is_aktif": _parse_bool(vals[3]) if len(vals) > 3 else True,
            })
        elif table_name == "tingkat":
            # VALUES (1, 'Internasional');
            data["tingkat"].append({
                "id_tingkat": _parse_int(vals[0]),
                "nm_tingkat": _parse_text(vals[1]) or "",
            })
        elif table_name == "jabatan_prestasi":
            # VALUES (1, 'Ketua');
            data["jabatan_prestasi"].append({
                "id_jabatan_prestasi": _parse_int(vals[0]),
                "nm_jabatan_prestasi": _parse_text(vals[1]) or "",
            })
        elif table_name == "kegiatan_2":
            # VALUES (1, 41, 1, 1);
            data["kegiatan_2"].append({
                "id_kegiatan_2": _parse_int(vals[0]),
                "id_kegiatan_1": _parse_int(vals[1]),
                "id_tingkat": _parse_int(vals[2], nullable=True),
                "id_jabatan_prestasi": _parse_int(vals[3], nullable=True),
            })
        elif table_name == "master_kegiatan_rule":
            # VALUES (1, 26, 2, 67, 6, 1, 'Sert/SK/SP', 6883, 't', '...', '...');
            data["master_kegiatan_rule"].append({
                "id": _parse_int(vals[0]),
                "source_no": _parse_int(vals[1]),
                "id_kelompok_kegiatan": _parse_int(vals[2]),
                "id_kegiatan_1": _parse_int(vals[3]),
                "id_tingkat": _parse_int(vals[4], nullable=True),
                "id_jabatan_prestasi": _parse_int(vals[5], nullable=True),
                "dasar_penilaian": _parse_text(vals[6]) or "",
                "id_kegiatan_2": _parse_int(vals[7]),
                "is_active": _parse_bool(vals[8]) if len(vals) > 8 else True,
            })

    return data


def seed_khp_master(db: Session, sql_path: str | Path | None = None, force: bool = False) -> dict[str, int]:
    path = sql_path or settings.khp_aucc_sql_path
    data = parse_aucc_sql(path)

    # Check if data already exists
    existing_rules = db.query(KHPMasterRule).count()
    if existing_rules > 0 and not force:
        logger.info("Tabel KHP master sudah terisi (%d rules). Gunakan --force untuk replace.", existing_rules)
        return {
            "kelompok_kegiatan": db.query(KHPKelompokKegiatan).count(),
            "kegiatan_1": db.query(KHPKegiatan1).count(),
            "tingkat": db.query(KHPTingkat).count(),
            "jabatan_prestasi": db.query(KHPJabatanPrestasi).count(),
            "kegiatan_2": db.query(KHPKegiatan2).count(),
            "master_kegiatan_rule": existing_rules,
        }

    if force and existing_rules > 0:
        logger.warning("Menghapus data lama KHP master (--force)...")
        db.query(KHPMasterRule).delete()
        db.query(KHPKegiatan2).delete()
        db.query(KHPKegiatan1).delete()
        db.query(KHPKelompokKegiatan).delete()
        db.query(KHPTingkat).delete()
        db.query(KHPJabatanPrestasi).delete()
        db.commit()

    logger.info("Memulai seeding KHP master...")

    # 1. Kelompok Kegiatan
    db.bulk_insert_mappings(KHPKelompokKegiatan, data["kelompok_kegiatan"])
    db.commit()
    logger.info("Seeded %d kelompok_kegiatan", len(data["kelompok_kegiatan"]))

    # 2. Kegiatan 1
    db.bulk_insert_mappings(KHPKegiatan1, data["kegiatan_1"])
    db.commit()
    logger.info("Seeded %d kegiatan_1", len(data["kegiatan_1"]))

    # 3. Tingkat
    db.bulk_insert_mappings(KHPTingkat, data["tingkat"])
    db.commit()
    logger.info("Seeded %d tingkat", len(data["tingkat"]))

    # 4. Jabatan Prestasi
    db.bulk_insert_mappings(KHPJabatanPrestasi, data["jabatan_prestasi"])
    db.commit()
    logger.info("Seeded %d jabatan_prestasi", len(data["jabatan_prestasi"]))

    # 5. Kegiatan 2 (17,830 rows - batch in chunks)
    k2_rows = data["kegiatan_2"]
    chunk_size = 2000
    for i in range(0, len(k2_rows), chunk_size):
        db.bulk_insert_mappings(KHPKegiatan2, k2_rows[i:i + chunk_size])
        db.commit()
    logger.info("Seeded %d kegiatan_2", len(k2_rows))

    # 6. Master Kegiatan Rules
    db.bulk_insert_mappings(KHPMasterRule, data["master_kegiatan_rule"])
    db.commit()
    logger.info("Seeded %d master_kegiatan_rule", len(data["master_kegiatan_rule"]))

    return {
        "kelompok_kegiatan": len(data["kelompok_kegiatan"]),
        "kegiatan_1": len(data["kegiatan_1"]),
        "tingkat": len(data["tingkat"]),
        "jabatan_prestasi": len(data["jabatan_prestasi"]),
        "kegiatan_2": len(data["kegiatan_2"]),
        "master_kegiatan_rule": len(data["master_kegiatan_rule"]),
    }


def main():
    parser = argparse.ArgumentParser(description="Seed KHP master database from aucc.sql")
    parser.add_argument("--force", action="store_true", help="Clear and re-seed existing data")
    parser.add_argument("--path", default=None, help="Custom path to aucc.sql")
    args = parser.parse_args()

    # Create tables if not exist
    logger.info("Memastikan skema tabel ada di database target...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        counts = seed_khp_master(db, sql_path=args.path, force=args.force)
        logger.info("Seeding KHP master sukses: %s", counts)
    finally:
        db.close()


if __name__ == "__main__":
    main()
