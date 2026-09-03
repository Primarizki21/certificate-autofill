"""Benchmark GLiNER dan GLiNER2.5 pada dataset 74 sertifikat (GT v9 + Matcher v2).

Mendukung model:
1. urchade/gliner_multi-v2.1 (GLiNER v2.1 Multilingual Span Model)
2. fastino/gliner2.5-base-v1 (GLiNER2.5 Boundary Extractor dari paper arXiv:2507.18546)

Usage:
    uv run python -m tests.benchmark_gliner --models gliner-multi-v2.1 gliner2.5-base
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

REPO = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO / "backend"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(BACKEND_DIR))

from app.services.field_extractor import ExtractedValue
from tests.evaluation_framework import EVAL_FIELDS, aggregate_results, evaluate_row, load_csv, print_report
from tests.post_processors import score_entity_for_field

GT_CSV = REPO / "Ground_Truth_Sertifikat_v9.csv"
TESSERACT_TEXTS = REPO / "tests" / "benchmark_runs" / "ocr_experiment" / "tesseract_primary_v4" / "extracted_texts"
RUNS_DIR = REPO / "tests" / "benchmark_runs"
SEED = 42

FREE_INSTITUTION_FIELDS = {
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "nomor_bukti_fisik_nomor_sertifikasi",
}

GLINER_MODELS = {
    "gliner-multi-v2.1": "urchade/gliner_multi-v2.1",
    "gliner2.5-base": "fastino/gliner2.5-base-v1",
}


@dataclass(frozen=True)
class ExtractedEntity:
    label: str
    text: str
    score: float


def _load_gt_rows(csv_path: Path) -> dict[str, dict[str, str]]:
    raw_rows = load_csv(str(csv_path))
    return {
        row.get("nama_file", "").rsplit(".", 1)[0]: row
        for row in raw_rows
        if row.get("nama_file")
    }


def _read_text(path: Path) -> str:
    return "\n".join(l for l in path.read_text(encoding="utf-8").splitlines() if not l.startswith("#")).strip()


def _chunk_text(text: str, chunk_size: int = 250, overlap: int = 50) -> list[str]:
    words = text.split()
    if len(words) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += (chunk_size - overlap)
    return chunks


def _predict_gliner_v1(model: Any, text: str, labels: list[str], threshold: float = 0.25) -> list[ExtractedEntity]:
    chunks = _chunk_text(text, chunk_size=200, overlap=40)
    entities: list[ExtractedEntity] = []
    seen = set()
    for chunk in chunks:
        preds = model.predict_entities(chunk, labels, threshold=threshold)
        for p in preds:
            txt = p["text"].strip()
            key = (p["label"], txt.lower())
            if key not in seen and len(txt) > 2:
                seen.add(key)
                entities.append(ExtractedEntity(label=p["label"], text=txt, score=float(p["score"])))
    return entities


def _predict_gliner2(model: Any, text: str, labels: list[str]) -> list[ExtractedEntity]:
    chunks = _chunk_text(text, chunk_size=250, overlap=50)
    entities: list[ExtractedEntity] = []
    seen = set()
    for chunk in chunks:
        try:
            res = model.extract_entities(chunk, labels)
            ent_dict = res.get("entities", {})
            for lbl, vals in ent_dict.items():
                if isinstance(vals, list):
                    for v in vals:
                        txt = str(v).strip()
                        key = (lbl, txt.lower())
                        if key not in seen and len(txt) > 2:
                            seen.add(key)
                            entities.append(ExtractedEntity(label=lbl, text=txt, score=0.85))
        except Exception as e:
            continue
    return entities


def map_gliner_entities_to_fields(entities: list[ExtractedEntity], full_text: str, source: str) -> dict[str, ExtractedValue]:
    fields: dict[str, ExtractedValue] = {}

    # 1. Nama Kegiatan
    evt_candidates = [e for e in entities if any(k in e.label.lower() for k in ("event", "kegiatan"))]
    if evt_candidates:
        # Filter out junk candidates (like NIP/NIM or single letters)
        valid_evts = [e for e in evt_candidates if not re.match(r'^(NIP|NIK|NIM|NO|NOMOR)\b', e.text, re.IGNORECASE) and len(e.text) > 4]
        if valid_evts:
            best_evt = max(valid_evts, key=lambda e: len(e.text))
            fields["nama_kegiatan_sertifikasi"] = ExtractedValue(best_evt.text.replace("\n", " ").strip(), round(best_evt.score, 2), source)

    # 2. Penyelenggara
    org_candidates = [e for e in entities if any(k in e.label.lower() for k in ("organizer", "penyelenggara", "organization", "organisasi"))]
    if org_candidates:
        valid_orgs = [e for e in org_candidates if not re.match(r'^(PANITIA|PESERTA|JUARA)\b', e.text, re.IGNORECASE) and len(e.text) > 3]
        if valid_orgs:
            best_org = max(valid_orgs, key=lambda e: len(e.text))
            fields["penyelenggara_kegiatan"] = ExtractedValue(best_org.text.replace("\n", " ").strip(), round(best_org.score, 2), source)

    # 3. Nomor Sertifikat
    num_candidates = [e for e in entities if any(k in e.label.lower() for k in ("certificate number", "nomor sertifikat", "nomor"))]
    if num_candidates:
        valid_nums = [e for e in num_candidates if any(c.isdigit() for c in e.text) and any(c in e.text for c in ("/", ".", "-"))]
        if valid_nums:
            best_num = max(valid_nums, key=lambda e: e.score)
            cleaned_num = re.sub(r'^(Nomor|No\.?|Number)\s*[:.]?\s*', '', best_num.text, flags=re.IGNORECASE).strip()
            fields["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(cleaned_num, round(best_num.score, 2), source)

    # 4. Tanggal
    date_candidates = [e for e in entities if any(k in e.label.lower() for k in ("date", "tanggal"))]
    if date_candidates:
        valid_dates = [e for e in date_candidates if any(c.isdigit() for c in e.text)]
        if valid_dates:
            d_start = valid_dates[0]
            d_end = valid_dates[-1]
            fields["waktu_mulai_pelaksanaan"] = ExtractedValue(d_start.text.strip(), round(d_start.score, 2), source)
            fields["waktu_selesai_pelaksanaan"] = ExtractedValue(d_end.text.strip(), round(d_end.score, 2), source)

    return fields


def _bootstrap_ci(row_results: list[dict], iterations: int = 1000, seed: int = SEED) -> dict[str, float]:
    rng = random.Random(seed)
    observations = []
    for result in row_results:
        exact = sum(1 for field in EVAL_FIELDS if field in result and result[field]["exact"])
        total = sum(1 for field in EVAL_FIELDS if field in result)
        observations.append((exact, total))
    values: list[float] = []
    for _ in range(iterations):
        sample = [rng.choice(observations) for _ in observations]
        exact = sum(item[0] for item in sample)
        total = sum(item[1] for item in sample)
        values.append(exact / total if total else 0.0)
    values.sort()
    return {
        "iterations": iterations,
        "mean": sum(values) / len(values),
        "lower_95": values[int(0.025 * (len(values) - 1))],
        "upper_95": values[int(0.975 * (len(values) - 1))],
    }


def _mutate_institution(text: str) -> str:
    replacements = (("Universitas Airlangga", "Universitas Negeri Semarang"), ("UNAIR", "UNS"), ("FTMM", "FST"))
    for source, target in replacements:
        text = re.sub(re.escape(source), target, text, flags=re.IGNORECASE)
    return text


def _inject_ocr_noise(text: str, rate: float, rng: random.Random) -> str:
    substitutions = {"5": "S", "S": "5", "8": "B", "B": "8", "0": "O", "O": "0", "1": "I", "I": "1"}
    return "".join(substitutions.get(char, char) if char.upper() in substitutions and rng.random() < rate else char for char in text)


def _free_field_exact(row_result: dict) -> tuple[int, int]:
    selected = [result for field, result in row_result.items() if field in FREE_INSTITUTION_FIELDS]
    return sum(1 for result in selected if result["exact"]), len(selected)


def run_benchmark(model_key: str, hf_id: str, gt_rows: dict[str, dict[str, str]], device: str) -> dict[str, Any]:
    print(f"\n=======================================================")
    print(f"BENCHMARKING: {model_key} ({hf_id}) on {device.upper()}")
    print(f"=======================================================")

    is_gliner2 = "gliner2" in model_key
    t0_load = time.perf_counter()

    if is_gliner2:
        from gliner2 import AutoExtractor
        model = AutoExtractor.from_pretrained(hf_id, map_location=device)
    else:
        from gliner import GLiNER
        model = GLiNER.from_pretrained(hf_id, map_location=device)

    print(f"Model loaded in {time.perf_counter() - t0_load:.2f}s")

    labels_en = ["event name", "certificate number", "organizer", "date"]
    source_tag = f"gliner:{model_key}"

    clean_results = []
    ood_raw = {"mutation": [], "noise_10": [], "noise_25": [], "noise_50": []}
    per_cert_times = []

    stems = sorted(gt_rows.keys())
    for stem in stems:
        txt_path = TESSERACT_TEXTS / f"{stem}.txt"
        if not txt_path.exists():
            continue
        text = _read_text(txt_path)
        expected = gt_rows[stem]

        t_start = time.perf_counter()
        if is_gliner2:
            entities = _predict_gliner2(model, text, labels_en)
        else:
            entities = _predict_gliner_v1(model, text, labels_en, threshold=0.25)
        elapsed = time.perf_counter() - t_start
        per_cert_times.append(elapsed)

        mapped = map_gliner_entities_to_fields(entities, text, source_tag)
        row_eval = evaluate_row(mapped, expected)
        clean_results.append(row_eval)

        # OOD evaluations
        mut_text = _mutate_institution(text)
        mut_ents = _predict_gliner2(model, mut_text, labels_en) if is_gliner2 else _predict_gliner_v1(model, mut_text, labels_en, threshold=0.25)
        ood_raw["mutation"].append(evaluate_row(map_gliner_entities_to_fields(mut_ents, mut_text, source_tag), expected))

        for rate, key in [(0.10, "noise_10"), (0.25, "noise_25"), (0.50, "noise_50")]:
            rng = random.Random(f"{SEED}:{stem}:{int(rate*100)}")
            n_text = _inject_ocr_noise(text, rate, rng)
            n_ents = _predict_gliner2(model, n_text, labels_en) if is_gliner2 else _predict_gliner_v1(model, n_text, labels_en, threshold=0.25)
            ood_raw[key].append(evaluate_row(map_gliner_entities_to_fields(n_ents, n_text, source_tag), expected))

    # Aggregasi hasil
    summary = aggregate_results(clean_results)
    ci = _bootstrap_ci(clean_results)

    # OOD summary
    clean_exact, clean_total = map(sum, zip(*(_free_field_exact(row) for row in clean_results)))
    clean_acc = clean_exact / clean_total if clean_total else 0.0
    ood_summary = {"clean": {"exact": clean_acc, "count": clean_total}}
    for name, rows in ood_raw.items():
        exact, total = map(sum, zip(*(_free_field_exact(row) for row in rows))) if rows else (0, 0)
        acc = exact / total if total else 0.0
        ood_summary[name] = {"exact": acc, "count": total, "drop_points": (clean_acc - acc) * 100}

    slug = model_key.replace("-", "_").replace(".", "_")
    run_dir = RUNS_DIR / f"gliner_{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "model": model_key,
        "hf_id": hf_id,
        "mode": "zero_shot_schema_extraction",
        "labels": labels_en,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "bootstrap_ci": ci,
        "ood": ood_summary,
        "avg_latency_s": sum(per_cert_times) / len(per_cert_times) if per_cert_times else 0,
        "total_time_s": sum(per_cert_times),
        "results": clean_results,
    }

    (run_dir / "results.json").write_text(json.dumps(payload, indent=2, default=str))
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\n--- REPORT: {model_key} ---")
    print_report(summary)
    print(f"Bootstrap 95% CI: [{ci['lower_95']:.2%}, {ci['upper_95']:.2%}] (Mean: {ci['mean']:.2%})")
    print(f"Avg Latency: {payload['avg_latency_s']:.3f}s / cert (Total: {payload['total_time_s']:.1f}s)")
    return payload


def main():
    parser = argparse.ArgumentParser(description="Benchmark GLiNER dan GLiNER2.5 pada Tesseract OCR + GT v9")
    parser.add_argument("--models", nargs="+", choices=list(GLINER_MODELS.keys()), default=list(GLINER_MODELS.keys()))
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    gt_rows = _load_gt_rows(GT_CSV)
    print(f"Loaded {len(gt_rows)} ground truth certificate rows.")

    for m in args.models:
        run_benchmark(m, GLINER_MODELS[m], gt_rows, args.device)


if __name__ == "__main__":
    main()
