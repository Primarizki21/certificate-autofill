"""Offline organizer eval — no LLM needed.

Compares organizer extraction variants (hybrid / phrase_v2) against GT
`penyelenggara_kegiatan` on the 74-text corpus. Prints exact/fuzzy per variant
plus per-cert mismatches for taxonomy analysis.

'hybrid' = combine_hybrid(NER_pp + regex) = the production baseline (16.2%).
'phrase_v2' = extract_organizer_v2 override (experiment).

Usage:
  uv run python -m tests.eval_organizer_offline
  uv run python -m tests.eval_organizer_offline --limit 10
  uv run python -m tests.eval_organizer_offline --no-ner   (skip hybrid)
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.field_extractor import extract_certificate_fields, extract_organizer, ExtractedValue
from tests.evaluation_framework import load_csv, match_field
from tests.organizer_extractor_v2 import extract_organizer_v2
from tests.benchmark_hybrid import combine_hybrid

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSV_PATH = os.path.join(REPO_ROOT, "Ground_Truth_Sertifikat_v8.csv")
TEXTS_DIR = os.path.join(
    REPO_ROOT, "tests", "benchmark_runs", "run_20260728_131835", "extracted_texts"
)


def _match(actual, expected):
    return match_field(expected, actual, "penyelenggara_kegiatan")


def main(limit=None, use_ner=True):
    rows = load_csv(CSV_PATH)
    stem_to_row = {os.path.splitext(r["nama_file"])[0]: r for r in rows}
    text_files = sorted(f for f in os.listdir(TEXTS_DIR) if f.endswith(".txt"))
    if limit:
        text_files = text_files[:limit]

    ner_pipe = None
    if use_ner:
        from tests.ner_extractor import load_ner_model, extract_entities, normalize_for_ner
        from tests.ner_to_fields import map_entities_to_fields
        from tests.post_processors import filter_signer_roles
        ner_pipe = load_ner_model()

    per = {"hybrid": Counter(), "phrase_v2": Counter()}
    mismatches = []
    for tf in text_files:
        stem = os.path.splitext(tf)[0]
        row = stem_to_row.get(stem)
        if row is None:
            continue
        expected = (row.get("penyelenggara_kegiatan") or "").strip()
        with open(os.path.join(TEXTS_DIR, tf)) as f:
            text = f.read()

        org_hybrid = None
        if use_ner:
            try:
                regex_fields = extract_certificate_fields(text)
                entities = extract_entities(text, ner_pipe)
                filtered = filter_signer_roles(entities, text)
                ner_pp = map_entities_to_fields(filtered, full_text=normalize_for_ner(text))
                hybrid = combine_hybrid(ner_pp, regex_fields)
                ev = hybrid.get("penyelenggara_kegiatan")
                org_hybrid = ev.value if ev else None
            except Exception:
                org_hybrid = None
        org_v2 = extract_organizer_v2(text)

        for variant, org in (("hybrid", org_hybrid), ("phrase_v2", org_v2)):
            m = _match(org, expected)
            per[variant]["total"] += 1
            per[variant]["exact"] += 1 if m["exact"] else 0
            per[variant]["fuzzy"] += 1 if m["fuzzy"] else 0
        if org_v2 != expected:
            m = _match(org_v2, expected)
            mismatches.append((stem, expected, org_v2, "EXACT" if not m["exact"] else "fuzzy-only"))

    print(f"Corpus: {len(text_files)} certs, GT rows {len(rows)} (NER={'on' if use_ner else 'off'})\n")
    print(f"{'variant':10s} {'exact':>8s} {'fuzzy':>8s} {'n':>4s}")
    for variant, c in per.items():
        n = c["total"]
        print(f"{variant:10s} {c['exact']/n*100:7.1f}% {c['fuzzy']/n*100:7.1f}% {n:4d}")

    print(f"\nNon-exact phrase_v2: {len(mismatches)}")
    for stem, exp, act, kind in sorted(mismatches):
        print(f"  [{kind}] {stem}")
        print(f"    GT: {exp}")
        print(f"    v2: {act}")

    _save_run(per)


def _save_run(per: dict):
    """Write a benchmark_runs entry so runs_summary.md can index the offline eval."""
    runs_root = os.path.join(os.path.dirname(__file__), "benchmark_runs")
    run_dir = os.path.join(runs_root, f"organizer_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(run_dir, exist_ok=True)
    summary = {}
    for variant, c in per.items():
        n = c["total"]
        summary[variant] = {
            "total": n,
            "exact": c["exact"],
            "fuzzy": c["fuzzy"],
            "exact_acc": round(c["exact"] / n, 4) if n else 0,
            "fuzzy_acc": round(c["fuzzy"] / n, 4) if n else 0,
        }
    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)
    with open(os.path.join(run_dir, "config.json"), "w") as f:
        json.dump({
            "kind": "organizer_offline",
            "gt_version": os.path.basename(CSV_PATH),
            "n_certs": 74,
            "csv_path": CSV_PATH,
            "texts_dir": TEXTS_DIR,
        }, f, indent=2, default=str)
    print(f"\nSaved: {run_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-ner", action="store_true")
    args = parser.parse_args()
    main(limit=args.limit, use_ner=not args.no_ner)
