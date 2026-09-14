"""Automated verifier for EXP-SEARCH-GROUNDING-002 artifacts, metrics, and arithmetic."""

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = REPO_ROOT / "docs/experiments/EXP-SEARCH-GROUNDING-002/run_full_94"
MANIFEST_PATH = REPO_ROOT / "docs/experiments/EXP-SEARCH-GROUNDING-002/manifest_94_fallback.csv"
CHECKPOINT_PATH = RUN_DIR / "checkpoint_forced_search.jsonl"
CSV_PATH = RUN_DIR / "evaluation_details.csv"
METRICS_PATH = RUN_DIR / "comparative_metrics.json"
SUMMARY_MD_PATH = RUN_DIR / "comparative_summary.md"


def test_verify_exp_search_grounding_002_artifacts() -> None:
    if not MANIFEST_PATH.exists() or not CHECKPOINT_PATH.exists():
        pytest.skip("Local untracked artifacts for EXP-SEARCH-GROUNDING-002 not present in this workspace.")

    assert CSV_PATH.exists(), f"Missing CSV: {CSV_PATH}"
    assert METRICS_PATH.exists(), f"Missing metrics: {METRICS_PATH}"
    assert SUMMARY_MD_PATH.exists(), f"Missing summary: {SUMMARY_MD_PATH}"

    # 1. Manifest
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest_rows = list(csv.DictReader(f))
    assert len(manifest_rows) == 94
    manifest_files = [r["nama_file"] for r in manifest_rows]
    assert len(set(manifest_files)) == 94

    # 2. Checkpoint JSONL
    with open(CHECKPOINT_PATH, encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]
    assert len(records) == 94

    cp_files = [r["nama_file"] for r in records]
    assert cp_files == manifest_files, "Checkpoint order must match manifest!"

    # 3. CSV
    with open(CSV_PATH, encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    assert len(csv_rows) == 94

    # 4. Metrics JSON
    with open(METRICS_PATH, encoding="utf-8") as f:
        metrics = json.load(f)

    meta = metrics["metadata"]
    assert meta["experiment_id"] == "EXP-SEARCH-GROUNDING-002"
    assert meta["total_documents_evaluated"] == 94
    assert meta["target_denominator"] == 94
    assert meta["mock"] is False

    acc = metrics["accuracy"]
    assert acc["v2_historical_correct"] == 77
    assert round(acc["v2_historical_tingkat_exact"], 2) == 81.91
    assert acc["v3_forced_search_correct"] == 73
    assert round(acc["v3_forced_search_tingkat_exact"], 2) == 77.66
    assert acc["net_gain_percentage"] == -4.26

    cohorts = metrics["grounding_cohorts"]
    assert cohorts["grounded_count"] == 37
    assert cohorts["ungrounded_count"] == 57
    assert cohorts["grounded_count"] + cohorts["ungrounded_count"] == 94
    assert cohorts["grounded_rate"] == 39.36
    assert cohorts["ungrounded_rate"] == 60.64
    assert cohorts["grounded_v3_accuracy"] == 72.97
    assert cohorts["grounded_v2_accuracy"] == 81.08

    costs = metrics["costs"]
    assert costs["total_queries"] == 69
    assert costs["total_search_fee_idr"] == 17154.09
    assert costs["total_effective_cost_idr"] == 18599.69
    assert costs["total_tokens"] == 161979

    # 5. Arithmetic invariants per record
    for r in records:
        assert r["total_web_queries"] == len(r["web_queries"])
        expected_fee = round(r["total_web_queries"] * 248.61, 2)
        assert r["search_fee_idr"] == expected_fee


if __name__ == "__main__":
    test_verify_exp_search_grounding_002_artifacts()
    print("Verification PASSED! All EXP-SEARCH-GROUNDING-002 artifacts and invariants verified.")
