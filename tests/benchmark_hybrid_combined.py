"""HYB-COMBINED — Gabungan terbaik dari semua pipeline improvements (0 LLM, offline).

Menggabungkan:
- Tingkat: router rules (v9 ROUTER-002+003, 45/74 routed @100%)
- Nama kegiatan: AKT-005 (v5, 62.2% exact)
- Organizer: ORG-004 canonical format (66.2% exact)
- Nomor: PROD-002 normalization (76.9% exact)
- Tanggal: pipeline baseline (81.8%)
- Semua dari pipeline offline, TANPA LLM

Gate: MACRO > 60.2% (v9 reval baseline), no-regress per field vs best individual.

Usage:
  python -m tests.benchmark_hybrid_combined
"""

import json
import os
import sys
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "backend"))

from tests.benchmark_akt2 import eval_corpus
from tests.benchmark_akt5 import offline_akt5, extract_activity_v5
from tests.benchmark_prod_port import offline_prod
from tests.llm_router_v4 import route_tingkat_trace
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts
from tests.matchers import match_field

OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"hyb_combined_{datetime.now().strftime('%Y%m%d_%H%M%S')}")


def offline_hybrid_combined(text: str) -> dict[str, str]:
    """Pipeline hybrid: offline_prod + AKT-005 activity + router tingkat."""
    # Start with offline_prod (organizer_v2 + normalization)
    fields = offline_prod(text)

    # Override nama_kegiatan with AKT-005 patterns
    new_act = extract_activity_v5(text)
    if new_act:
        fields["nama_kegiatan_sertifikasi"] = new_act

    # Override tingkat with router rules (if router decides)
    organizer_val = fields.get("penyelenggara_kegiatan") or ""
    router_tingkat, rule = route_tingkat_trace(text, organizer_val)
    if router_tingkat:
        fields["tingkat"] = router_tingkat

    return fields


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()

    # Baseline = offline_prod (produksi PROD-002, flag ON)
    base = eval_corpus(texts, gt, offline_prod)
    # Hybrid combined
    hybrid = eval_corpus(texts, gt, offline_hybrid_combined)

    # Per-field comparison
    print("=" * 70)
    print("HYB-COMBINED — Gabungan Terbaik Pipeline Improvements (0 LLM)")
    print("=" * 70)
    print()
    print(f"{'Field':<35s} {'Base':>8s} {'Hybrid':>8s} {'Delta':>8s} Gate")
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
        print(f"  {f:<33s} {b_pct:>7.1f}% {h_pct:>7.1f}% {delta_str:>8s} {gate}")

    print("-" * 70)
    b_macro = base["macro_exact"] * 100
    h_macro = hybrid["macro_exact"] * 100
    d_macro = h_macro - b_macro
    print(f"  {'MACRO exact':<33s} {b_macro:>7.1f}% {h_macro:>7.1f}% {d_macro:+.1f}pp")
    b_fuzzy = base["macro_fuzzy"] * 100
    h_fuzzy = hybrid["macro_fuzzy"] * 100
    d_fuzzy = h_fuzzy - b_fuzzy
    print(f"  {'MACRO fuzzy':<33s} {b_fuzzy:>7.1f}% {h_fuzzy:>7.1f}% {d_fuzzy:+.1f}pp")

    # Router stats
    routed = 0
    unrouted = 0
    for stem, text in texts.items():
        row = gt.get(stem)
        if not row:
            continue
        organizer = offline_prod(text).get("penyelenggara_kegiatan") or ""
        _, rule = route_tingkat_trace(text, organizer)
        if rule:
            routed += 1
        else:
            unrouted += 1

    print()
    print(f"Router: {routed}/{routed+unrouted} routed ({routed/(routed+unrouted)*100:.0f}%)")
    print(f"Unrouted (need LLM): {unrouted}")

    # Gate check
    v9_macro = 60.2  # v9 reval baseline
    pass_gate = h_macro > v9_macro and not regress_fields
    print()
    print(f"Target: MACRO > {v9_macro}% (v9 reval baseline)")
    print(f"VERDICT: {'GATE PASS ✅' if pass_gate else 'GATE FAIL ❌'}")
    if regress_fields:
        print(f"Regress fields: {regress_fields}")

    # Save summary
    summary = {
        "baseline": {
            "macro_exact": base["macro_exact"],
            "macro_fuzzy": base["macro_fuzzy"],
            "per_field": {f: {"exact": v["exact"], "fuzzy": v["fuzzy"], "total": v["total"]}
                         for f, v in base["per_field"].items()},
        },
        "hybrid": {
            "macro_exact": hybrid["macro_exact"],
            "macro_fuzzy": hybrid["macro_fuzzy"],
            "per_field": {f: {"exact": v["exact"], "fuzzy": v["fuzzy"], "total": v["total"]}
                         for f, v in hybrid["per_field"].items()},
        },
        "router": {"routed": routed, "unrouted": unrouted},
        "gate": {"pass": pass_gate, "target_macro": v9_macro, "regress_fields": regress_fields},
        "gt": "Ground_Truth_Sertifikat_v9.csv",
        "matcher": "v2",
    }
    with open(os.path.join(OUT_DIR, "summary_hybrid_combined.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary: {OUT_DIR}/summary_hybrid_combined.json")


if __name__ == "__main__":
    main()
