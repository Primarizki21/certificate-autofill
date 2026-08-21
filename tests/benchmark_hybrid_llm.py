"""HYB-LLM — Hybrid + LLM untuk tingkat (26 cert unrouted).

Sama seperti HYB-COMBINED, tapi untuk 26 cert yang router tidak bisa decide,
tingkat ditanyakan ke LLM (Ollama llama3.1:8b).

Alur:
  74 cert → router rules → 48 routed (tingkat langsung)
                        → 26 unrouted → LLM → tingkat dari LLM

Field lain tetap dari HYB-COMBINED:
  - Nama kegiatan: AKT-005 (62.2%)
  - Organizer: ORG-004 (63.5%)
  - Nomor: PROD-002 (76.9%)
  - Tanggal: pipeline (81.8%)

Gate: MACRO ≥ 73.7% (HYB-COMBINED baseline), tingkat ≥ 81.1%

Usage:
  python -m tests.benchmark_hybrid_llm
"""

import json
import os
import sys
import time
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "backend"))

from tests.benchmark_akt2 import eval_corpus
from tests.benchmark_hybrid_combined import offline_hybrid_combined
from tests.benchmark_prod_port import offline_prod
from tests.llm_extractor import build_prompt_tingkat, call_ollama, validate_tingkat, TINGKAT_OPTIONS
from tests.llm_router_v4 import route_tingkat_trace
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts
from tests.matchers import match_field

OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"hyb_llm_{datetime.now().strftime('%Y%m%d_%H%M%S')}")


def offline_hybrid_llm(text: str, known_fields: dict = None) -> dict[str, str]:
    """Pipeline hybrid: offline_prod + AKT-005 + router + LLM fallback untuk tingkat."""
    # Start with offline_hybrid_combined (router + AKT-005)
    fields = offline_hybrid_combined(text)

    # Check if router decided
    organizer_val = fields.get("penyelenggara_kegiatan") or ""
    router_tingkat, rule = route_tingkat_trace(text, organizer_val)

    if not router_tingkat:
        # Router tidak bisa decide → tanya LLM
        if known_fields is None:
            known_fields = {}
        known_fields["nama_kegiatan_sertifikasi"] = fields.get("nama_kegiatan_sertifikasi", "")
        known_fields["penyelenggara_kegiatan"] = organizer_val

        prompt = build_prompt_tingkat(text, known_fields)
        response, usage = call_ollama(prompt)
        llm_tingkat = validate_tingkat(response)

        if llm_tingkat:
            fields["tingkat"] = llm_tingkat
        # else: keep pipeline default (None)

    return fields


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()

    # Baseline = HYB-COMBINED (offline, no LLM)
    base = eval_corpus(texts, gt, offline_hybrid_combined)

    # Run LLM for unrouted certs
    print("=" * 70)
    print("HYB-LLM — Hybrid + LLM Tingkat untuk 26 cert unrouted")
    print("=" * 70)
    print()

    # First, identify unrouted certs
    unrouted_stems = []
    for stem, text in texts.items():
        row = gt.get(stem)
        if not row:
            continue
        organizer = offline_prod(text).get("penyelenggara_kegiatan") or ""
        router_tingkat, rule = route_tingkat_trace(text, organizer)
        if not router_tingkat:
            unrouted_stems.append(stem)

    print(f"Router: {74-len(unrouted_stems)}/74 routed, {len(unrouted_stems)} need LLM")
    print()

    # Run LLM for each unrouted cert
    llm_results = {}
    total_tokens = 0
    total_time = 0
    llm_correct = 0
    llm_wrong = 0

    for i, stem in enumerate(unrouted_stems):
        text = texts[stem]
        row = gt.get(stem, {})
        gt_tingkat = row.get("tingkat", "")

        start = time.time()
        fields = offline_hybrid_llm(text)
        elapsed = time.time() - start

        predicted = fields.get("tingkat", "")
        total_time += elapsed

        # Check if LLM answered
        if predicted:
            # Compare with GT
            from tests.matchers import match_field
            m = match_field(gt_tingkat, predicted, "tingkat")
            if m["exact"]:
                llm_correct += 1
                status = "✅"
            else:
                llm_wrong += 1
                status = "❌"
            print(f"  [{i+1}/{len(unrouted_stems)}] {stem[:45]:<45s} {predicted:<30s} GT={gt_tingkat:<30s} {status} ({elapsed:.1f}s)")
        else:
            print(f"  [{i+1}/{len(unrouted_stems)}] {stem[:45]:<45s} {'NO ANSWER':<30s} GT={gt_tingkat:<30s} ⚠️ ({elapsed:.1f}s)")

        llm_results[stem] = fields

    print()
    print(f"LLM Results: {llm_correct} correct, {llm_wrong} wrong, {len(unrouted_stems)-llm_correct-llm_wrong} no answer")
    print(f"LLM Accuracy: {llm_correct}/{len(unrouted_stems)} = {llm_correct/len(unrouted_stems)*100:.1f}%")
    print(f"Total LLM time: {total_time:.1f}s ({total_time/len(unrouted_stems):.1f}s/cert)")
    print()

    # Now eval full corpus with LLM results
    def hybrid_llm_full(text):
        """Full hybrid with LLM for unrouted certs."""
        stem = None
        for s, t in texts.items():
            if t is text:
                stem = s
                break
        if stem and stem in llm_results:
            return llm_results[stem]
        return offline_hybrid_combined(text)

    hybrid = eval_corpus(texts, gt, hybrid_llm_full)

    # Per-field comparison
    print("=" * 70)
    print("HASIL AKHIR — HYB-COMBINED vs HYB-LLM")
    print("=" * 70)
    print()
    print(f"{'Field':<35s} {'Combined':>10s} {'+LLM':>10s} {'Delta':>8s} Gate")
    print("-" * 70)

    regress_fields = []
    for f in EVAL_FIELDS:
        b = base["per_field"][f]
        h = hybrid["per_field"][f]
        b_pct = b["exact"] / b["total"] * 100 if b["total"] else 0
        h_pct = h["exact"] / h["total"] * 100 if h["total"] else 0
        delta = h_pct - b_pct
        delta_str = f"{delta:+.1f}pt"
        is_regress = h["exact"] < b["exact"]
        gate = "REGRESS ❌" if is_regress else ("PASS ✅" if delta > 0 else "no-regress")
        if is_regress:
            regress_fields.append(f)
        print(f"  {f:<33s} {b_pct:>9.1f}% {h_pct:>9.1f}% {delta_str:>8s} {gate}")

    print("-" * 70)
    b_macro = base["macro_exact"] * 100
    h_macro = hybrid["macro_exact"] * 100
    d_macro = h_macro - b_macro
    print(f"  {'MACRO exact':<33s} {b_macro:>9.1f}% {h_macro:>9.1f}% {d_macro:+.1f}pp")
    b_fuzzy = base["macro_fuzzy"] * 100
    h_fuzzy = hybrid["macro_fuzzy"] * 100
    d_fuzzy = h_fuzzy - b_fuzzy
    print(f"  {'MACRO fuzzy':<33s} {b_fuzzy:>9.1f}% {h_fuzzy:>9.1f}% {d_fuzzy:+.1f}pp")

    # Gate check
    base_macro = 73.7  # HYB-COMBINED baseline
    base_tingkat = 81.1
    h_tingkat = hybrid["per_field"]["tingkat"]["exact"] / hybrid["per_field"]["tingkat"]["total"] * 100
    pass_gate = h_macro >= base_macro - 0.5 and h_tingkat >= base_tingkat - 0.5 and not regress_fields

    print()
    print(f"Target: MACRO ≥ {base_macro}% (HYB-COMBINED), Tingkat ≥ {base_tingkat}%")
    print(f"Tingkat: {base_tingkat}% → {h_tingkat:.1f}%")
    print(f"VERDICT: {'GATE PASS ✅' if pass_gate else 'GATE FAIL ❌'}")
    if regress_fields:
        print(f"Regress fields: {regress_fields}")

    # Save summary
    summary = {
        "baseline_combined": {
            "macro_exact": base["macro_exact"],
            "macro_fuzzy": base["macro_fuzzy"],
            "per_field": {f: {"exact": v["exact"], "fuzzy": v["fuzzy"], "total": v["total"]}
                         for f, v in base["per_field"].items()},
        },
        "hybrid_llm": {
            "macro_exact": hybrid["macro_exact"],
            "macro_fuzzy": hybrid["macro_fuzzy"],
            "per_field": {f: {"exact": v["exact"], "fuzzy": v["fuzzy"], "total": v["total"]}
                         for f, v in hybrid["per_field"].items()},
        },
        "llm_stats": {
            "unrouted": len(unrouted_stems),
            "correct": llm_correct,
            "wrong": llm_wrong,
            "no_answer": len(unrouted_stems) - llm_correct - llm_wrong,
            "accuracy": llm_correct / len(unrouted_stems) if unrouted_stems else 0,
            "total_time_s": total_time,
            "avg_time_s": total_time / len(unrouted_stems) if unrouted_stems else 0,
        },
        "gate": {"pass": pass_gate, "target_macro": base_macro, "target_tingkat": base_tingkat,
                 "regress_fields": regress_fields},
        "gt": "Ground_Truth_Sertifikat_v9.csv",
        "matcher": "v2",
        "model": "llama3.1:8b",
    }
    with open(os.path.join(OUT_DIR, "summary_hybrid_llm.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary: {OUT_DIR}/summary_hybrid_llm.json")


if __name__ == "__main__":
    main()
