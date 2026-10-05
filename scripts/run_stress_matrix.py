#!/usr/bin/env python3
"""Runner Otomatis Matriks Stress Testing & Evaluasi MLOps / DevOps.

Menjalankan serangkaian skenario pengujian beban terstruktur (Matriks A, B, C),
mengatur penskalaan horizontal worker Docker Compose, memastikan isolasi
antrean per pengujian, dan mengompilasi laporan komparatif terpadu.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import httpx

from scripts.stress_test import run_stress_test

MATRIX_SCENARIOS: dict[str, dict[str, Any]] = {
    # Matriks A: Ingestion Concurrency Sweep (W=2 konstan, N=100 konstan)
    "A1": {
        "matrix": "A",
        "name": "Ingestion Baseline (C=1)",
        "docs": 100,
        "concurrency": 1,
        "workers": 2,
        "description": "Latensi upload sekuensial baseline (concurrency 1)",
    },
    "A2": {
        "matrix": "A",
        "name": "Ingestion Moderate (C=5)",
        "docs": 100,
        "concurrency": 5,
        "workers": 2,
        "description": "Perilaku koneksi simultan 5 klien",
    },
    "A3": {
        "matrix": "A",
        "name": "Ingestion Busy (C=10)",
        "docs": 100,
        "concurrency": 10,
        "workers": 2,
        "description": "Batas normal beban sibuk 10 klien simultan",
    },
    "A4": {
        "matrix": "A",
        "name": "Ingestion Peak (C=15)",
        "docs": 100,
        "concurrency": 15,
        "workers": 2,
        "description": "Batas puncak upload API 15 klien simultan",
    },
    # Matriks B: Worker Horizontal Scaling Sweep (C=10 konstan, N=100 konstan)
    "B1": {
        "matrix": "B",
        "name": "Scale Worker Single (W=1)",
        "docs": 100,
        "concurrency": 10,
        "workers": 1,
        "description": "Throughput baseline pemrosesan dengan 1 kontainer worker",
    },
    "B2": {
        "matrix": "B",
        "name": "Scale Worker Dual (W=2)",
        "docs": 100,
        "concurrency": 10,
        "workers": 2,
        "description": "Peningkatan throughput pemrosesan dengan 2 kontainer worker",
    },
    "B3": {
        "matrix": "B",
        "name": "Scale Worker Quad (W=4)",
        "docs": 100,
        "concurrency": 10,
        "workers": 4,
        "description": "Peningkatan throughput puncak pemrosesan dengan 4 kontainer worker",
    },
    # Matriks C: Grand Peak Endurance (N=1000 puncak, C=15, W=4)
    "C1": {
        "matrix": "C",
        "name": "Grand Peak Endurance (N=1000)",
        "docs": 1000,
        "concurrency": 15,
        "workers": 4,
        "description": "Uji ketahanan volume puncak 1.000 dokumen dengan 4 worker",
    },
}


def scale_docker_workers(target_workers: int) -> bool:
    """Ubah jumlah kontainer worker menggunakan docker compose up --scale worker=k."""
    print(f"\n[DevOps] Menyesuaikan replika worker Docker Compose menjadi {target_workers} kontainer...")
    cmd = ["docker", "compose", "up", "-d", "--scale", f"worker={target_workers}"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✓ Berhasil mengatur worker={target_workers}: {res.stdout.strip() or 'OK'}")
        time.sleep(5)  # Memberikan jeda waktu inisialisasi worker baru
        return True
    except subprocess.CalledProcessError as exc:
        print(f"⚠️ Gagal melakukan scaling worker Docker: {exc.stderr}")
        return False
    except FileNotFoundError:
        print("⚠️ Perintah docker compose tidak ditemukan di sistem host.")
        return False


def wait_for_queue_drain(base_url: str, timeout_seconds: int = 180) -> bool:
    """Tunggu hingga antrean PostgreSQL kosong untuk memastikan isolasi antar skenario."""
    print("[Antrean] Memeriksa status antrean worker sebelum memulai skenario...")
    t_start = time.perf_counter()
    while time.perf_counter() - t_start < timeout_seconds:
        try:
            res = httpx.get(f"{base_url}/metrics", timeout=5.0)
            if res.status_code == 200:
                text = res.text
                queued_match = re.search(r'cert_queue_jobs_count\{status="queued"\}\s+([0-9.]+)', text)
                proc_match = re.search(r'cert_queue_jobs_count\{status="processing"\}\s+([0-9.]+)', text)
                queued_val = float(queued_match.group(1)) if queued_match else 0.0
                proc_val = float(proc_match.group(1)) if proc_match else 0.0

                if queued_val == 0.0 and proc_val == 0.0:
                    print("✓ Antrean bersih (queued=0, processing=0). Siap memulai skenario baru.")
                    return True
                print(f"  Menunggu antrean tuntas... (queued={queued_val}, processing={proc_val})")
        except Exception as exc:
            print(f"  Peringatan saat memeriksa metrics: {exc}")

        time.sleep(2.0)

    print("⚠️ Batas waktu tunggu antrean habis. Melanjutkan pengujian.")
    return False


def build_markdown_summary(
    results_map: dict[str, dict[str, Any]],
    start_time: str,
    end_time: str,
    total_elapsed: float,
) -> str:
    """Susun laporan komparatif markdown menyeluruh dari seluruh skenario pengujian."""
    lines: list[str] = [
        "# Laporan Komparatif Matriks Stress Testing & Evaluasi MLOps/DevOps",
        "",
        f"- **Waktu Pengujian**: {start_time} s/d {end_time}",
        f"- **Durasi Total Eksekusi**: {total_elapsed} detik ({round(total_elapsed / 60, 2)} menit)",
        f"- **Jumlah Skenario Diuji**: {len(results_map)} skenario",
        "",
        "---",
        "",
        "## 1. Tabel Komparasi Menyeluruh Seluruh Skenario",
        "",
        "| ID | Skenario | Dokumen ($N$) | Concurrency ($C$) | Workers ($W$) | Upload P50 (ms) | Upload P90 (ms) | Upload P99 (ms) | E2E P50 (s) | E2E P90 (s) | E2E P99 (s) | Total Durasi (s) | Throughput (RPS) | Sukses (%) |",
        "|:---:|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for sc_id, data in sorted(results_map.items()):
        cfg = data["config"]
        summary = data.get("summary", {})
        http_p = summary.get("http_ingestion", {}).get("latency_ms", {})
        e2e_p = summary.get("end_to_end_processing", {}).get("latency_ms", {})
        meta = summary.get("metadata", {})
        completion_pct = summary.get("end_to_end_processing", {}).get("completion_rate_pct", 0.0)

        lines.append(
            f"| **{sc_id}** | {cfg['name']} | {cfg['docs']} | {cfg['concurrency']} | {cfg['workers']} | "
            f"{http_p.get('p50', '-')} ms | {http_p.get('p90', '-')} ms | {http_p.get('p99', '-')} ms | "
            f"{round(e2e_p.get('p50', 0) / 1000, 2)} s | {round(e2e_p.get('p90', 0) / 1000, 2)} s | {round(e2e_p.get('p99', 0) / 1000, 2)} s | "
            f"{meta.get('total_elapsed_seconds', '-')} s | {meta.get('throughput_rps', '-')} RPS | {completion_pct}% |"
        )

    # Analisis Matriks B: Skalabilitas Paralel
    if all(k in results_map for k in ("B1", "B2", "B3")):
        lines.extend([
            "",
            "---",
            "",
            "## 2. Analisis Skalabilitas Horizontal Worker (Matriks B)",
            "",
            "Mengukur dampak penambahan worker terhadap durasi total pemrosesan antrean ($N=100$, $C=10$):",
            "",
            "| Skenario | Worker ($k$) | Total Durasi ($T_k$) | Throughput (RPS) | Speedup ($S = T_1 / T_k$) | Efisiensi Paralel ($E = S / k$) |",
            "|:---:|:---:|:---:|:---:|:---:|:---:|",
        ])
        t1 = results_map["B1"]["summary"]["metadata"]["total_elapsed_seconds"]
        for sc_id in ("B1", "B2", "B3"):
            w = results_map[sc_id]["config"]["workers"]
            tk = results_map[sc_id]["summary"]["metadata"]["total_elapsed_seconds"]
            speedup = round(t1 / tk, 2) if tk > 0 else 0.0
            efficiency = round((speedup / w) * 100, 2) if w > 0 else 0.0
            rps = results_map[sc_id]["summary"]["metadata"]["throughput_rps"]
            lines.append(f"| **{sc_id}** | {w} worker | {tk} s | {rps} RPS | **{speedup}x** | **{efficiency}%** |")

    # Analisis Matriks A: Dampak Concurrency
    lines.extend([
        "",
        "---",
        "",
        "## 3. Analisis Lapis Ingestion API (Matriks A: Concurrency Sweep)",
        "",
        "Mengukur ketahanan FastAPI saat menerima request simultan ($N=100$, $W=2$):",
        "",
        "| Skenario | Concurrency ($C$) | Upload P50 (ms) | Upload P90 (ms) | Upload P99 (ms) | Status Keberhasilan |",
        "|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])
    for sc_id in ("A1", "A2", "A3", "A4"):
        if sc_id in results_map:
            cfg = results_map[sc_id]["config"]
            http_p = results_map[sc_id]["summary"]["http_ingestion"]["latency_ms"]
            success_pct = results_map[sc_id]["summary"]["http_ingestion"]["success_rate_pct"]
            lines.append(
                f"| **{sc_id}** | {cfg['concurrency']} | {http_p.get('p50', '-')} ms | "
                f"{http_p.get('p90', '-')} ms | {http_p.get('p99', '-')} ms | {success_pct}% |"
            )

    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Runner Matriks Pengujian Beban MLOps/DevOps")
    parser.add_argument("--base-url", default="http://localhost:8000", help="URL dasar API")
    parser.add_argument("--certs-dir", default="certs_unified", help="Direktori berkas sertifikat")
    parser.add_argument("--output-dir", default="docs/stress_test", help="Direktori penyimpanan laporan")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["A1", "A2", "A3", "A4", "B1", "B2", "B3", "C1"],
        help="Daftar skenario yang akan dijalankan (contoh: A1 A2 B1 C1)",
    )
    parser.add_argument("--no-scale", action="store_true", help="Nonaktifkan scaling otomatis Docker Compose")

    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    certs_dir = Path(args.certs_dir)
    output_dir = Path(args.output_dir)
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*75}")
    print("ORCHESTRATOR MATRIKS STRESS TESTING & EVALUASI MLOPS")
    print(f"{'='*75}")
    print(f"Target API     : {base_url}")
    print(f"Sertifikat     : {certs_dir}")
    print(f"Skenario Aktif : {', '.join(args.scenarios)}")
    print(f"Output Root    : {output_dir}")
    print(f"{'='*75}\n")

    global_start_iso = datetime.now(timezone.utc).isoformat()
    t_global_start = time.perf_counter()

    results_map: dict[str, dict[str, Any]] = {}
    summary_json_path = output_dir / "matrix_summary.json"
    if summary_json_path.exists():
        try:
            prev_data = json.loads(summary_json_path.read_text(encoding="utf-8"))
            results_map.update(prev_data.get("scenarios", {}))
        except Exception:
            pass
    current_workers = -1

    for sc_id in args.scenarios:
        if sc_id not in MATRIX_SCENARIOS:
            print(f"⚠️ Melewati skenario tidak dikenal: {sc_id}")
            continue

        cfg = MATRIX_SCENARIOS[sc_id]
        print(f"\n{'#'*75}")
        print(f"MEMULAI SKENARIO [{sc_id}]: {cfg['name']}")
        print(f"Deskripsi: {cfg['description']}")
        print(f"Parameter: Dokumen={cfg['docs']}, Concurrency={cfg['concurrency']}, Workers={cfg['workers']}")
        print(f"{'#'*75}")

        # Skalakan worker jika berbeda dengan konfigurasi aktif
        if not args.no_scale and cfg["workers"] != current_workers:
            scale_docker_workers(cfg["workers"])
            current_workers = cfg["workers"]

        # Pastikan antrean bersih sebelum mulai
        wait_for_queue_drain(base_url)

        # Siapkan folder output spesifik skenario
        scenario_out_dir = runs_dir / sc_id
        scenario_out_dir.mkdir(parents=True, exist_ok=True)

        # Jalankan stress test untuk skenario ini
        summary = await run_stress_test(
            base_url=base_url,
            certs_dir=certs_dir,
            total_requests=cfg["docs"],
            concurrency=cfg["concurrency"],
            poll_interval=1.0,
            poll_timeout=600.0 if cfg["docs"] <= 100 else 3600.0,
            output_dir=scenario_out_dir,
            bypass_rate_limit=True,
        )

        results_map[sc_id] = {
            "config": cfg,
            "summary": summary,
        }

    t_global_end = time.perf_counter()
    global_elapsed = round(t_global_end - t_global_start, 2)
    global_end_iso = datetime.now(timezone.utc).isoformat()

    # Susun dan simpan ringkasan matriks
    md_report = build_markdown_summary(
        results_map=results_map,
        start_time=global_start_iso,
        end_time=global_end_iso,
        total_elapsed=global_elapsed,
    )
    summary_md_path = output_dir / "matrix_summary.md"
    summary_md_path.write_text(md_report, encoding="utf-8")

    summary_json_path = output_dir / "matrix_summary.json"
    summary_json_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "start_time": global_start_iso,
                    "end_time": global_end_iso,
                    "total_elapsed_seconds": global_elapsed,
                },
                "scenarios": results_map,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Cetak laporan akhir ke konsol
    print(f"\n\n{'='*75}")
    print("HASIL LENGKAP MATRIKS STRESS TEST & MLOPS")
    print(f"{'='*75}")
    print(md_report)
    print(f"Laporan komparatif tersimpan di:\n  - {summary_md_path}\n  - {summary_json_path}")
    print(f"{'='*75}\n")


if __name__ == "__main__":
    asyncio.run(main())
