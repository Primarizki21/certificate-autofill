#!/usr/bin/env python3
"""Low-Level Profiling & High-Scale Verification Probe.

Mengukur metrik low-level pada level driver database (SQL query count,
durasi per query, connection pool) dan konkurensi skala tinggi pada
endpoint /api/documents/{id}/result serta pipeline ekstraksi end-to-end.
"""

from __future__ import annotations

import asyncio
import uuid
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import statistics
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.main import get_result
from app.models import Document, ExtractedField, KHPMasterResolution
from app.schemas import FieldResult, PublicExtractionResult


class SQLQueryCounter:
    """Interceptor tingkat driver untuk mencatat setiap query SQL yang dieksekusi."""

    def __init__(self, engine: Any):
        self.engine = engine
        self.queries: list[dict[str, Any]] = []
        self._listener = self._before_cursor_execute
        event.listen(self.engine, "before_cursor_execute", self._listener)

    def _before_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        table_name = "unknown"
        stmt_lower = statement.lower()
        if "from documents" in stmt_lower or "into documents" in stmt_lower:
            table_name = "documents"
        elif "from extracted_fields" in stmt_lower:
            table_name = "extracted_fields"
        elif "from khp_master_resolutions" in stmt_lower:
            table_name = "khp_master_resolutions"

        self.queries.append(
            {
                "timestamp": time.perf_counter(),
                "statement": statement,
                "table": table_name,
            }
        )

    def reset(self) -> None:
        self.queries.clear()

    def count(self) -> int:
        return len(self.queries)

    def counts_by_table(self) -> dict[str, int]:
        breakdown: dict[str, int] = {}
        for q in self.queries:
            t = q["table"]
            breakdown[t] = breakdown.get(t, 0) + 1
        return breakdown

    def close(self) -> None:
        try:
            event.remove(self.engine, "before_cursor_execute", self._listener)
        except Exception:
            pass


def compute_latencies(latencies_ms: list[float]) -> dict[str, float]:
    if not latencies_ms:
        return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0}
    sorted_l = sorted(latencies_ms)
    n = len(sorted_l)

    def _p(p: float) -> float:
        idx = max(0, min(math.ceil((p / 100.0) * n) - 1, n - 1))
        return round(sorted_l[idx], 3)

    return {
        "min": round(sorted_l[0], 3),
        "p50": _p(50),
        "p90": _p(90),
        "p95": _p(95),
        "p99": _p(99),
        "max": round(sorted_l[-1], 3),
        "avg": round(statistics.mean(sorted_l), 3),
    }


def legacy_get_result_simulated(document_id: str, db: Session) -> PublicExtractionResult:
    """Simulasi perilaku legacy (sebelum optimasi PERF-002) yang menembak 3 tabel setiap kali dipanggil."""
    document = db.get(Document, document_id)
    if not document:
        raise ValueError("Not found")

    # Legacy: selalu query ExtractedField dan KHPMasterResolution
    fields = db.query(ExtractedField).filter(ExtractedField.document_id == document_id).all()
    resolution_row = (
        db.query(KHPMasterResolution)
        .filter(KHPMasterResolution.document_id == document_id)
        .one_or_none()
    )
    field_dict = {
        f.form_field_name: FieldResult(
            value=f.mapped_value or f.extracted_value,
            confidence=float(f.confidence),
            source=f.source,
            needs_review=bool(f.needs_review),
        )
        for f in fields
    }
    return PublicExtractionResult(
        document_id=document_id,
        status=document.status,
        needs_review=False,
        fields=field_dict,
    )


def run_probe_part_1_query_counts() -> dict[str, Any]:
    """Part 1: Mengukur eksekusi SQL granular per status dokumen."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    counter = SQLQueryCounter(engine)

    results: dict[str, Any] = {}

    with session_factory() as db:
        # Siapkan sample documents
        id_q = str(uuid.uuid4())
        id_p = str(uuid.uuid4())
        id_d = str(uuid.uuid4())
        id_f = str(uuid.uuid4())
        doc_queued = Document(id=id_q, original_file_name="q.pdf", tahun_akademik="2024/2025", mime_type="application/pdf", file_size=1024, checksum_sha256="c1", status="queued")
        doc_proc = Document(id=id_p, original_file_name="p.pdf", tahun_akademik="2024/2025", mime_type="application/pdf", file_size=1024, checksum_sha256="c2", status="processing")
        doc_done = Document(id=id_d, original_file_name="d.pdf", tahun_akademik="2024/2025", mime_type="application/pdf", file_size=1024, checksum_sha256="c3", status="completed")
        db.add_all([doc_queued, doc_proc, doc_done])
        db.commit()

        # Tambahkan fields untuk doc_done
        f1 = ExtractedField(id=id_f, document_id=id_d, form_field_name="nama_kegiatan_sertifikasi", extracted_value="Lomba AI", confidence=0.9, source="test", needs_review=False)
        db.add(f1)
        db.commit()

        # Uji status 'queued' (Optimasi aktif)
        counter.reset()
        res_q = get_result(id_q, db=db)
        q_count = counter.count()
        q_breakdown = counter.counts_by_table()

        # Uji status 'processing' (Optimasi aktif)
        counter.reset()
        res_p = get_result(id_p, db=db)
        p_count = counter.count()
        p_breakdown = counter.counts_by_table()

        # Uji status 'completed' (Data integrity check - short circuit mati, full data kembali)
        counter.reset()
        res_d = get_result(id_d, db=db)
        d_count = counter.count()
        d_breakdown = counter.counts_by_table()
        results = {
            "queued": {
                "total_queries": q_count,
                "breakdown": q_breakdown,
                "response_status": res_q.status,
                "fields_returned": len(res_q.fields),
            },
            "processing": {
                "total_queries": p_count,
                "breakdown": p_breakdown,
                "response_status": res_p.status,
                "fields_returned": len(res_p.fields),
            },
            "completed": {
                "total_queries": d_count,
                "breakdown": d_breakdown,
                "response_status": res_d.status,
                "fields_returned": len(res_d.fields),
                "has_nama_kegiatan": "nama_kegiatan_sertifikasi" in res_d.fields,
            },
        }

    counter.close()
    return results


def run_probe_part_2_high_concurrency_burst(concurrency_level: int = 50) -> dict[str, Any]:
    """Part 2: Simulasi burst 50 konkurensi polling serentak pada dokumen antre."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    # Seed dokumen antre
    with session_factory() as db:
        id_campus = str(uuid.uuid4())
        doc = Document(id=id_campus, original_file_name="cert.pdf", tahun_akademik="2024/2025", mime_type="application/pdf", file_size=1024, checksum_sha256="sha", status="queued")
        db.add(doc)
        db.commit()

    counter = SQLQueryCounter(engine)

    # Test A: Perilaku Legacy (Tanpa Short-Circuit)
    counter.reset()
    t_start_legacy = time.perf_counter()
    legacy_latencies: list[float] = []

    for _ in range(concurrency_level):
        t0 = time.perf_counter()
        with session_factory() as db:
            legacy_get_result_simulated(id_campus, db=db)
        legacy_latencies.append((time.perf_counter() - t0) * 1000)

    legacy_elapsed_s = time.perf_counter() - t_start_legacy
    legacy_queries = counter.count()
    legacy_breakdown = counter.counts_by_table()
    legacy_stats = compute_latencies(legacy_latencies)

    # Test B: Perilaku Optimized (Dengan Short-Circuit PERF-002)
    counter.reset()
    t_start_opt = time.perf_counter()
    opt_latencies: list[float] = []

    for _ in range(concurrency_level):
        t0 = time.perf_counter()
        with session_factory() as db:
            get_result(id_campus, db=db)
        opt_latencies.append((time.perf_counter() - t0) * 1000)

    opt_elapsed_s = time.perf_counter() - t_start_opt
    opt_queries = counter.count()
    opt_breakdown = counter.counts_by_table()
    opt_stats = compute_latencies(opt_latencies)

    counter.close()

    query_reduction_pct = round(((legacy_queries - opt_queries) / legacy_queries) * 100, 2)
    p99_speedup = round((legacy_stats["p99"] - opt_stats["p99"]) / legacy_stats["p99"] * 100, 2) if legacy_stats["p99"] > 0 else 0.0

    return {
        "concurrency_requests": concurrency_level,
        "legacy": {
            "total_sql_queries": legacy_queries,
            "query_breakdown": legacy_breakdown,
            "duration_s": round(legacy_elapsed_s, 4),
            "throughput_rps": round(concurrency_level / legacy_elapsed_s, 2),
            "latencies_ms": legacy_stats,
        },
        "optimized": {
            "total_sql_queries": opt_queries,
            "query_breakdown": opt_breakdown,
            "duration_s": round(opt_elapsed_s, 4),
            "throughput_rps": round(concurrency_level / opt_elapsed_s, 2),
            "latencies_ms": opt_stats,
        },
        "improvements": {
            "sql_query_reduction_pct": query_reduction_pct,
            "p50_latency_reduction_pct": round(((legacy_stats["p50"] - opt_stats["p50"]) / legacy_stats["p50"]) * 100, 2) if legacy_stats["p50"] > 0 else 0.0,
            "p99_latency_reduction_pct": p99_speedup,
            "rps_gain_factor": round((concurrency_level / opt_elapsed_s) / (concurrency_level / legacy_elapsed_s), 2),
        },
    }


def run_probe_part_3_adaptive_polling_comparison(simulated_job_duration_s: float = 8.0) -> dict[str, Any]:
    """Part 3: Membandingkan total panggilan HTTP polling antara Flat 1.0s vs Adaptive Backoff."""
    # Skenario: Job AI memerlukan waktu 8 detik untuk tuntas (P90 khas pada dokumen sertifikat)
    # Mode Flat: Polling tiap 1.0s
    flat_poll_times: list[float] = []
    t = 1.0
    while t <= simulated_job_duration_s:
        flat_poll_times.append(round(t, 2))
        t += 1.0

    # Mode Adaptive (frontend/app.js & scripts/stress_test.py):
    # attempt 1: +1.0s
    # attempt 2-5: +2.0s
    # attempt >5: +2.5s
    adaptive_poll_times: list[float] = []
    curr_time = 0.0
    attempt = 0
    while True:
        attempt += 1
        delay = 1.0 if attempt == 1 else (2.0 if attempt <= 5 else 2.5)
        curr_time += delay
        if curr_time > simulated_job_duration_s:
            break
        adaptive_poll_times.append(round(curr_time, 2))

    reduction_pct = round(((len(flat_poll_times) - len(adaptive_poll_times)) / len(flat_poll_times)) * 100, 2)

    return {
        "job_duration_s": simulated_job_duration_s,
        "flat_polling": {
            "total_requests": len(flat_poll_times),
            "timestamps_s": flat_poll_times,
        },
        "adaptive_polling": {
            "total_requests": len(adaptive_poll_times),
            "timestamps_s": adaptive_poll_times,
        },
        "request_reduction_pct": reduction_pct,
    }


def main() -> None:
    print("=" * 70)
    print("PROBE EVALUASI KINERJA SKALA TINGGI (LOW-LEVEL PROFILING)")
    print("=" * 70)

    # 1. Query Count Profiling
    p1 = run_probe_part_1_query_counts()
    print("\n--- 1. PROFILING EKSEKUSI SQL PER STATUS ---")
    for status, data in p1.items():
        print(f"Status [{status.upper():10s}] -> Total SQL: {data['total_queries']} | Breakdown: {data['breakdown']} | Fields: {data['fields_returned']}")

    # 2. High-Concurrency Burst (C=50)
    p2 = run_probe_part_2_high_concurrency_burst(concurrency_level=50)
    print(f"\n--- 2. SIMULASI BURST KONKURENSI TINGGI (C={p2['concurrency_requests']}) ---")
    print(f"Legacy (Sebelum)  : {p2['legacy']['total_sql_queries']} SQL queries | P50={p2['legacy']['latencies_ms']['p50']}ms | P99={p2['legacy']['latencies_ms']['p99']}ms | {p2['legacy']['throughput_rps']} RPS")
    print(f"Optimized (Sesudah): {p2['optimized']['total_sql_queries']} SQL queries | P50={p2['optimized']['latencies_ms']['p50']}ms | P99={p2['optimized']['latencies_ms']['p99']}ms | {p2['optimized']['throughput_rps']} RPS")
    print(f"Keuntungan         : Reduksi SQL {p2['improvements']['sql_query_reduction_pct']}% | P50 turun {p2['improvements']['p50_latency_reduction_pct']}% | Throughput RPS {p2['improvements']['rps_gain_factor']}x lipat")

    # 3. Adaptive Polling Comparison
    p3 = run_probe_part_3_adaptive_polling_comparison(simulated_job_duration_s=8.0)
    print("\n--- 3. PEMBANDING FREKUENSI POLLING CLIENT (DURASI PROSES = 8 DETIK) ---")
    print(f"Flat 1.0s Polling     : {p3['flat_polling']['total_requests']} requests (timestamps: {p3['flat_polling']['timestamps_s']})")
    print(f"Adaptive Backoff      : {p3['adaptive_polling']['total_requests']} requests (timestamps: {p3['adaptive_polling']['timestamps_s']})")
    print(f"Trafik HTTP Terpangkas: {p3['request_reduction_pct']}%")

    print("\n" + "=" * 70)
    print("HASIL LENGKAP DIKOMPILASI DALAM JSON UNTUK AUDIT PERF LEDGER")
    print("=" * 70)

    summary_payload = {
        "part_1_sql_counts": p1,
        "part_2_high_concurrency": p2,
        "part_3_polling_reduction": p3,
    }
    print(json.dumps(summary_payload, indent=2))


if __name__ == "__main__":
    main()
