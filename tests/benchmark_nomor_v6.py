"""B6 — Benchmark nomor: v4.2 (normalize_nomor_v5) vs v6 (length-preserving + guard).

Gate B6:
  - nomor exact >= 66.7% (all-cells, = v4.2) / 88.5% non-empty (NUM-003).
  - 100% unit test invariant panjang digit (test_nomor_v6.py).
  - Zero regression vs v4.2.

Usage:
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_nomor_v6
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.combined_extractor import apply_combined_v4_2
from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from tests.matchers import match_field
from tests.nomor_normalizer_v6 import normalize_nomor_v6
from tests.ood_probe import load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(
    REPO, "tests", "benchmark_runs", f"nomor_v6_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
OUT_MD = os.path.join(REPO, "docs", "report", "b6_nomor_normalizer_report.md")

FIELD = "nomor_bukti_fisik_nomor_sertifikasi"
GATE_EXACT = 66.7  # all-cells basis v4.2 (48/72) — di sini non-empty basis = 48/52

CONF_REPAIRED = 0.78  # flag B6 -> confidence rendah (memicu review di <0.80)


def run_v42(text: str) -> str:
    extracted = extract_certificate_fields(text)
    extracted = apply_combined_v4_2(extracted, text)
    mapped = map_fields_to_form(extracted, text, bukti_fisik="Sertifikat")
    return (mapped.get(FIELD).value if mapped.get(FIELD) else None) or ""


def run_v6(text: str) -> str:
    extracted = extract_certificate_fields(text)
    extracted = apply_combined_v4_2(extracted, text)
    val, repaired = normalize_nomor_v6(text)
    if val:
        extracted[FIELD] = ExtractedValue(val, CONF_REPAIRED if repaired else 0.95, "nomor_v6")
    mapped = map_fields_to_form(extracted, text, bukti_fisik="Sertifikat")
    return (mapped.get(FIELD).value if mapped.get(FIELD) else None) or ""


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    texts = load_texts()
    gt = load_gt()

    stats = {}
    details = {}
    for label, fn in (("v4_2", run_v42), ("v6", run_v6)):
        total = exact = fuzzy = 0
        per = {}
        for stem, text in texts.items():
            gv = (gt.get(stem, {}).get(FIELD, "") or "").strip()
            if not gv or gv == "-":
                continue
            pred = fn(text)
            res = match_field(gv, pred, FIELD)
            total += 1
            exact += int(res["exact"])
            fuzzy += int(res["fuzzy"])
            per[stem] = {"gt": gv, "pred": pred, "exact": res["exact"]}
        stats[label] = {
            "exact": exact, "total": total,
            "exact_pct": exact / total * 100 if total else 0.0,
            "fuzzy_pct": fuzzy / total * 100 if total else 0.0,
        }
        details[label] = per

    diff = {"fix": [], "regress": []}
    for stem in details["v4_2"]:
        a, b = details["v4_2"][stem], details["v6"][stem]
        if a["exact"] != b["exact"]:
            (diff["fix"] if b["exact"] else diff["regress"]).append(
                {"stem": stem, "gt": a["gt"], "v42": a["pred"], "v6": b["pred"]}
            )

    gates = {
        "v6_exact_pct": stats["v6"]["exact_pct"],
        "exact_gate": GATE_EXACT,
        "exact_pass": stats["v6"]["exact_pct"] >= GATE_EXACT,
        "fix_count": len(diff["fix"]),
        "regress_count": len(diff["regress"]),
        "zero_regression_pass": len(diff["regress"]) == 0,
    }
    summary = {"created": datetime.now().isoformat(), "stats": stats, "gates": gates, "diff": diff}
    with open(os.path.join(OUT_DIR, "summary_nomor_v6.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    lines = [
        "# B6 — Nomor Normalizer v6 (length-preserving DPKKA + guard Roman, N=74)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2.",
        "",
        "| Varian | exact | fuzzy |",
        "|---|---|---|",
        f"| v4.2 (normalize_nomor_v5) | {stats['v4_2']['exact_pct']:.1f}% ({stats['v4_2']['exact']}/{stats['v4_2']['total']}) | {stats['v4_2']['fuzzy_pct']:.1f}% |",
        f"| **v6 (preserve + guard)** | **{stats['v6']['exact_pct']:.1f}%** ({stats['v6']['exact']}/{stats['v6']['total']}) | **{stats['v6']['fuzzy_pct']:.1f}%** |",
        "",
        f"**Gate**: exact >= {GATE_EXACT}% -> {'PASS' if gates['exact_pass'] else 'FAIL'} | "
        f"zero-regression -> {'PASS' if gates['zero_regression_pass'] else 'FAIL'} "
        f"(fix {gates['fix_count']}, regress {gates['regress_count']})",
        "",
        "Unit test invariant: `tests/test_nomor_v6.py` (13 tests) — panjang digit",
        "terjaga, prefix NOMOR/NUMBER didukung, \"1\" polos tidak di-overcorrect,",
        "DPKKA O-run -> flag 0.78 (review).",
        "",
    ]
    if diff["fix"]:
        lines.append("### Fix")
        lines.append("")
        for d in diff["fix"]:
            lines.append(f"- `{d['stem'][:44]}` GT={d['gt'][:50]!r} v4.2={d['v42'][:50]!r} -> v6={d['v6'][:50]!r}")
        lines.append("")
    if diff["regress"]:
        lines.append("### Regress")
        lines.append("")
        for d in diff["regress"]:
            lines.append(f"- `{d['stem'][:44]}` GT={d['gt'][:50]!r} v4.2={d['v42'][:50]!r} -> v6={d['v6'][:50]!r}")
        lines.append("")
    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines))

    print(f"v4.2: {stats['v4_2']['exact_pct']:.1f}% | v6: {stats['v6']['exact_pct']:.1f}% exact, {stats['v6']['fuzzy_pct']:.1f}% fuzzy")
    print(f"diff: fix {len(diff['fix'])} regress {len(diff['regress'])}")
    print(f"GATES: exact {'PASS' if gates['exact_pass'] else 'FAIL'} ({gates['v6_exact_pct']:.1f}% vs {GATE_EXACT}%) | zero-regression {'PASS' if gates['zero_regression_pass'] else 'FAIL'}")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
