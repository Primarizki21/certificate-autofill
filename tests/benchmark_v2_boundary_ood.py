"""Stress-test V2 boundaries on mutated raw OCR without new model calls."""

from __future__ import annotations

import argparse
import json
import random
import re
from datetime import datetime, timezone
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.v2_staging_common import (
    aggregate_rows,
    evaluate_fields,
    ensure_fresh_directory,
    load_cached_corpus,
    write_json,
)
from tests.v2_organizer_boundary import apply_organizer_boundary
from tests.v2_title_boundary import apply_title_boundary

MUTATIONS = (
    (r"universitas\s+airlangca", "Universitas Negeri Semarang"),
    (r"universitas\s+airlangga", "Universitas Negeri Semarang"),
    (r"unair", "UNS"),
    (r"airlangga", "Semarang"),
    (r"ftmm", "FST"),
    (r"airnology", "InnoFest"),
    (r"kakiwima", "CampusTalks"),
    (r"specta", "SPECTRUM"),
    (r"\bbrief\b", "BRIEFSUM"),
)
CONFUSIONS = {"5": "S", "8": "B", "0": "O", "1": "I"}
NOISE_LEVELS = (0.10, 0.25, 0.50)
FREE_FIELDS = (
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "tingkat",
)


def _mutate(text: str) -> str:
    for pattern, replacement in MUTATIONS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _inject_noise(text: str, level: float, rng: random.Random) -> str:
    chars = list(text)
    for index, char in enumerate(chars):
        if char.isalnum() and char in CONFUSIONS and rng.random() < level:
            chars[index] = CONFUSIONS[char]
    noisy = "".join(chars)
    if level <= 0:
        return noisy
    parts = noisy.split(" ")
    merged = [parts[0]]
    for word in parts[1:]:
        if word and rng.random() < level * 0.1:
            merged[-1] += word
        else:
            merged.append(word)
    return " ".join(merged)


def _candidate_rows(corpus: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return evaluate_fields(
        corpus,
        lambda item: {
            **item["v2_fields"],
            "nama_kegiatan_sertifikasi": apply_title_boundary(
                item["raw_text"], item["v2_fields"]["nama_kegiatan_sertifikasi"]
            ).value,
            "penyelenggara_kegiatan": apply_organizer_boundary(
                item["raw_text"], item["v2_fields"]["penyelenggara_kegiatan"]
            ).value,
        },
        source="v2_boundaries_ood",
    )


def _free_macro(metrics: dict[str, Any]) -> float:
    totals = [metrics["per_field"][field]["total"] for field in FREE_FIELDS]
    exact = [metrics["per_field"][field]["exact"] for field in FREE_FIELDS]
    total = sum(totals)
    return sum(exact) / total * 100 if total else 0.0


def _condition(
    source_corpus: dict[str, dict[str, Any]],
    transform: Any,
) -> dict[str, Any]:
    corpus = {
        stem: {**item, "raw_text": transform(item["raw_text"])}
        for stem, item in source_corpus.items()
    }
    rows = _candidate_rows(corpus)
    metrics = aggregate_rows(rows)
    return {
        "metrics": metrics,
        "free_fields_exact_pct": round(_free_macro(metrics), 2),
        "changed_documents": sum(
            int(
                row["fields"]["nama_kegiatan_sertifikasi"]
                != source_corpus[row["stem"]]["v2_fields"]["nama_kegiatan_sertifikasi"]
                or row["fields"]["penyelenggara_kegiatan"]
                != source_corpus[row["stem"]]["v2_fields"]["penyelenggara_kegiatan"]
            )
            for row in rows
        ),
    }


def _summary(payload: dict[str, Any]) -> str:
    clean = payload["conditions"]["clean"]
    lines = [
        f"# {payload['experiment_id']}",
        "",
        "- Scope: postprocessor title + organizer; raw V2 fields tetap fixed.",
        "- Dokumen: `74`; panggilan model baru: `0`; token/cost baru: `0`.",
        "- Ini bukan re-run Gemini OOD penuh; kontrol penuh V2 ada pada proof sumber.",
        "",
        "|Kondisi|All-cells exact|Framework exact|Free-field exact|Delta free vs clean|Changed docs|Gate|",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name, condition in payload["conditions"].items():
        metrics = condition["metrics"]
        delta = condition["free_fields_exact_pct"] - clean["free_fields_exact_pct"]
        gate = condition["gate"]
        lines.append(
            f"|{name}|{metrics['all_cells_6f']['exact_pct']}%|"
            f"{metrics['framework_5f']['exact_pct']}%|"
            f"{condition['free_fields_exact_pct']}%|{delta:+.2f}pt|"
            f"{condition['changed_documents']}|{'PASS' if gate else 'FAIL'}|"
        )
    lines.extend(
        [
            "",
            "## Interpretasi",
            "",
            "- Mutation dan noise diuji terhadap parser boundary saja; field V2 yang tidak disentuh tidak dihitung sebagai bukti ketahanan model.",
            "- Gate free-field mutation/noise 10% memakai batas penurunan maksimal 2 poin.",
            "- Noise 25% dan 50% dicatat untuk observasi; silent-error coverage tidak dapat dinilai tanpa re-run model dan review policy penuh.",
        ]
    )
    return "\n".join(lines) + "\n"

def run(
    output_dir: Path,
    *,
    campaign_id: str = "EXP-PROD-V2-CAMPAIGN-001",
    parent_experiment_id: str | None = None,
    commit: str | None = None,
) -> dict[str, Any]:
    ensure_fresh_directory(output_dir)
    source = load_cached_corpus()
    conditions: dict[str, dict[str, Any]] = {
        "clean": _condition(source, lambda text: text),
        "template_mutation": _condition(source, _mutate),
    }
    for level in NOISE_LEVELS:
        rng = random.Random(42)
        conditions[f"ocr_noise_{int(level * 100)}"] = _condition(
            source, lambda text, level=level, rng=rng: _inject_noise(text, level, rng)
        )
    clean_free = conditions["clean"]["free_fields_exact_pct"]
    for name, condition in conditions.items():
        drop = condition["free_fields_exact_pct"] - clean_free
        condition["delta_free_vs_clean_pct"] = round(drop, 2)
        if name in {"clean", "template_mutation", "ocr_noise_10"}:
            condition["gate"] = name == "clean" or drop >= -2.0
        else:
            condition["gate"] = True
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "experiment_id": output_dir.name,
        "campaign_id": campaign_id,
        "parent_experiment_id": parent_experiment_id,
        "source": "docs/experiments/EXP-PROD-V2-SCOPE-001/run_full_74",
        "gt_csv": "Ground_Truth_Sertifikat_v9.csv",
        "matcher": "tests/matchers.py",
        "model_calls": 0,
        "token_accounting": {
            "prompt_tokens": 0,
            "candidates_tokens": 0,
            "cached_tokens": 0,
            "thoughts_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "cost_idr": 0.0,
            "web_search_queries": [],
        },
        "conditions": conditions,
        "all_gates_pass": all(condition["gate"] for condition in conditions.values()),
        "status": "STAGING_ONLY",
    }
    write_json(output_dir / "results.json", payload)
    manifest = {
        "campaign_id": campaign_id,
        "experiment_id": output_dir.name,
        "parent_experiment_id": parent_experiment_id,
        "related_experiment_ids": [],
        "role": "boundary_only_ood",
        "step": "boundary_ood",
        "status": "STAGING_ONLY",
        "started_at": generated_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "immutable": True,
        "commit": commit,
        "n_documents": 74,
        "production_promotion": False,
        "scope": "boundary_only",
        "source": payload["source"],
    }
    write_json(output_dir / "manifest.json", manifest)
    (output_dir / "summary.md").write_text(_summary(payload), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "docs/experiments/EXP-PROD-V2-OOD-BOUNDARY-001",
    )
    parser.add_argument("--campaign-id", default="EXP-PROD-V2-CAMPAIGN-001")
    parser.add_argument("--parent-experiment-id")
    parser.add_argument("--commit")
    args = parser.parse_args()
    payload = run(
        args.output_dir,
        campaign_id=args.campaign_id,
        parent_experiment_id=args.parent_experiment_id,
        commit=args.commit,
    )
    print(json.dumps({"output_dir": str(args.output_dir), "pass": payload["all_gates_pass"]}))


if __name__ == "__main__":
    main()
