"""EXP-DB-VOLUME-001: validasi volume 360k dokumen pada PostgreSQL.

Mengisi database eksperimen dengan data sintetis berskala target produksi,
lalu mengukur ukuran tabel, latensi query hasil ekstraksi, waktu VACUUM,
serta waktu dan ukuran pg_dump / pg_restore.

Bukan unit test. Jalankan manual:
    EXP_DATABASE_URL=postgresql+psycopg2://... \
    python -m tests.benchmark_db_volume --pg-container <nama-kontainer>
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from tests.experiment_io import write_bundle

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_ID = "EXP-DB-VOLUME-001"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "experiments" / EXPERIMENT_ID

FIELD_NAMES = (
    "nama_kegiatan_sertifikasi",
    "nomor_bukti_fisik_nomor_sertifikasi",
    "penyelenggara_kegiatan",
    "jenis_penyelenggara",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "tingkat",
    "kelompok_kegiatan",
    "jenis_kegiatan",
    "prestasi_partisipasi_jabatan",
)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(fraction * len(ordered)))
    return ordered[index]


def git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def recreate_schema(engine: Engine) -> None:
    from app.database import Base
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def seed(engine: Engine, docs: int, fields_per_doc: int) -> None:
    field_values = ", ".join(f"('{name}')" for name in FIELD_NAMES[:fields_per_doc])
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE khp_master_resolutions, extracted_fields, extraction_jobs,"
                " documents RESTART IDENTITY CASCADE"
            )
        )
        started = time.perf_counter()
        connection.execute(
            text(
                """
                INSERT INTO documents
                    (id, tahun_akademik, bukti_fisik, original_file_name, mime_type,
                     file_size, checksum_sha256, status, parser_engine, created_at, updated_at)
                SELECT gen_random_uuid(), '2024/2025', 'Sertifikat',
                       'sertifikat_' || i || '.pdf', 'application/pdf', 800000,
                       md5(i::text), 'completed', 'benchmark',
                       now() - (i || ' seconds')::interval, now()
                FROM generate_series(1, :docs) AS i
                """
            ),
            {"docs": docs},
        )
        connection.execute(
            text(
                """
                INSERT INTO extraction_jobs
                    (id, document_id, status, retry_count, created_at, started_at, finished_at)
                SELECT gen_random_uuid(), d.id,
                       CASE WHEN d.rn % 20 = 0 THEN 'queued' ELSE 'completed' END,
                       0, d.created_at, d.created_at, d.created_at
                FROM (SELECT id, created_at, row_number() OVER () AS rn FROM documents) d
                """
            )
        )
        connection.execute(
            text(
                f"""
                INSERT INTO extracted_fields
                    (id, document_id, form_field_name, extracted_value, mapped_value,
                     confidence, source, needs_review)
                SELECT gen_random_uuid(), d.id, f.name,
                       'Nilai ' || f.name || ' ' || left(md5(random()::text), 12),
                       'Nilai ' || f.name || ' ' || left(md5(random()::text), 12),
                       0.95, 'benchmark', false
                FROM documents d CROSS JOIN (VALUES {field_values}) AS f(name)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO khp_master_resolutions (id, document_id, resolution_json)
                SELECT gen_random_uuid()::text, d.id,
                       json_build_object(
                           'id_kegiatan_2', 5803,
                           'fields', json_build_object(
                               'kelompok_kegiatan', json_build_object('id', 1, 'label', 'Kegiatan Bidang Organisasi'),
                               'jenis_kegiatan', json_build_object('id', 10, 'label', 'Seminar'),
                               'tingkat', json_build_object('id', 1, 'label', 'Nasional'),
                               'prestasi_partisipasi_jabatan', json_build_object('id', 1, 'label', 'Peserta')
                           ),
                           'reasons', '[]'::json,
                           'evidence_status', 'matched'
                       )::text
                FROM documents d
                """
            )
        )
        seed_seconds = time.perf_counter() - started
    return seed_seconds


def table_sizes(engine: Engine) -> dict[str, int]:
    query = text(
        """
        SELECT 'documents', pg_total_relation_size('documents')
        UNION ALL SELECT 'extraction_jobs', pg_total_relation_size('extraction_jobs')
        UNION ALL SELECT 'extracted_fields', pg_total_relation_size('extracted_fields')
        UNION ALL SELECT 'khp_master_resolutions', pg_total_relation_size('khp_master_resolutions')
        """
    )
    with engine.connect() as connection:
        sizes = dict(connection.execute(query).all())
        sizes["database"] = connection.execute(
            text("SELECT pg_database_size(current_database())")
        ).scalar_one()
    return sizes


def measure_latency(engine: Engine, samples: int) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        document_ids = [
            row[0]
            for row in connection.execute(
                text("SELECT id::text FROM documents ORDER BY random() LIMIT :samples"),
                {"samples": samples},
            )
        ]
        doc_query = text(
            "SELECT id, status, file_size, checksum_sha256 FROM documents WHERE id = :doc_id"
        )
        fields_query = text(
            "SELECT form_field_name, mapped_value, confidence, needs_review"
            " FROM extracted_fields WHERE document_id = :doc_id"
        )
        resolution_query = text(
            "SELECT resolution_json FROM khp_master_resolutions WHERE document_id = :doc_id"
        )
        records: list[dict[str, Any]] = []
        for document_id in document_ids:
            start = time.perf_counter()
            connection.execute(doc_query, {"doc_id": document_id}).all()
            after_document = time.perf_counter()
            connection.execute(fields_query, {"doc_id": document_id}).all()
            after_fields = time.perf_counter()
            connection.execute(resolution_query, {"doc_id": document_id}).all()
            after_resolution = time.perf_counter()
            records.append(
                {
                    "document_id": document_id,
                    "document_ms": round((after_document - start) * 1000, 4),
                    "fields_ms": round((after_fields - after_document) * 1000, 4),
                    "resolution_ms": round((after_resolution - after_fields) * 1000, 4),
                    "total_ms": round((after_resolution - start) * 1000, 4),
                }
            )
    return records


def measure_vacuum(engine: Engine) -> float:
    start = time.perf_counter()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("VACUUM (ANALYZE)"))
    return time.perf_counter() - start


def run_in_container(container: str, command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "exec", container, *command], capture_output=True, text=True)


def measure_dump_restore(
    engine: Engine, container: str, database: str
) -> dict[str, Any]:
    result: dict[str, Any] = {"dump_status": "NOT_RUN", "restore_status": "NOT_RUN"}
    dump_path = "/tmp/exp_db_volume.dump"
    start = time.perf_counter()
    dump = run_in_container(
        container, ["pg_dump", "-Fc", "-U", "postgres", "-d", database, "-f", dump_path]
    )
    result["dump_seconds"] = round(time.perf_counter() - start, 2)
    if dump.returncode != 0:
        result["dump_status"] = "FAIL"
        result["dump_error"] = dump.stderr[-500:]
        return result
    result["dump_status"] = "PASS"
    size = run_in_container(container, ["du", "-b", dump_path])
    result["dump_bytes"] = int(size.stdout.split()[0]) if size.returncode == 0 else None

    restore_db = f"{database}_restore"
    run_in_container(container, ["dropdb", "-U", "postgres", "--if-exists", restore_db])
    run_in_container(container, ["createdb", "-U", "postgres", restore_db])
    start = time.perf_counter()
    restore = run_in_container(
        container,
        ["pg_restore", "-U", "postgres", "-d", restore_db, "--no-owner", "--no-privileges", dump_path],
    )
    result["restore_seconds"] = round(time.perf_counter() - start, 2)
    if restore.returncode != 0:
        result["restore_status"] = "FAIL"
        result["restore_error"] = restore.stderr[-500:]
        return result
    result["restore_status"] = "PASS"

    restored_engine = create_engine(
        engine.url.set(database=restore_db).render_as_string(hide_password=False)
    )
    with restored_engine.connect() as connection:
        result["restored_documents"] = connection.execute(
            text("SELECT count(*) FROM documents")
        ).scalar_one()
        result["restored_fields"] = connection.execute(
            text("SELECT count(*) FROM extracted_fields")
        ).scalar_one()
    restored_engine.dispose()
    run_in_container(container, ["dropdb", "-U", "postgres", restore_db])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("EXP_DATABASE_URL", ""))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--docs", type=int, default=360_000)
    parser.add_argument("--fields-per-doc", type=int, default=10)
    parser.add_argument("--latency-samples", type=int, default=1_000)
    parser.add_argument("--pg-container", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("--database-url atau EXP_DATABASE_URL wajib diisi")
    if "exp" not in args.database_url and not args.force:
        raise SystemExit("URL database harus memuat 'exp' atau gunakan --force")
    if args.pg_container and "exp" not in args.database_url.split("/")[-1]:
        raise SystemExit("Nama database eksperimen harus memuat 'exp'")

    started_at = datetime.now(timezone.utc)
    engine = create_engine(args.database_url)
    recreate_schema(engine)

    seed_seconds = seed(engine, args.docs, args.fields_per_doc)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("ANALYZE"))

    sizes = table_sizes(engine)
    vacuum_seconds = measure_vacuum(engine)
    records = measure_latency(engine, args.latency_samples)
    total_latencies = [record["total_ms"] for record in records]
    database = engine.url.database or ""

    dump_metrics = (
        measure_dump_restore(engine, args.pg_container, database)
        if args.pg_container
        else {"dump_status": "NOT_RUN", "restore_status": "NOT_RUN"}
    )

    metrics = {
        "experiment_id": EXPERIMENT_ID,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision(),
        "config": {
            "documents": args.docs,
            "fields_per_document": args.fields_per_doc,
            "latency_samples": args.latency_samples,
        },
        "row_counts": {
            "documents": args.docs,
            "extraction_jobs": args.docs,
            "extracted_fields": args.docs * args.fields_per_doc,
            "khp_master_resolutions": args.docs,
        },
        "sizes_bytes": sizes,
        "timing_seconds": {
            "seed": round(seed_seconds, 2),
            "vacuum_analyze": round(vacuum_seconds, 2),
            **{key: value for key, value in dump_metrics.items() if key.endswith("_seconds")},
        },
        "latency_ms": {
            "document_p50": round(percentile([r["document_ms"] for r in records], 0.50), 4),
            "fields_p50": round(percentile([r["fields_ms"] for r in records], 0.50), 4),
            "resolution_p50": round(percentile([r["resolution_ms"] for r in records], 0.50), 4),
            "total_p50": round(percentile(total_latencies, 0.50), 4),
            "total_p95": round(percentile(total_latencies, 0.95), 4),
            "total_p99": round(percentile(total_latencies, 0.99), 4),
            "total_max": round(max(total_latencies), 4),
        },
        "dump_restore": dump_metrics,
        "gates": {
            "result_p95_under_100ms": percentile(total_latencies, 0.95) < 100,
            "dump_under_4gb": (
                (dump_metrics.get("dump_bytes") or 0) <= 4 * 1024**3
                if dump_metrics.get("dump_status") == "PASS"
                else None
            ),
            "restore_under_15min": (
                dump_metrics.get("restore_seconds", 10**9) <= 900
                if dump_metrics.get("restore_status") == "PASS"
                else None
            ),
        },
    }

    status = "PASS"
    if not metrics["gates"]["result_p95_under_100ms"]:
        status = "FAIL"
    if metrics["gates"]["dump_under_4gb"] is False or metrics["gates"]["restore_under_15min"] is False:
        status = "FAIL"
    if dump_metrics.get("dump_status") == "NOT_RUN":
        status = "STAGING_ONLY"

    rows = [
        {"metric": name, "value": value, "unit": "bytes"}
        for name, value in sizes.items()
    ] + [
        {"metric": f"latency_{key}", "value": value, "unit": "ms"}
        for key, value in metrics["latency_ms"].items()
    ] + [
        {"metric": f"timing_{key}", "value": value, "unit": "seconds"}
        for key, value in metrics["timing_seconds"].items()
    ]

    gb = 1024**3
    summary = f"""# {EXPERIMENT_ID} — Volume Database 360k Dokumen

Status: **{status}**

## Konfigurasi
- Dokumen: {args.docs:,}
- Field per dokumen: {args.fields_per_doc}
- Total baris: {args.docs * (2 + args.fields_per_doc):,}
- Sampel latensi: {args.latency_samples:,}

## Ukuran
| Objek | Ukuran |
|---|---|
| documents | {sizes['documents'] / gb:.3f} GB |
| extraction_jobs | {sizes['extraction_jobs'] / gb:.3f} GB |
| extracted_fields | {sizes['extracted_fields'] / gb:.3f} GB |
| khp_master_resolutions | {sizes['khp_master_resolutions'] / gb:.3f} GB |
| database total | {sizes['database'] / gb:.3f} GB |

## Latensi query hasil ekstraksi
| Metrik | Nilai |
|---|---|
| p50 | {metrics['latency_ms']['total_p50']:.3f} ms |
| p95 | {metrics['latency_ms']['total_p95']:.3f} ms |
| p99 | {metrics['latency_ms']['total_p99']:.3f} ms |
| max | {metrics['latency_ms']['total_max']:.3f} ms |

## Backup dan restore
- Dump: {dump_metrics.get('dump_status')} ({dump_metrics.get('dump_seconds', 'n/a')} s,
  {dump_metrics.get('dump_bytes') or 0} byte)
- Restore: {dump_metrics.get('restore_status')} ({dump_metrics.get('restore_seconds', 'n/a')} s)
- Baris terpulihkan: documents={dump_metrics.get('restored_documents', 'n/a')},
  extracted_fields={dump_metrics.get('restored_fields', 'n/a')}

## Gate
| Gate | Hasil |
|---|---|
| p95 < 100 ms | {metrics['gates']['result_p95_under_100ms']} |
| dump <= 4 GB | {metrics['gates']['dump_under_4gb']} |
| restore <= 15 menit | {metrics['gates']['restore_under_15min']} |

## Interpretasi
Ukuran database menentukan strategi backup dan kebutuhan disk. Latensi p95
menunjukkan apakah endpoint hasil tetap nyaman dipakai saat data penuh.
"""
    manifest = {
        "campaign_id": "CAMPAIGN-PRODUCTION-CAPACITY",
        "experiment_id": EXPERIMENT_ID,
        "parent_id": None,
        "role": "capacity-db-volume",
        "started_at": metrics["started_at"],
        "finished_at": metrics["finished_at"],
        "git_revision": metrics["git_revision"],
        "command": "python -m tests.benchmark_db_volume",
        "status": status,
        "inputs": {
            "documents": args.docs,
            "fields_per_document": args.fields_per_doc,
            "pg_container": args.pg_container or None,
        },
        "supersedes": None,
    }

    write_bundle(
        args.output_dir,
        rows=rows,
        records=records,
        metrics=metrics,
        manifest=manifest,
        summary=summary,
        xlsx_sheets={"Ringkasan": rows, "Latensi": records},
        force=args.force,
    )
    print(f"{EXPERIMENT_ID}: {status} -> {args.output_dir}")


if __name__ == "__main__":
    main()
