"""Offline router precision eval — no LLM needed.

Runs route_tingkat on all 74 certs (raw_text + phrase_v2 organizer), compares
against GT tingkat. Validates precision of router rules across the WHOLE
corpus (not just the 35 currently routed).

Usage:
  uv run python -m tests.eval_router_offline
"""

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.evaluation_framework import load_csv
from tests.llm_router_v4 import route_tingkat_trace
from tests.llm_extractor import TINGKAT_GT_MAP
from tests.organizer_extractor_v2 import extract_organizer_v2

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSV_PATH = os.path.join(REPO_ROOT, "Ground_Truth_Sertifikat_v8.csv")
TEXTS_DIR = os.path.join(
    REPO_ROOT, "tests", "benchmark_runs", "run_20260728_131835", "extracted_texts"
)


def main():
    rows = load_csv(CSV_PATH)
    stem_to_row = {os.path.splitext(r["nama_file"])[0]: r for r in rows}
    text_files = sorted(f for f in os.listdir(TEXTS_DIR) if f.endswith(".txt"))

    decisions = []
    per_rule = Counter()
    per_rule_ok = Counter()
    for tf in text_files:
        stem = os.path.splitext(tf)[0]
        row = stem_to_row.get(stem)
        if row is None:
            continue
        expected_raw = (row.get("tingkat") or "").strip()
        expected = TINGKAT_GT_MAP.get(expected_raw, expected_raw)
        with open(os.path.join(TEXTS_DIR, tf)) as f:
            text = f.read()
        org = extract_organizer_v2(text)
        routed, rule = route_tingkat_trace(text, org or "")
        decisions.append({
            "stem": stem, "expected": expected, "decision": routed,
            "rule": rule, "exact": routed is not None and routed == expected,
        })
        if routed:
            per_rule[rule] += 1
            if routed == expected:
                per_rule_ok[rule] += 1

    n_routed = sum(1 for d in decisions if d["decision"])
    n_ok = sum(1 for d in decisions if d["exact"])
    print(f"Corpus: {len(text_files)} certs")
    print(f"Routed by rule: {n_routed}/{len(decisions)} | correct: {n_ok}/{n_routed} | precision {n_ok/n_routed:.1%}" if n_routed else "no routes")
    print(f"Would skip LLM: {n_routed} (baseline was 35)")

    print("\nPer-rule:")
    for rule in sorted(per_rule):
        print(f"  {rule:24s} {per_rule_ok[rule]:3d}/{per_rule[rule]:3d}")

    print("\nWrong decisions (would cause regressions):")
    for d in decisions:
        if d["decision"] and not d["exact"]:
            print(f"  {d['stem']}: rule={d['rule']} -> {d['decision']} (GT {d['expected']})")


if __name__ == "__main__":
    main()
