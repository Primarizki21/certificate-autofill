"""Unit tests untuk Runner Benchmark EXP-SEARCH-GROUNDING-002."""

import csv
import json
import pytest
from pathlib import Path

from tests.benchmark_forced_search import (
    determine_outcome_category,
    run_benchmark,
    write_prompt_registry,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_manifest_94_fallback_integrity() -> None:
    manifest_path = REPO_ROOT / "docs/experiments/EXP-SEARCH-GROUNDING-002/manifest_94_fallback.csv"
    assert manifest_path.exists(), f"Manifest file missing: {manifest_path}"

    with open(manifest_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 94, f"Expected exactly 94 rows, got {len(rows)}"

    filenames = set(r["nama_file"] for r in rows)
    assert len(filenames) == 94, "Duplicate filenames in manifest!"

    # Verify V2 historical exact count matches baseline 77/94 (81.91%)
    v2_correct = sum(int(r["v2_historical_exact"]) for r in rows)
    assert v2_correct == 77, f"Expected 77 correct in V2 baseline, got {v2_correct}"


def test_outcome_category_logic() -> None:
    # 1. Grounded Categories (Q > 0)
    assert determine_outcome_category("Nasional", "Nasional", "Nasional", 2) == "Keduanya Benar ✅"
    assert determine_outcome_category("Universitas", "Fakultas", "Nasional", 2) == "Keduanya Salah ❌"
    assert determine_outcome_category("Nasional", "Fakultas", "Nasional", 2) == "Search Memperbaiki ✅ (Grounded)"
    assert determine_outcome_category("Internasional", "Nasional", "Nasional", 1) == "Search Memperburuk ❌ (Grounded)"

    # 2. Ungrounded Categories (Q == 0)
    assert determine_outcome_category("Nasional", "Nasional", "Nasional", 0) == "Keduanya Benar ✅ (Ungrounded)"
    assert determine_outcome_category("Universitas", "Fakultas", "Nasional", 0) == "Keduanya Salah ❌ (Ungrounded)"
    assert determine_outcome_category("Nasional", "Fakultas", "Nasional", 0) == "V3 Benar Tanpa Search (Q=0)"
    assert determine_outcome_category("Internasional", "Nasional", "Nasional", 0) == "V3 Salah Tanpa Search (Q=0)"


def test_prompt_registry_fence_balance(tmp_path: Path) -> None:
    out_reg = tmp_path / "PROMPT_REGISTRY.md"
    write_prompt_registry(out_reg, "gemini-3.1-flash-lite")
    assert out_reg.exists()

    content = out_reg.read_text(encoding="utf-8")
    lines = content.splitlines()

    fences_4 = [i + 1 for i, l in enumerate(lines) if l.strip().startswith("````")]
    fences_3 = [i + 1 for i, l in enumerate(lines) if l.strip().startswith("```") and not l.strip().startswith("````")]

    assert len(fences_4) > 0
    assert len(fences_4) % 2 == 0, f"Unbalanced 4-backtick fences: {fences_4}"
    assert len(fences_3) % 2 == 0, f"Unbalanced 3-backtick fences: {fences_3}"


def test_mock_benchmark_execution(tmp_path: Path) -> None:
    out_dir = tmp_path / "mock_test_run"
    summary = run_benchmark(
        output_dir=str(out_dir),
        mock=True,
        limit=5,
    )

    assert summary["metadata"]["mock"] is True
    assert summary["metadata"]["total_documents_evaluated"] == 5

    metrics_json = out_dir / "comparative_metrics.json"
    assert metrics_json.exists()

    details_csv = out_dir / "evaluation_details.csv"
    assert details_csv.exists()

    with open(details_csv, encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    assert len(csv_rows) == 5

    valid_categories = {
        "Keduanya Benar ✅",
        "Keduanya Salah ❌",
        "Search Memperbaiki ✅ (Grounded)",
        "Search Memperburuk ❌ (Grounded)",
        "Keduanya Benar ✅ (Ungrounded)",
        "Keduanya Salah ❌ (Ungrounded)",
        "V3 Benar Tanpa Search (Q=0)",
        "V3 Salah Tanpa Search (Q=0)",
        "Lainnya",
    }

    for r in csv_rows:
        assert r["outcome_category"] in valid_categories, f"Unexpected category: {r['outcome_category']}"
        assert r["grounding_status"] in ["grounded_first_attempt", "grounded_on_retry", "ungrounded_fallback"]
        assert int(r["attempts_count"]) in (1, 2)
