"""EXP-CAPACITY-001: beban HTTP 1.000 poller + 5 upload/detik.

Menjalankan server uvicorn nyata di atas database eksperimen, lalu mengukur
latensi polling hasil, error rate, upload, dan pemakaian memori server.

Jalankan manual:
    EXP_DATABASE_URL=postgresql+psycopg2://... \
    python -m tests.benchmark_concurrency --pollers 1000 --duration 60
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import psutil
from sqlalchemy import create_engine, text

from tests.experiment_io import write_bundle
from tests.experiment_server import (
    create_schema,
    seed_completed_documents,
    start_server,
    stop_server,
    wait_ready,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_ID = "EXP-CAPACITY-001"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "experiments" / EXPERIMENT_ID
API_KEYS = [f"sk-expcapacity-{index:02d}-1234567890" for index in range(1, 11)]


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


def smallest_certificate() -> bytes:
    candidates = [
        path
        for path in (REPO_ROOT / "certs_unified").iterdir()
        if path.suffix.lower() in {".pdf", ".png", ".jpeg"}
    ]
    candidates.sort(key=lambda path: path.stat().st_size)
    return candidates[0].read_bytes()


async def poller(
    client: httpx.AsyncClient,
    base_url: str,
    document_id: str,
    interval: float,
    deadline: float,
    latencies: list[tuple[float, float, int]],
) -> None:
    await asyncio.sleep(random.uniform(0, interval))
    while time.perf_counter() < deadline:
        started = time.perf_counter()
        status = 0
        try:
            response = await client.get(f"{base_url}/api/documents/{document_id}/result")
            status = response.status_code
        except httpx.HTTPError:
            status = -1
        latencies.append((time.perf_counter(), (time.perf_counter() - started) * 1000, status))
        await asyncio.sleep(interval)


async def uploader(
    client: httpx.AsyncClient,
    base_url: str,
    payload: bytes,
    rate: float,
    deadline: float,
    results: list[tuple[float, float, int]],
) -> None:
    interval = 1.0 / rate
    key_index = 0
    while time.perf_counter() < deadline:
        started = time.perf_counter()
        key = API_KEYS[key_index % len(API_KEYS)]
        key_index += 1
        status = 0
        try:
            response = await client.post(
                f"{base_url}/api/documents",
                data={"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"},
                files={"file": ("exp_capacity.pdf", payload, "application/pdf")},
                headers={"X-API-Key": key},
            )
            status = response.status_code
        except httpx.HTTPError:
            status = -1
        results.append((time.perf_counter(), (time.perf_counter() - started) * 1000, status))
        await asyncio.sleep(interval)


def bucket(latencies: list[tuple[float, float, int]], start: float) -> list[dict[str, Any]]:
    buckets: dict[int, list[tuple[float, int]]] = {}
    for timestamp, latency, status in latencies:
        key = int(timestamp - start)
        buckets.setdefault(key, []).append((latency, status))
    rows = []
    for second in sorted(buckets):
        values = buckets[second]
        rows.append(
            {
                "second": second,
                "requests": len(values),
                "p95_ms": round(percentile([value[0] for value in values], 0.95), 2),
                "errors": sum(1 for value in values if value[1] >= 500 or value[1] == -1),
            }
        )
    return rows


async def run_load(args: argparse.Namespace, document_ids: list[str], payload: bytes) -> dict[str, Any]:
    base_url = f"http://127.0.0.1:{args.port}"
    poll_latencies: list[tuple[float, float, int]] = []
    upload_results: list[tuple[float, float, int]] = []
    limits = httpx.Limits(
        max_connections=args.pollers + 20, max_keepalive_connections=args.pollers + 20
    )
    timeout = httpx.Timeout(15.0)
    start = time.perf_counter()
    deadline = start + args.duration
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        tasks = [
            asyncio.create_task(
                poller(
                    client,
                    base_url,
                    document_ids[index % len(document_ids)],
                    args.poll_interval,
                    deadline,
                    poll_latencies,
                )
            )
            for index in range(args.pollers)
        ]
        tasks.append(
            asyncio.create_task(
                uploader(client, base_url, payload, args.uploads_per_second, deadline, upload_results)
            )
        )
        await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    poll_values = [value[1] for value in poll_latencies]
    poll_status = {status: sum(1 for value in poll_latencies if value[2] == status) for status in
                   {value[2] for value in poll_latencies}}
    upload_status = {status: sum(1 for value in upload_results if value[2] == status) for status in
                     {value[2] for value in upload_results}}
    return {
        "elapsed_seconds": round(elapsed, 2),
        "poll": {
            "requests": len(poll_latencies),
            "rps": round(len(poll_latencies) / elapsed, 1),
            "p50_ms": round(percentile(poll_values, 0.50), 2),
            "p95_ms": round(percentile(poll_values, 0.95), 2),
            "p99_ms": round(percentile(poll_values, 0.99), 2),
            "max_ms": round(max(poll_values), 2) if poll_values else 0,
            "status": poll_status,
        },
        "upload": {
            "requests": len(upload_results),
            "rps": round(len(upload_results) / elapsed, 2),
            "p95_ms": round(percentile([value[1] for value in upload_results], 0.95), 2),
            "status": upload_status,
        },
        "poll_buckets": bucket(poll_latencies, start),
        "upload_buckets": bucket(upload_results, start),
    }


def sample_server(process: psutil.Process, samples: list[float], stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            samples.append(process.memory_info().rss)
        except psutil.Error:
            break
        time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("EXP_DATABASE_URL", ""))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--pollers", type=int, default=1000)
    parser.add_argument("--poll-interval", type=float, default=3.0)
    parser.add_argument("--uploads-per-second", type=float, default=5.0)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("--database-url atau EXP_DATABASE_URL wajib diisi")
    if "exp" not in args.database_url and not args.force:
        raise SystemExit("URL database harus memuat 'exp' atau gunakan --force")

    os.environ["DATABASE_URL"] = args.database_url
    os.environ["APP_ENV"] = "test"
    os.environ["ADMIN_PASSWORD"] = "exp-capacity-admin"
    os.environ["API_KEYS"] = ",".join(API_KEYS)
    os.environ["REQUIRE_API_KEY"] = "false"
    os.environ["RATE_LIMIT_PER_MINUTE"] = "600"
    os.environ["QUEUE_BACKPRESSURE_SECONDS"] = "1800"
    os.environ["PROCESSING_MODE"] = "db_worker"
    os.environ["ENABLE_TESSERACT_GEMINI"] = "false"
    os.environ["GOOGLE_API_KEY"] = ""
    os.environ["PYTHONPATH"] = f"{REPO_ROOT}:{REPO_ROOT / 'backend'}"

    create_schema(args.database_url)
    document_ids = seed_completed_documents(args.database_url, args.pollers)
    payload = smallest_certificate()

    started_at = datetime.now(timezone.utc)
    process = start_server(args.port, dict(os.environ))
    wait_ready(args.port)
    server_process = psutil.Process(process.pid)
    rss_samples: list[float] = []
    sampler_stop = threading.Event()

    async def with_sampler() -> dict[str, Any]:
        sampler = threading.Thread(
            target=sample_server, args=(server_process, rss_samples, sampler_stop), daemon=True
        )
        sampler.start()
        try:
            return await run_load(args, document_ids, payload)
        finally:
            sampler_stop.set()
            sampler.join(timeout=2)

    try:
        results = asyncio.run(with_sampler())
    finally:
        stop_server(process)

    engine = create_engine(args.database_url)
    with engine.connect() as connection:
        db_connections = connection.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
        ).scalar_one()
    engine.dispose()

    poll_status = results["poll"]["status"]
    error_count = sum(count for status, count in poll_status.items() if status >= 500 or status == -1)
    error_rate = error_count / max(results["poll"]["requests"], 1)
    upload_success = results["upload"]["status"].get(200, 0) / max(results["upload"]["requests"], 1)
    rss_max_mb = round(max(rss_samples) / 1024**2, 1) if rss_samples else 0

    gates = {
        "poll_p95_under_150ms": results["poll"]["p95_ms"] < 150,
        "poll_error_rate_under_0_1pct": error_rate < 0.001,
        "upload_success_over_99pct": upload_success > 0.99,
        "server_rss_under_1500mb": rss_max_mb < 1500,
    }
    status = "PASS" if all(gates.values()) else "FAIL"

    metrics = {
        "experiment_id": EXPERIMENT_ID,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision(),
        "config": {
            "pollers": args.pollers,
            "poll_interval_seconds": args.poll_interval,
            "uploads_per_second": args.uploads_per_second,
            "duration_seconds": args.duration,
            "server_workers": 1,
            "server_pid": process.pid,
        },
        "results": results,
        "server": {"rss_max_mb": rss_max_mb, "db_connections_after": db_connections},
        "gates": gates,
        "status": status,
    }

    poll_buckets = results["poll_buckets"]
    records = [
        {"lane": "poll", "second": row["second"], "requests": row["requests"],
         "p95_ms": row["p95_ms"], "errors": row["errors"]}
        for row in poll_buckets
    ] + [
        {"lane": "upload", "second": row["second"], "requests": row["requests"],
         "p95_ms": row["p95_ms"], "errors": row["errors"]}
        for row in results["upload_buckets"]
    ]
    rows = [
        {"metric": "poll_rps", "value": results["poll"]["rps"]},
        {"metric": "poll_p50_ms", "value": results["poll"]["p50_ms"]},
        {"metric": "poll_p95_ms", "value": results["poll"]["p95_ms"]},
        {"metric": "poll_p99_ms", "value": results["poll"]["p99_ms"]},
        {"metric": "poll_requests", "value": results["poll"]["requests"]},
        {"metric": "poll_error_rate", "value": round(error_rate, 6)},
        {"metric": "upload_rps", "value": results["upload"]["rps"]},
        {"metric": "upload_p95_ms", "value": results["upload"]["p95_ms"]},
        {"metric": "upload_success_rate", "value": round(upload_success, 6)},
        {"metric": "server_rss_max_mb", "value": rss_max_mb},
        {"metric": "db_connections_after", "value": db_connections},
    ]

    summary = f"""# {EXPERIMENT_ID} — Beban HTTP 1.000 Poller

Status: **{status}**

## Konfigurasi
- Poller: {args.pollers:,} klien, interval {args.poll_interval} s, durasi {args.duration} s
- Upload: {args.uploads_per_second}/detik (10 API key berputar)
- Server: 1 proses uvicorn, tanpa worker aktif (job hanya masuk antrean)
- Total request polling: {results['poll']['requests']:,} ({results['poll']['rps']} rps)

## Hasil polling
| Metrik | Nilai |
|---|---|
| p50 | {results['poll']['p50_ms']} ms |
| p95 | {results['poll']['p95_ms']} ms |
| p99 | {results['poll']['p99_ms']} ms |
| max | {results['poll']['max_ms']} ms |
| error rate | {error_rate*100:.4f}% |
| status | {poll_status} |

## Hasil upload
| Metrik | Nilai |
|---|---|
| rps | {results['upload']['rps']} |
| p95 | {results['upload']['p95_ms']} ms |
| status | {results['upload']['status']} |

## Server
- RSS maksimum: {rss_max_mb} MB
- Koneksi database setelah uji: {db_connections}

## Gate
| Gate | Hasil |
|---|---|
| poll p95 < 150 ms | {gates['poll_p95_under_150ms']} |
| error rate < 0,1% | {gates['poll_error_rate_under_0_1pct']} |
| upload sukses > 99% | {gates['upload_success_over_99pct']} |
| RSS < 1500 MB | {gates['server_rss_under_1500mb']} |

## Keterbatasan
Klien dan server berada di mesin 8 GB yang sama, sehingga angka ini batas
bawah untuk server kampus. Upload hanya menguji penerimaan dan antrean; OCR
tidak berjalan pada uji ini (worker dimatikan).
"""
    manifest = {
        "campaign_id": "CAMPAIGN-PRODUCTION-CAPACITY",
        "experiment_id": EXPERIMENT_ID,
        "parent_id": None,
        "role": "capacity-http",
        "started_at": metrics["started_at"],
        "finished_at": metrics["finished_at"],
        "git_revision": metrics["git_revision"],
        "command": "python -m tests.benchmark_concurrency",
        "status": status,
        "inputs": {
            "pollers": args.pollers,
            "poll_interval_seconds": args.poll_interval,
            "uploads_per_second": args.uploads_per_second,
            "duration_seconds": args.duration,
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
        xlsx_sheets={"Ringkasan": rows, "Per Detik": records},
        force=args.force,
    )
    print(f"{EXPERIMENT_ID}: {status} -> {args.output_dir}")


if __name__ == "__main__":
    main()
