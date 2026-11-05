"""Helper infrastruktur untuk eksperimen HTTP (server uvicorn + data seed)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parent.parent


def create_schema(database_url: str) -> None:
    from app import models  # noqa: F401
    from app.database import Base

    engine = create_engine(database_url)
    Base.metadata.create_all(bind=engine)
    engine.dispose()


def seed_completed_documents(database_url: str, count: int) -> list[str]:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE khp_master_resolutions, extracted_fields, extraction_jobs,"
                " documents RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO documents
                    (id, tahun_akademik, bukti_fisik, original_file_name, mime_type,
                     file_size, checksum_sha256, status, parser_engine, created_at, updated_at)
                SELECT gen_random_uuid(), '2024/2025', 'Sertifikat',
                       'seed_' || i || '.pdf', 'application/pdf', 800000,
                       md5(i::text), 'completed', 'seed', now(), now()
                FROM generate_series(1, :count) AS i
                """
            ),
            {"count": count},
        )
        connection.execute(
            text(
                """
                INSERT INTO extracted_fields
                    (id, document_id, form_field_name, extracted_value, mapped_value,
                     confidence, source, needs_review)
                SELECT gen_random_uuid(), d.id, f.name, 'Nilai ' || f.name,
                       'Nilai ' || f.name, 0.95, 'seed', false
                FROM documents d CROSS JOIN (VALUES
                    ('nama_kegiatan_sertifikasi'),
                    ('nomor_bukti_fisik_nomor_sertifikasi'),
                    ('penyelenggara_kegiatan'),
                    ('jenis_penyelenggara'),
                    ('waktu_mulai_pelaksanaan'),
                    ('waktu_selesai_pelaksanaan'),
                    ('tingkat'),
                    ('kelompok_kegiatan'),
                    ('jenis_kegiatan'),
                    ('prestasi_partisipasi_jabatan')
                ) AS f(name)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO khp_master_resolutions (id, document_id, resolution_json)
                SELECT gen_random_uuid()::text, d.id,
                       json_build_object('id_kegiatan_2', 5803, 'fields', json_build_object(
                           'kelompok_kegiatan', json_build_object('id', 1, 'label', 'Kegiatan'),
                           'jenis_kegiatan', json_build_object('id', 10, 'label', 'Seminar'),
                           'tingkat', json_build_object('id', 1, 'label', 'Nasional'),
                           'prestasi_partisipasi_jabatan', json_build_object('id', 1, 'label', 'Peserta')
                       ), 'reasons', '[]'::json)::text
                FROM documents d
                """
            )
        )
        document_ids = [
            row[0] for row in connection.execute(text("SELECT id::text FROM documents"))
        ]
    engine.dispose()
    return document_ids


def start_server(
    port: int, env: dict[str, str], log_path: str | None = None
) -> subprocess.Popen:
    stream = subprocess.DEVNULL
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        stream = open(log_path, "w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "1",
            "--log-level",
            "warning",
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=stream,
        stderr=subprocess.STDOUT,
        text=True,
    )
    process._log_stream = stream  # type: ignore[attr-defined]
    return process


def wait_ready(port: int, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/healthz"
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, OSError):
            pass
        time.sleep(0.5)
    raise SystemExit(f"server tidak siap pada port {port}")


def stop_server(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
