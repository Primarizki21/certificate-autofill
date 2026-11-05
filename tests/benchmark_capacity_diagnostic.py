"""EXP-CAPACITY-004: diagnostik kapasitas HTTP (atribusi server vs rig uji).

Mengukur ulang 1.000 poller pada beberapa interval, sambil membandingkan
latensi yang dilihat klien dengan histogram latensi di dalam aplikasi
(`cert_http_request_duration_seconds`), plus CPU dan RSS proses server.

Jalankan manual:
    EXP_DATABASE_URL=postgresql+psycopg2://... \
    python -m tests.benchmark_capacity_diagnostic
"""

from __future__ import annotations

import argparse
import asyncio
import multiprocessing
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import psutil

from tests.benchmark_concurrency import bucket, poller
from tests.experiment_io import write_bundle
from tests.experiment_server import (
    create_schema,
    seed_completed_documents,
    start_server,
    stop_server,
    wait_ready,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_ID = "EXP-CAPACITY-004"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "experiments" / EXPERIMENT_ID
RESULT_ENDPOINT = "/api/documents/{document_id}/result"
BUCKET_RE = re.compile(r'le="([^"]+)"')
VALUE_RE = re.compile(r"\}\s+([0-9.eE+-]+)$")


def git_revision() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def scrape_histogram(port: int) -> dict[str, Any]:
    """Scrape /metrics; timeout panjang karena endpoint ikut mengantre saat server jenuh."""
    last_error: Exception | None = None
    for _ in range(3):
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/metrics", timeout=180.0)
            response.raise_for_status()
            break
        except httpx.HTTPError as exc:
            last_error = exc
            time.sleep(2)
    else:
        raise SystemExit(f"/metrics tidak dapat dibaca: {last_error}")
    snapshot: dict[str, Any] = {"count": 0.0, "sum": 0.0, "buckets": {}}
    for line in response.text.splitlines():
        if not line.startswith("cert_http_request_duration_seconds"):
            continue
        if f'endpoint="{RESULT_ENDPOINT}"' not in line:
            continue
        if line.startswith("cert_http_request_duration_seconds_count"):
            snapshot["count"] = float(line.split()[-1])
        elif line.startswith("cert_http_request_duration_seconds_sum"):
            snapshot["sum"] = float(line.split()[-1])
        elif "_bucket" in line:
            bucket_match = BUCKET_RE.search(line)
            value_match = VALUE_RE.search(line)
            if bucket_match and value_match:
                snapshot["buckets"][bucket_match.group(1)] = float(value_match.group(1))
    return snapshot


def histogram_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    count = after["count"] - before["count"]
    total = after["sum"] - before["sum"]
    buckets = {
        limit: after["buckets"].get(limit, 0.0) - before["buckets"].get(limit, 0.0)
        for limit in after["buckets"]
    }
    return {
        "count": count,
        "mean_ms": round(total / count * 1000, 2) if count else 0.0,
        "buckets": buckets,
    }


def bucket_percentile(buckets: dict[str, float], quantile: float) -> float | None:
    total = buckets.get("+Inf", 0.0)
    if total <= 0:
        return 0.0
    target = total * quantile
    for limit, cumulative in sorted(
        ((key, value) for key, value in buckets.items() if key != "+Inf"),
        key=lambda item: float(item[0]),
    ):
        if cumulative >= target:
            return float(limit) * 1000
    return None


async def poll_interval(
    port: int, document_ids: list[str], pollers: int, interval: float, duration: float
) -> tuple[list[tuple[float, float, int]], float]:
    base_url = f"http://127.0.0.1:{port}"
    latencies: list[tuple[float, float, int]] = []
    limits = httpx.Limits(max_connections=pollers + 20, max_keepalive_connections=pollers + 20)
    start = time.perf_counter()
    deadline = start + duration
    async with httpx.AsyncClient(limits=limits, timeout=httpx.Timeout(60.0)) as client:
        tasks = [
            asyncio.create_task(
                poller(
                    client,
                    base_url,
                    document_ids[index % len(document_ids)],
                    interval,
                    deadline,
                    latencies,
                )
            )
            for index in range(pollers)
        ]
        await asyncio.gather(*tasks)
    return latencies, time.perf_counter() - start


def _client_worker(payload: tuple[int, list[str], int, float, float]):
    port, document_ids, pollers, interval, duration = payload
    return asyncio.run(poll_interval(port, document_ids, pollers, interval, duration))


def _tree_cpu(process: psutil.Process) -> float:
    total = 0.0
    for child in [process, *process.children(recursive=True)]:
        try:
            times = child.cpu_times()
            total += times.user + times.system
        except psutil.Error:
            continue
    return total


def _tree_rss(process: psutil.Process) -> float:
    total = 0.0
    for child in [process, *process.children(recursive=True)]:
        try:
            total += child.memory_info().rss
        except psutil.Error:
            continue
    return total


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(fraction * len(ordered)))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("EXP_DATABASE_URL", ""))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--port", type=int, default=18090)
    parser.add_argument("--pollers", type=int, default=1000)
    parser.add_argument("--intervals", type=float, nargs="+", default=[3.0, 5.0, 10.0])
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--client-processes", type=int, default=1)
    parser.add_argument("--metrics-port", type=int, default=0)
    parser.add_argument("--server-workers", type=int, default=1)
    parser.add_argument("--experiment-id", default=EXPERIMENT_ID)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("--database-url atau EXP_DATABASE_URL wajib diisi")
    if "exp" not in args.database_url and not args.force:
        raise SystemExit("URL database harus memuat 'exp' atau gunakan --force")

    os.environ["DATABASE_URL"] = args.database_url
    os.environ["APP_ENV"] = "test"
    os.environ["ADMIN_PASSWORD"] = "exp-diagnostic-admin"
    os.environ["API_KEYS"] = ""
    os.environ["REQUIRE_API_KEY"] = "false"
    os.environ["RATE_LIMIT_PER_MINUTE"] = "600"
    os.environ["QUEUE_BACKPRESSURE_SECONDS"] = "0"
    os.environ["PROCESSING_MODE"] = "db_worker"
    os.environ["ENABLE_TESSERACT_GEMINI"] = "false"
    os.environ["GOOGLE_API_KEY"] = ""
    os.environ["PYTHONPATH"] = f"{REPO_ROOT}:{REPO_ROOT / 'backend'}"
    os.environ["METRICS_PORT"] = "0" if args.server_workers > 1 else str(args.metrics_port)

    create_schema(args.database_url)
    document_ids = seed_completed_documents(args.database_url, args.pollers)

    metrics_port = args.metrics_port or args.port
    log_path = REPO_ROOT / ".cache" / f"exp_capacity_diagnostic_{args.port}.log"
    process = start_server(
        args.port, dict(os.environ), str(log_path), workers=args.server_workers
    )
    wait_ready(args.port)
    server_process = psutil.Process(process.pid)

    started_at = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    conclusions: list[str] = []

    context = multiprocessing.get_context("spawn")
    client_pool = (
        context.Pool(processes=args.client_processes) if args.client_processes > 1 else None
    )
    try:
        for interval in args.intervals:
            before = scrape_histogram(metrics_port) if args.server_workers == 1 else None
            cpu_before = _tree_cpu(server_process)
            rss_before = _tree_rss(server_process)
            interval_start = time.perf_counter()
            if client_pool:
                per_process = args.pollers // args.client_processes
                payloads = [
                    (
                        args.port,
                        document_ids[index * per_process : (index + 1) * per_process],
                        per_process,
                        interval,
                        args.duration,
                    )
                    for index in range(args.client_processes)
                ]
                results = client_pool.map(_client_worker, payloads)
                latencies = [item for values, _ in results for item in values]
                elapsed = max(value for _, value in results)
            else:
                latencies, elapsed = asyncio.run(
                    poll_interval(args.port, document_ids, args.pollers, interval, args.duration)
                )
            time.sleep(3)
            after = scrape_histogram(metrics_port) if before is not None else None
            cpu_after = _tree_cpu(server_process)
            rss_after = _tree_rss(server_process)

            delta = histogram_delta(before, after) if before and after else None
            total = len(latencies)
            values = [value[1] for value in latencies]
            rps = round(total / elapsed, 2)
            rps_window = round(total / args.duration, 2)
            response_estimate = (
                round(args.pollers / rps_window - interval, 2) if rps_window else None
            )
            cpu_seconds = round(cpu_after - cpu_before, 2)
            cpu_percent_of_one_core = round(cpu_seconds / elapsed * 100, 1)
            server_p95 = bucket_percentile(delta["buckets"], 0.95) if delta else None
            inf_count = delta["buckets"].get("+Inf", 0.0) if delta else 0.0
            under_10s = delta["buckets"].get("10.0", 0.0) if delta else 0.0
            over_10s = (
                round((inf_count - under_10s) / delta["count"], 4)
                if delta and delta["count"]
                else None
            )

            row = {
                "interval_seconds": interval,
                "requests": total,
                "rps": rps,
                "rps_window": rps_window,
                "client_p50_ms": round(percentile(values, 0.50), 1),
                "client_p95_ms": round(percentile(values, 0.95), 1),
                "client_p99_ms": round(percentile(values, 0.99), 1),
                "server_sample_count": int(delta["count"]) if delta else 0,
                "server_mean_ms": delta["mean_ms"] if delta else None,
                "server_p95_ms": (
                    (server_p95 if server_p95 is not None else ">10000") if delta else "n/a"
                ),
                "server_share_over_10s": over_10s,
                "server_cpu_pct_one_core": cpu_percent_of_one_core,
                "server_rss_after_mb": round(rss_after / 1024**2, 1),
                "server_rss_delta_mb": round((rss_after - rss_before) / 1024**2, 1),
                "closed_loop_response_est_s": response_estimate,
                "statuses": {
                    status: sum(1 for value in latencies if value[2] == status)
                    for status in {value[2] for value in latencies}
                },
            }
            rows.append(row)
            records.extend(
                {"interval_seconds": interval, **bucket_row}
                for bucket_row in bucket(latencies, interval_start)
            )

            if response_estimate is not None and delta and delta["mean_ms"] > 0:
                if delta["mean_ms"] < response_estimate * 1000 * 0.5:
                    conclusions.append(
                        f"interval {interval}s: latensi dalam aplikasi {delta['mean_ms']} ms "
                        f"jauh di bawah respons klien ~{response_estimate} s, "
                        "sebagian besar waktu hilang sebelum/after handler."
                    )
                else:
                    conclusions.append(
                        f"interval {interval}s: latensi dalam aplikasi {delta['mean_ms']} ms "
                        "sebanding dengan respons klien, bottleneck di handler/threadpool."
                    )
            print(row)
    finally:
        if client_pool:
            client_pool.close()
            client_pool.join()
        stop_server(process)
        stream = getattr(process, "_log_stream", None)
        if stream is not None and stream is not subprocess.DEVNULL:  # type: ignore[attr-defined]
            stream.close()

    metrics = {
        "experiment_id": args.experiment_id,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision(),
        "config": {
            "pollers": args.pollers,
            "client_processes": args.client_processes,
            "server_workers": args.server_workers,
            "metrics_port": args.metrics_port,
            "intervals": args.intervals,
            "duration_seconds": args.duration,
            "threadpool_default_limit": 40,
            "db_pool_size": int(os.getenv("DB_POOL_SIZE", "20")),
            "db_max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        },
        "rows": rows,
        "conclusions": conclusions,
        "note": "Klien dan server berada di host yang sama; angka rps adalah batas bawah.",
    }

    summary = f"""# {args.experiment_id} — Diagnostik Kapasitas HTTP

## Tujuan
Memisahkan latensi di dalam aplikasi dari latensi yang dilihat klien pada
1.000 poller, dan melihat efek interval polling 3/5/10 detik.

## Konfigurasi
- Poller: {args.pollers:,} dalam {args.client_processes} proses klien, durasi {args.duration} s per interval
- Interval diuji: {', '.join(str(value) for value in args.intervals)} detik
- Server: {args.server_workers} worker uvicorn, pool DB {os.getenv('DB_POOL_SIZE', '20')}
- Upload dinonaktifkan agar pengukuran hanya polling

## Hasil
| Interval | RPS (elapsed) | RPS (window) | Klien p50 | Klien p95 | Server mean | Server p95 | >10 s | CPU (1 core) | RSS |
|---|---|---|---|---|---|---|---|---|
""" + "\n".join(
        f"| {row['interval_seconds']} s | {row['rps']} | {row['rps_window']} | "
        f"{row['client_p50_ms']} ms | "
        f"{row['client_p95_ms']} ms | {row['server_mean_ms']} ms | {row['server_p95_ms']} | "
        f"{(row['server_share_over_10s']*100 if row['server_share_over_10s'] is not None else 0):.1f}% | "
        f"{row['server_cpu_pct_one_core']}% | "
        f"{row['server_rss_after_mb']} MB |"
        for row in rows
    ) + """

## Interpretasi
""" + "\n".join(f"- {line}" for line in conclusions) + """

## Keterbatasan
- Klien, server, dan PostgreSQL berada di satu host 8 vCPU.
- Histogram aplikasi memakai bucket maksimum 10 detik; nilai p95 di atas 10 detik
  dilaporkan sebagai `>10000` dan proporsi ekor dicatat terpisah.
"""
    manifest = {
        "campaign_id": "CAMPAIGN-PRODUCTION-CAPACITY",
        "experiment_id": args.experiment_id,
        "parent_id": "EXP-CAPACITY-003",
        "role": "capacity-diagnostic",
        "started_at": metrics["started_at"],
        "finished_at": metrics["finished_at"],
        "git_revision": metrics["git_revision"],
        "command": "python -m tests.benchmark_capacity_diagnostic",
        "status": "PASS",
        "inputs": {
            "pollers": args.pollers,
            "client_processes": args.client_processes,
            "server_workers": args.server_workers,
            "metrics_port": args.metrics_port,
            "intervals": args.intervals,
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
    print(f"{args.experiment_id}: PASS -> {args.output_dir}")


if __name__ == "__main__":
    main()
