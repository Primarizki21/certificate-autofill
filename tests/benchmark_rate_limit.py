"""EXP-RATE-LIMIT-001: isolasi kuota per API key di satu IP.

Skenario portal kampus: banyak pemanggil datang dari satu alamat IP. Uji ini
memastikan setiap API key valid mendapat kuota sendiri, sedangkan permintaan
tanpa key memakai bucket IP.

Jalankan manual:
    EXP_DATABASE_URL=postgresql+psycopg2://... \
    python -m tests.benchmark_rate_limit
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from tests.experiment_io import write_bundle
from tests.experiment_server import create_schema, start_server, stop_server, wait_ready

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_ID = "EXP-RATE-LIMIT-001"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "experiments" / EXPERIMENT_ID
API_KEYS = [f"sk-exp-ratelimit-{index:02d}-1234567890" for index in range(1, 21)]


def git_revision() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def smallest_certificate() -> tuple[str, bytes]:
    candidates = [
        path
        for path in (REPO_ROOT / "certs_unified").iterdir()
        if path.suffix.lower() in {".pdf", ".png", ".jpeg"}
    ]
    candidates.sort(key=lambda path: path.stat().st_size)
    return candidates[0].name, candidates[0].read_bytes()


def upload(
    client: httpx.Client, base_url: str, payload: tuple[str, bytes], key: str | None
) -> tuple[int, float | None]:
    headers = {"X-API-Key": key} if key else {}
    name, content = payload
    response = client.post(
        f"{base_url}/api/documents",
        data={"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"},
        files={"file": (name, content, "application/pdf")},
        headers=headers,
    )
    retry_after = response.headers.get("Retry-After") if response.status_code == 429 else None
    return response.status_code, float(retry_after) if retry_after else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("EXP_DATABASE_URL", ""))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--per-key-requests", type=int, default=5)
    parser.add_argument("--burst-requests", type=int, default=70)
    parser.add_argument("--ip-requests", type=int, default=65)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("--database-url atau EXP_DATABASE_URL wajib diisi")
    if "exp" not in args.database_url and not args.force:
        raise SystemExit("URL database harus memuat 'exp' atau gunakan --force")

    os.environ["DATABASE_URL"] = args.database_url
    os.environ["APP_ENV"] = "test"
    os.environ["ADMIN_PASSWORD"] = "exp-ratelimit-admin"
    os.environ["API_KEYS"] = ",".join(API_KEYS)
    os.environ["REQUIRE_API_KEY"] = "false"
    os.environ["RATE_LIMIT_PER_MINUTE"] = "60"
    os.environ["QUEUE_BACKPRESSURE_SECONDS"] = "0"
    os.environ["PROCESSING_MODE"] = "db_worker"
    os.environ["ENABLE_TESSERACT_GEMINI"] = "false"
    os.environ["GOOGLE_API_KEY"] = ""
    os.environ["PYTHONPATH"] = f"{REPO_ROOT}:{REPO_ROOT / 'backend'}"

    create_schema(args.database_url)
    payload = smallest_certificate()

    started_at = datetime.now(timezone.utc)
    process = start_server(args.port, dict(os.environ))
    wait_ready(args.port)
    base_url = f"http://127.0.0.1:{args.port}"
    records: list[dict[str, Any]] = []
    per_key: dict[str, dict[str, int]] = {}
    burst: list[tuple[int, float | None]] = []
    ip_only: list[int] = []

    try:
        with httpx.Client(timeout=30.0) as client:
            for key in API_KEYS:
                statuses: dict[int, int] = {}
                for _ in range(args.per_key_requests):
                    status, _retry = upload(client, base_url, payload, key)
                    statuses[status] = statuses.get(status, 0) + 1
                per_key[key] = statuses
                records.append({"lane": "per_key", "key": key[-6:], "statuses": statuses})

            for _ in range(args.ip_requests):
                status, _retry = upload(client, base_url, payload, None)
                ip_only.append(status)
            records.append({"lane": "ip_only", "statuses": {
                status: ip_only.count(status) for status in set(ip_only)
            }})

            for _ in range(args.burst_requests):
                status, retry_after = upload(client, base_url, payload, API_KEYS[0])
                burst.append((status, retry_after))
            records.append({"lane": "burst_key_1", "statuses": {
                status: sum(1 for value in burst if value[0] == status)
                for status in {value[0] for value in burst}
            }})
    finally:
        stop_server(process)

    key_success = all(
        statuses.get(200, 0) == args.per_key_requests for statuses in per_key.values()
    )
    ip_limit_hit = 429 in ip_only
    burst_limit_hit = any(status == 429 for status, _ in burst)
    retry_after_present = all(
        retry_after is not None for status, retry_after in burst if status == 429
    )
    gates = {
        "setiap_key_punya_kuota_sendiri": key_success,
        "bucket_ip_terpisah_dari_key": ip_limit_hit,
        "burst_key_kena_429": burst_limit_hit,
        "429_membawa_retry_after": retry_after_present,
    }
    status = "PASS" if all(gates.values()) else "FAIL"

    metrics = {
        "experiment_id": EXPERIMENT_ID,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision(),
        "config": {
            "api_keys": len(API_KEYS),
            "per_key_requests": args.per_key_requests,
            "ip_requests": args.ip_requests,
            "burst_requests": args.burst_requests,
            "rate_limit_per_minute": 60,
        },
        "per_key": per_key,
        "ip_bucket": {status: ip_only.count(status) for status in set(ip_only)},
        "burst": {
            "statuses": {status: sum(1 for value in burst if value[0] == status)
                         for status in {value[0] for value in burst}},
            "first_429_index": next(
                (index for index, value in enumerate(burst) if value[0] == 429), None
            ),
        },
        "gates": gates,
        "status": status,
    }

    rows = [
        {"metric": "keys_tested", "value": len(API_KEYS)},
        {"metric": "requests_per_key", "value": args.per_key_requests},
        {"metric": "success_per_key", "value": args.per_key_requests if key_success else 0},
        {"metric": "ip_200_count", "value": ip_only.count(200)},
        {"metric": "ip_429_count", "value": ip_only.count(429)},
        {"metric": "burst_200_count", "value": sum(1 for value in burst if value[0] == 200)},
        {"metric": "burst_429_count", "value": sum(1 for value in burst if value[0] == 429)},
        {"metric": "burst_first_429_index", "value": metrics["burst"]["first_429_index"]},
    ]

    summary = f"""# {EXPERIMENT_ID} — Isolasi Rate Limit per API Key

Status: **{status}**

## Konfigurasi
- API key: {len(API_KEYS)} (semua valid, satu alamat IP)
- Limit: 60 permintaan/menit per identitas
- Permintaan per key: {args.per_key_requests}
- Permintaan tanpa key (bucket IP): {args.ip_requests}
- Burst satu key: {args.burst_requests}

## Hasil
| Uji | Hasil |
|---|---|
| Setiap key dapat {args.per_key_requests} sukses | {key_success} |
| Bucket IP terpisah (tanpa key kena 429) | {ip_limit_hit} |
| Burst key pertama kena 429 | {burst_limit_hit} |
| 429 membawa Retry-After | {retry_after_present} |

Distribusi bucket IP: 200={ip_only.count(200)}, 429={ip_only.count(429)}.
Burst key pertama: 200={sum(1 for value in burst if value[0] == 200)},
429={sum(1 for value in burst if value[0] == 429)} pada indeks
{metrics['burst']['first_429_index']}.

## Interpretasi
Portal kampus yang memakai banyak key di satu IP tidak saling memblokir.
Permintaan tanpa key tetap dibatasi per IP agar endpoint tidak terbuka bebas.
"""
    manifest = {
        "campaign_id": "CAMPAIGN-PRODUCTION-CAPACITY",
        "experiment_id": EXPERIMENT_ID,
        "parent_id": None,
        "role": "rate-limit-isolation",
        "started_at": metrics["started_at"],
        "finished_at": metrics["finished_at"],
        "git_revision": metrics["git_revision"],
        "command": "python -m tests.benchmark_rate_limit",
        "status": status,
        "inputs": {
            "api_keys": len(API_KEYS),
            "per_key_requests": args.per_key_requests,
            "ip_requests": args.ip_requests,
            "burst_requests": args.burst_requests,
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
        xlsx_sheets={"Ringkasan": rows},
        force=args.force,
    )
    print(f"{EXPERIMENT_ID}: {status} -> {args.output_dir}")


if __name__ == "__main__":
    main()
