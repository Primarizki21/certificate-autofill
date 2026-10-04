#!/usr/bin/env python3
"""Script Stress Testing API & MLOps Monitoring Pipeline.

Menguji konkurensi upload dokumen ke /api/documents, mengukur latensi
HTTP Ingestion dan End-to-End Processing (P50, P90, P99), serta
menghasilkan artefak evaluasi di docs/stress_test/.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def compute_percentiles(values: list[float]) -> dict[str, float]:
    """Hitung nilai persentil p50, p90, p95, dan p99 menggunakan metode nearest-rank."""
    if not values:
        return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0}
    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _get_p(p: float) -> float:
        idx = max(0, min(math.ceil((p / 100.0) * n) - 1, n - 1))
        return round(sorted_vals[idx], 2)

    return {
        "min": round(sorted_vals[0], 2),
        "p50": _get_p(50),
        "p90": _get_p(90),
        "p95": _get_p(95),
        "p99": _get_p(99),
        "max": round(sorted_vals[-1], 2),
        "avg": round(sum(sorted_vals) / n, 2),
    }


def load_certificates(certs_dir: Path) -> list[tuple[str, bytes]]:
    """Muat seluruh berkas sertifikat dari direktori target ke dalam RAM."""
    if not certs_dir.exists() or not certs_dir.is_dir():
        raise FileNotFoundError(f"Direktori sertifikat tidak ditemukan: {certs_dir}")

    certs: list[tuple[str, bytes]] = []
    for entry in sorted(certs_dir.iterdir()):
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
            certs.append((entry.name, entry.read_bytes()))

    if not certs:
        raise ValueError(f"Tidak ada berkas sertifikat yang didukung di {certs_dir}")
    return certs


async def worker_task(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    base_url: str,
    cert_item: tuple[str, bytes],
    request_id: int,
    poll_interval: float,
    poll_timeout: float,
    bypass_rate_limit: bool,
) -> dict[str, Any]:
    """Kirim satu request upload dokumen dan pantau status hingga tuntas."""
    filename, file_bytes = cert_item
    record: dict[str, Any] = {
        "request_id": request_id,
        "filename": filename,
        "file_size_bytes": len(file_bytes),
        "http_status": 0,
        "http_latency_ms": 0.0,
        "document_id": None,
        "job_id": None,
        "e2e_latency_ms": 0.0,
        "job_status": "unsubmitted",
        "engine": None,
        "needs_review": False,
        "error": None,
    }

    headers = {}
    if bypass_rate_limit:
        # Simulasi IP virtual agar tidak terhadang sliding window rate limiter internal
        headers["X-Forwarded-For"] = f"10.0.{(request_id // 250) + 1}.{(request_id % 250) + 1}"

    async with semaphore:
        t_upload_start = time.perf_counter()
        try:
            files = {"file": (filename, file_bytes, "application/pdf")}
            data = {"tahun_akademik": "2023/2024", "bukti_fisik": "Sertifikat"}
            res = await client.post(
                f"{base_url}/api/documents",
                headers=headers,
                files=files,
                data=data,
            )
            t_upload_end = time.perf_counter()
            record["http_status"] = res.status_code
            record["http_latency_ms"] = round((t_upload_end - t_upload_start) * 1000, 2)

            if res.status_code != 200:
                record["job_status"] = "upload_failed"
                record["error"] = f"HTTP {res.status_code}: {res.text[:200]}"
                return record

            resp_json = res.json()
            document_id = resp_json.get("document_id")
            job_id = resp_json.get("job_id")
            record["document_id"] = document_id
            record["job_id"] = job_id
            record["job_status"] = resp_json.get("status", "queued")

        except Exception as exc:
            t_upload_end = time.perf_counter()
            record["http_latency_ms"] = round((t_upload_end - t_upload_start) * 1000, 2)
            record["job_status"] = "network_error"
            record["error"] = str(exc)
            return record

    # Polling fase ekstraksi hingga status tuntas atau timeout
    if not document_id:
        return record

    t_poll_start = time.perf_counter()
    while True:
        await asyncio.sleep(poll_interval)
        try:
            res_poll = await client.get(
                f"{base_url}/api/documents/{document_id}/result",
                headers=headers,
            )
            if res_poll.status_code == 200:
                poll_json = res_poll.json()
                status = poll_json.get("status", "queued")
                record["job_status"] = status
                if status in ("completed", "needs_review"):
                    record["e2e_latency_ms"] = round((time.perf_counter() - t_upload_start) * 1000, 2)
                    fields_data = poll_json.get("fields", {})
                    sources = [f.get("source", "") for f in fields_data.values() if isinstance(f, dict)]
                    if any("gemini" in s.lower() for s in sources):
                        record["engine"] = "gemini"
                    elif any("combined" in s.lower() for s in sources):
                        record["engine"] = "combined_v4_2"
                    else:
                        record["engine"] = "hybrid_rules"
                    record["needs_review"] = bool(poll_json.get("needs_review", False))
                    break
                if status == "failed":
                    record["e2e_latency_ms"] = round((time.perf_counter() - t_upload_start) * 1000, 2)
                    record["error"] = "Job extraction failed in worker"
                    break
        except Exception as exc:
            record["error"] = f"Polling error: {exc}"

        if time.perf_counter() - t_poll_start >= poll_timeout:
            record["e2e_latency_ms"] = round((time.perf_counter() - t_upload_start) * 1000, 2)
            record["job_status"] = "timeout"
            record["error"] = f"Job incomplete after {poll_timeout}s"
            break

    return record


async def run_stress_test(
    base_url: str,
    certs_dir: Path,
    total_requests: int,
    concurrency: int,
    poll_interval: float,
    poll_timeout: float,
    output_dir: Path,
    bypass_rate_limit: bool,
) -> dict[str, Any]:
    """Jalankan suite stress test terkonkurensi penuh dan rekam hasilnya."""
    print(f"\n{'='*70}")
    print("STRESS TEST & PIPELINE LATENCY PROFILER")
    print(f"{'='*70}")
    print(f"Target API Base URL : {base_url}")
    print(f"Direktori Sertifikat: {certs_dir}")
    print(f"Total Dokumen       : {total_requests}")
    print(f"Konkurensi Upload   : {concurrency}")
    print(f"Interval Polling    : {poll_interval}s")
    print(f"Batas Waktu Polling : {poll_timeout}s")
    print(f"Direktori Output    : {output_dir}")
    print(f"{'='*70}\n")

    print("[1/4] Memuat berkas sertifikat ke memori RAM...")
    certs = load_certificates(certs_dir)
    print(f"✓ Berhasil memuat {len(certs)} sertifikat sampel unik ke RAM.")

    semaphore = asyncio.Semaphore(concurrency)
    output_dir.mkdir(parents=True, exist_ok=True)

    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency)
    timeout = httpx.Timeout(connect=15.0, read=45.0, write=45.0, pool=45.0)

    start_iso = datetime.now(timezone.utc).isoformat()
    t_global_start = time.perf_counter()

    print(f"[2/4] Menjalankan pengiriman {total_requests} dokumen dengan {concurrency} koneksi konkuren...")

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        tasks = []
        for seq in range(1, total_requests + 1):
            cert_item = certs[(seq - 1) % len(certs)]
            task = worker_task(
                client=client,
                semaphore=semaphore,
                base_url=base_url,
                cert_item=cert_item,
                request_id=seq,
                poll_interval=poll_interval,
                poll_timeout=poll_timeout,
                bypass_rate_limit=bypass_rate_limit,
            )
            tasks.append(task)

        # Jalankan semua task asinkron
        results: list[dict[str, Any]] = await asyncio.gather(*tasks)

    t_global_end = time.perf_counter()
    total_elapsed_s = round(t_global_end - t_global_start, 2)
    end_iso = datetime.now(timezone.utc).isoformat()

    print(f"\n[3/4] Seluruh {total_requests} request tuntas dalam {total_elapsed_s} detik.")
    print("[4/4] Mengompilasi metrik latensi dan menyusun laporan...")

    # Kalkulasi metrik
    http_latencies = [r["http_latency_ms"] for r in results if r["http_status"] == 200]
    e2e_latencies = [r["e2e_latency_ms"] for r in results if r["job_status"] in ("completed", "needs_review")]

    http_percentiles = compute_percentiles(http_latencies)
    e2e_percentiles = compute_percentiles(e2e_latencies)

    http_status_counts: dict[int, int] = {}
    job_status_counts: dict[str, int] = {}
    engine_counts: dict[str, int] = {}
    needs_review_count = 0

    for r in results:
        status_code = r["http_status"]
        http_status_counts[status_code] = http_status_counts.get(status_code, 0) + 1

        j_status = r["job_status"]
        job_status_counts[j_status] = job_status_counts.get(j_status, 0) + 1

        eng = r["engine"] or "unknown"
        engine_counts[eng] = engine_counts.get(eng, 0) + 1

        if r.get("needs_review"):
            needs_review_count += 1

    http_success_count = http_status_counts.get(200, 0)
    job_completed_count = job_status_counts.get("completed", 0) + job_status_counts.get("needs_review", 0)
    rps = round(total_requests / total_elapsed_s, 2) if total_elapsed_s > 0 else 0.0

    summary = {
        "metadata": {
            "start_time": start_iso,
            "end_time": end_iso,
            "total_elapsed_seconds": total_elapsed_s,
            "target_url": base_url,
            "total_requests": total_requests,
            "concurrency": concurrency,
            "throughput_rps": rps,
        },
        "http_ingestion": {
            "total_submitted": total_requests,
            "status_200": http_success_count,
            "status_code_breakdown": http_status_counts,
            "success_rate_pct": round((http_success_count / total_requests) * 100, 2) if total_requests else 0.0,
            "latency_ms": http_percentiles,
        },
        "end_to_end_processing": {
            "total_completed": job_completed_count,
            "status_breakdown": job_status_counts,
            "completion_rate_pct": round((job_completed_count / total_requests) * 100, 2) if total_requests else 0.0,
            "latency_ms": e2e_percentiles,
            "engine_breakdown": engine_counts,
            "needs_review_count": needs_review_count,
        },
    }

    # Tulis CSV
    csv_path = output_dir / "latencies.csv"
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "request_id",
                "filename",
                "file_size_bytes",
                "http_status",
                "http_latency_ms",
                "document_id",
                "job_id",
                "job_status",
                "e2e_latency_ms",
                "engine",
                "needs_review",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    # Tulis JSON
    json_path = output_dir / "summary.json"
    with open(json_path, mode="w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Tulis Markdown Report
    md_path = output_dir / "report.md"
    report_content = f"""# Laporan Evaluasi Kinerja & Stress Test API

- **Waktu Pengujian**: {start_iso} s/d {end_iso}
- **Total Permintaan**: {total_requests} dokumen
- **Konkurensi**: {concurrency} koneksi simultan
- **Durasi Pengujian**: {total_elapsed_s} detik
- **Throughput**: {rps} request/detik

---

## 1. Latensi HTTP Ingestion (Endpoint Upload)

Mengukur waktu respon API `/api/documents` dari pengiriman form multipart hingga tiket antrean diterbitkan.

| Metrik | Nilai (ms) | Target SLA | Status |
|---|:---:|:---:|:---:|
| **P50 (Median)** | {http_percentiles['p50']} ms | < 100 ms | {'PASS' if http_percentiles['p50'] < 100 else 'WARN'} |
| **P90** | {http_percentiles['p90']} ms | < 250 ms | {'PASS' if http_percentiles['p90'] < 250 else 'WARN'} |
| **P95** | {http_percentiles['p95']} ms | < 500 ms | {'PASS' if http_percentiles['p95'] < 500 else 'WARN'} |
| **P99** | {http_percentiles['p99']} ms | < 1000 ms | {'PASS' if http_percentiles['p99'] < 1000 else 'WARN'} |
| **Min / Max** | {http_percentiles['min']} ms / {http_percentiles['max']} ms | - | - |
| **Rata-rata** | {http_percentiles['avg']} ms | - | - |

- **Tingkat Keberhasilan Upload**: {summary['http_ingestion']['success_rate_pct']}% ({http_success_count}/{total_requests})

---

## 2. Latensi End-to-End Processing (Antrean Worker + Ekstraksi AI)

Mengukur waktu tunggu antrean ditambah komputasi pipeline (PyMuPDF, OCR Tesseract, dan Gemini).

| Metrik | Nilai (detik) | Nilai (ms) |
|---|:---:|:---:|
| **P50 (Median)** | {round(e2e_percentiles['p50']/1000, 2)} s | {e2e_percentiles['p50']} ms |
| **P90** | {round(e2e_percentiles['p90']/1000, 2)} s | {e2e_percentiles['p90']} ms |
| **P95** | {round(e2e_percentiles['p95']/1000, 2)} s | {e2e_percentiles['p95']} ms |
| **P99** | {round(e2e_percentiles['p99']/1000, 2)} s | {e2e_percentiles['p99']} ms |
| **Min / Max** | {round(e2e_percentiles['min']/1000, 2)} s / {round(e2e_percentiles['max']/1000, 2)} s | {e2e_percentiles['min']} ms / {e2e_percentiles['max']} ms |

- **Tingkat Penyelesaian Job**: {summary['end_to_end_processing']['completion_rate_pct']}% ({job_completed_count}/{total_requests})
- **Distribusi Mesin Ekstraksi**: `{json.dumps(engine_counts)}`
- **Dokumen Memerlukan Review**: {needs_review_count} dokumen

---

## 3. Ringkasan Status HTTP & Worker
- **Rincian Status HTTP**: `{json.dumps(http_status_counts)}`
- **Rincian Status Job**: `{json.dumps(job_status_counts)}`
"""
    with open(md_path, mode="w", encoding="utf-8") as f:
        f.write(report_content)

    # Cetak ringkasan terminal
    print(f"\n{'='*70}")
    print("HASIL EVALUASI STRESS TEST")
    print(f"{'='*70}")
    print(f"Durasi Total       : {total_elapsed_s} detik")
    print(f"Throughput         : {rps} RPS")
    print(f"Upload Success Rate: {summary['http_ingestion']['success_rate_pct']}% ({http_success_count}/{total_requests})")
    print(f"Job Completion Rate: {summary['end_to_end_processing']['completion_rate_pct']}% ({job_completed_count}/{total_requests})")
    print("-" * 70)
    print("LATENSI HTTP INGESTION (Upload API):")
    print(f"  P50 : {http_percentiles['p50']} ms")
    print(f"  P90 : {http_percentiles['p90']} ms")
    print(f"  P95 : {http_percentiles['p95']} ms")
    print(f"  P99 : {http_percentiles['p99']} ms")
    print("LATENSI END-TO-END PROCESSING (Worker Queue + Ekstraksi):")
    print(f"  P50 : {round(e2e_percentiles['p50']/1000, 2)} s ({e2e_percentiles['p50']} ms)")
    print(f"  P90 : {round(e2e_percentiles['p90']/1000, 2)} s ({e2e_percentiles['p90']} ms)")
    print(f"  P95 : {round(e2e_percentiles['p95']/1000, 2)} s ({e2e_percentiles['p95']} ms)")
    print(f"  P99 : {round(e2e_percentiles['p99']/1000, 2)} s ({e2e_percentiles['p99']} ms)")
    print("-" * 70)
    print(f"Artefak tersimpan di: {output_dir}/")
    print(f"  - {json_path.name}")
    print(f"  - {csv_path.name}")
    print(f"  - {md_path.name}")
    print(f"{'='*70}\n")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stress Test API Certificate Autofill")
    parser.add_argument("--base-url", default="http://localhost:8000", help="URL dasar API")
    parser.add_argument("--certs-dir", default="certs_unified", help="Direktori berkas sertifikat")
    parser.add_argument("--total-requests", type=int, default=20, help="Jumlah total dokumen yang diuji")
    parser.add_argument("--concurrency", type=int, default=5, help="Jumlah request upload simultan")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Interval polling status (detik)")
    parser.add_argument("--poll-timeout", type=float, default=180.0, help="Batas waktu polling per job (detik)")
    parser.add_argument("--output-dir", default="docs/stress_test", help="Direktori penyimpanan laporan")
    parser.add_argument("--no-bypass", action="store_true", help="Jangan bypass internal rate limiter")

    args = parser.parse_args()

    asyncio.run(
        run_stress_test(
            base_url=args.base_url.rstrip("/"),
            certs_dir=Path(args.certs_dir),
            total_requests=args.total_requests,
            concurrency=args.concurrency,
            poll_interval=args.poll_interval,
            poll_timeout=args.poll_timeout,
            output_dir=Path(args.output_dir),
            bypass_rate_limit=not args.no_bypass,
        )
    )


if __name__ == "__main__":
    main()
