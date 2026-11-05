"""EXP-WORKER-THROUGHPUT-001: kapasitas worker pada 104 sertifikat.

Menjalankan pipeline offline (tanpa Gemini) melalui antrean database nyata
dengan beberapa tingkat concurrency, lalu mengukur dokumen/jam, latensi
per dokumen, kegagalan, dan pemakaian memori.

Jalankan manual:
    EXP_DATABASE_URL=postgresql+psycopg2://... \
    python -m tests.benchmark_worker_throughput
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from tests.experiment_io import write_bundle

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_ID = "EXP-WORKER-THROUGHPUT-001"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "experiments" / EXPERIMENT_ID
MANIFEST_PATH = REPO_ROOT / "certs_unified" / "manifest.json"


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(fraction * len(ordered)))
    return ordered[index]


def git_revision() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_certificates() -> list[dict[str, Any]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    certificates: list[dict[str, Any]] = []
    for entry in manifest:
        if not entry.get("file_exists"):
            continue
        path = REPO_ROOT / entry["unified_path"]
        if path.exists():
            certificates.append({"stem": path.stem, "path": path})
    return certificates


def reset_tables(session_factory) -> None:
    from app.models import Document, ExtractionJob, ExtractedField, KHPMasterResolution

    session = session_factory()
    try:
        session.query(ExtractedField).delete()
        session.query(KHPMasterResolution).delete()
        session.query(ExtractionJob).delete()
        session.query(Document).delete()
        session.commit()
    finally:
        session.close()


def seed_jobs(session_factory, upload_store, certificates: list[dict[str, Any]]) -> None:
    import uuid

    from app.models import Document, ExtractionJob

    session = session_factory()
    try:
        for certificate in certificates:
            content = certificate["path"].read_bytes()
            temp_key = upload_store.stage_bytes(content, certificate["path"].name)
            document_id = str(uuid.uuid4())
            session.add(
                Document(
                    id=document_id,
                    source_system="experiment",
                    tahun_akademik="2024/2025",
                    bukti_fisik="Sertifikat",
                    original_file_name=certificate["path"].name,
                    mime_type="application/pdf",
                    file_size=len(content),
                    checksum_sha256=uuid.uuid4().hex,
                    status="queued",
                )
            )
            session.add(
                ExtractionJob(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    status="queued",
                    retry_count=0,
                    temp_file_key=temp_key,
                )
            )
        session.commit()
    finally:
        session.close()


def run_level(session_factory, concurrency: int) -> dict[str, Any]:
    from app.services.job_processor import process_document_job

    stop = threading.Event()
    process = psutil.Process()

    def loop(thread_id: int) -> None:
        while not stop.is_set():
            processed = process_document_job(worker_id=f"exp-worker-t{thread_id}")
            if not processed:
                stop.set()

    rss_before = process.memory_info().rss
    cpu_before = process.cpu_times()
    started = time.perf_counter()
    threads = [
        threading.Thread(target=loop, args=(index,), daemon=True)
        for index in range(1, concurrency + 1)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall_seconds = time.perf_counter() - started
    rss_after = process.memory_info().rss
    cpu_after = process.cpu_times()

    from app.models import ExtractionJob

    session = session_factory()
    try:
        jobs = session.query(ExtractionJob).all()
        completed = sum(1 for job in jobs if job.status == "completed")
        failed = sum(1 for job in jobs if job.status == "failed")
        durations = [
            (job.finished_at - job.started_at).total_seconds()
            for job in jobs
            if job.finished_at and job.started_at
        ]
    finally:
        session.close()

    wall_minutes = wall_seconds / 60
    return {
        "concurrency": concurrency,
        "documents": len(jobs),
        "completed": completed,
        "failed": failed,
        "wall_seconds": round(wall_seconds, 2),
        "documents_per_hour": round(len(jobs) / wall_minutes * 60, 1) if wall_minutes else 0,
        "throughput_per_slot_per_hour": round(
            (len(jobs) / wall_minutes * 60) / concurrency, 1
        )
        if wall_minutes
        else 0,
        "document_p50_seconds": round(statistics.median(durations), 3) if durations else 0,
        "document_p95_seconds": round(percentile(durations, 0.95), 3),
        "document_max_seconds": round(max(durations), 3) if durations else 0,
        "cpu_seconds": round(
            (cpu_after.user + cpu_after.system) - (cpu_before.user + cpu_before.system), 2
        ),
        "rss_before_mb": round(rss_before / 1024**2, 1),
        "rss_after_mb": round(rss_after / 1024**2, 1),
        "rss_growth_mb": round((rss_after - rss_before) / 1024**2, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("EXP_DATABASE_URL", ""))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--concurrency", type=int, nargs="+", default=[2, 4, 8])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("--database-url atau EXP_DATABASE_URL wajib diisi")
    if "exp" not in args.database_url and not args.force:
        raise SystemExit("URL database harus memuat 'exp' atau gunakan --force")

    temp_root = REPO_ROOT / ".cache" / "exp_worker_uploads"
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True)

    os.environ["DATABASE_URL"] = args.database_url
    os.environ["UPLOAD_TEMP_DIR"] = str(temp_root)
    os.environ["ENABLE_TESSERACT_GEMINI"] = "false"
    os.environ["ENABLE_COMBINED_V4_2"] = "true"
    os.environ["GOOGLE_API_KEY"] = ""
    os.environ["APP_ENV"] = "test"
    os.environ["WORKER_HEARTBEAT_SECONDS"] = "3600"

    from app.database import Base, SessionLocal, engine
    from app.services.temporary_upload_store import upload_store

    certificates = load_certificates()
    if len(certificates) != 104:
        raise SystemExit(f"Target 104 sertifikat, ditemukan {len(certificates)}")

    Base.metadata.create_all(bind=engine)

    started_at = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for concurrency in args.concurrency:
        reset_tables(SessionLocal)
        seed_jobs(SessionLocal, upload_store, certificates)
        level = run_level(SessionLocal, concurrency)
        rows.append(level)
        records.append(
            {
                "concurrency": concurrency,
                "documents": level["documents"],
                "completed": level["completed"],
                "failed": level["failed"],
                "documents_per_hour": level["documents_per_hour"],
                "wall_seconds": level["wall_seconds"],
                "document_p95_seconds": level["document_p95_seconds"],
                "rss_growth_mb": level["rss_growth_mb"],
            }
        )
        print(
            f"concurrency={concurrency} docs/hour={level['documents_per_hour']} "
            f"p95={level['document_p95_seconds']}s failed={level['failed']}"
        )

    best = max(rows, key=lambda row: row["documents_per_hour"])
    slots_for_target = (
        (1350 / best["throughput_per_slot_per_hour"]) if best["throughput_per_slot_per_hour"] else None
    )
    metrics = {
        "experiment_id": EXPERIMENT_ID,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision(),
        "config": {
            "certificates": len(certificates),
            "concurrency_levels": args.concurrency,
            "pipeline": "offline_combined_v4_2",
            "llm_calls": 0,
        },
        "levels": rows,
        "best_level": best,
        "target_documents_per_hour": 1350,
        "slots_needed_for_target": round(slots_for_target, 2) if slots_for_target else None,
        "gates": {
            "target_reached": best["documents_per_hour"] >= 1350,
            "no_failures": all(level["failed"] == 0 for level in rows),
            "rss_growth_under_10pct": all(
                level["rss_growth_mb"] <= 0.10 * max(level["rss_before_mb"], 1)
                for level in rows
            ),
        },
    }

    status = "PASS" if all(metrics["gates"].values()) else "FAIL"
    summary = f"""# {EXPERIMENT_ID} — Throughput Worker (104 Sertifikat)

Status: **{status}**

## Konfigurasi
- Sertifikat: {len(certificates)} (certs_unified manifest)
- Pipeline: offline Combined v4.2, 0 panggilan LLM
- Concurrency diuji: {', '.join(str(value) for value in args.concurrency)}

## Hasil per tingkat
| Concurrency | Dokumen | Selesai | Gagal | Dokumen/jam | p95/dokumen | RSS growth |
|---|---|---|---|---|---|---|
""" + "\n".join(
        f"| {level['concurrency']} | {level['documents']} | {level['completed']} | "
        f"{level['failed']} | {level['documents_per_hour']} | "
        f"{level['document_p95_seconds']} s | {level['rss_growth_mb']} MB |"
        for level in rows
    ) + f"""

## Proyeksi
- Target puncak: 1.350 dokumen/jam
- Slot terbaik: {best['concurrency']} (dokumen/jam per slot {best['throughput_per_slot_per_hour']})
- Slot yang dibutuhkan untuk target: {metrics['slots_needed_for_target']}

## Gate
| Gate | Hasil |
|---|---|
| Target 1.350 dokumen/jam | {metrics['gates']['target_reached']} |
| Tidak ada job gagal | {metrics['gates']['no_failures']} |
| RSS growth <= 10% | {metrics['gates']['rss_growth_under_10pct']} |

## Interpretasi
Throughput per slot dipakai untuk menentukan `WORKER_CONCURRENCY` dan jumlah
node. Angka ini mengukur pipeline offline; jalur Gemini menambah latensi
jaringan per dokumen. Uji ini memakai antrean database nyata, tetapi seluruh
thread berada dalam satu proses sehingga CPU dibagi.
"""
    manifest = {
        "campaign_id": "CAMPAIGN-PRODUCTION-CAPACITY",
        "experiment_id": EXPERIMENT_ID,
        "parent_id": None,
        "role": "capacity-worker-throughput",
        "started_at": metrics["started_at"],
        "finished_at": metrics["finished_at"],
        "git_revision": metrics["git_revision"],
        "command": "python -m tests.benchmark_worker_throughput",
        "status": status,
        "inputs": {
            "certificates": len(certificates),
            "manifest": "certs_unified/manifest.json",
            "concurrency": args.concurrency,
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
        xlsx_sheets={"Ringkasan": rows, "Per Level": rows},
        force=args.force,
    )
    print(f"{EXPERIMENT_ID}: {status} -> {args.output_dir}")


if __name__ == "__main__":
    main()
