"""Unit tests for V2 Scope-Aware four-layer proof assembly."""

from __future__ import annotations

import random

from tests.benchmark_prompt_opt_v2_v3 import (
    V2_BASELINE_SYSTEM_INSTRUCTION,
    V2_BASELINE_USER_PROMPT_TEMPLATE,
)
from tests.ood_probe import inject_noise
from tests.validate_gemini_4layer import run_anti_hardcoding_audit
from tests.validate_v2_production_equivalent import (
    MUTATION_DIAGNOSTIC_FIELDS,
    MUTATION_GATE_FIELDS,
    _accuracy,
    _token_rollup,
)


def _row(*, exact_fields: set[str]) -> dict:
    return {
        "evaluation": {
            field_name: {"exact": field_name in exact_fields}
            for field_name in (*MUTATION_DIAGNOSTIC_FIELDS, "penyelenggara_kegiatan")
        }
    }


def test_accuracy_can_measure_uncontaminated_mutation_gate_fields() -> None:
    rows = [_row(exact_fields=set(MUTATION_GATE_FIELDS))]
    assert _accuracy(rows, MUTATION_GATE_FIELDS) == 100.0
    assert _accuracy(rows, MUTATION_DIAGNOSTIC_FIELDS) == 75.0


def test_scope_aware_prompt_has_no_corpus_event_hardcoding() -> None:
    audit = run_anti_hardcoding_audit(
        V2_BASELINE_SYSTEM_INSTRUCTION,
        V2_BASELINE_USER_PROMPT_TEMPLATE,
    )
    assert audit["violations_found"] == []
    assert audit["anti_hardcoding_pass"] is True


def test_noise_injection_is_reproducible_for_same_seed() -> None:
    text = "Universitas Airlangga SEPTEMBER 2024 BEM FTMM"
    first = inject_noise(text, 0.25, random.Random(42))
    second = inject_noise(text, 0.25, random.Random(42))
    assert first == second


def test_noise_injection_preserves_clean_text_at_zero_rate() -> None:
    text = "Teks sertifikat tanpa gangguan"
    assert inject_noise(text, 0.0, random.Random(42)) == text

def test_token_rollup_persists_required_per_call_accounting() -> None:
    rows = [
        {
            "call_meta": {
                "status": "success",
                "prompt_tokens": 10,
                "candidates_tokens": 4,
                "cached_tokens": 1,
                "thoughts_tokens": 2,
                "total_tokens": 16,
                "cost_usd": 0.001,
                "cost_idr": 18.0,
                "calls_count": 1,
                "latency_s": 0.4,
                "web_search_queries": [],
            }
        }
    ]

    rollup = _token_rollup(rows)

    assert rollup["total_calls"] == 1
    assert rollup["total_tokens"] == 16
    assert rollup["total_cost_idr"] == 18.0
    assert rollup["calls_details"][0]["prompt_tokens"] == 10
    assert rollup["calls_details"][0]["thoughts_tokens"] == 2
