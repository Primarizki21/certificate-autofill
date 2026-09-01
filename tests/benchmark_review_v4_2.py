"""B3 — Benchmark Review & Safety Net untuk kalibrasi confidence v4.2.

Mengukur efek `calibrate_v4_2_confidence` terhadap flag `field_needs_review`
(pipeline produksi form_mapper, threshold < 0.80) pada 74 sertifikat GT v9:

  - Certificate-level Review Recall : % sertifikat SALAH yang ter-flag review.
  - Review Precision                 : % flag yang benar (cert salah).
  - False Alarm Rate                 : % sertifikat 100% benar yang ter-flag.
  - Weak-field recall                : % error nama_kegiatan / nomor yang ter-flag.

Pembanding: (a) confidence statis v4.2 (tanpa kalibrasi), (b) kalibrasi B3.

Gate B3 (plan):
  - Certificate-level review recall  >= 95.0%
  - Weak field review recall (nama_kegiatan & nomor) >= 88.0%
  - False review rate pada cert 100% exact <= 20.0%

Usage:
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_review_v4_2
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.combined_extractor import apply_combined_v4_2
from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import field_needs_review, map_fields_to_form
from tests.calibrated_confidence_v4_2 import calibrate_v4_2_confidence
from tests.matchers import match_field
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(
    REPO, "tests", "benchmark_runs", f"review_v4_2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
OUT_MD = os.path.join(REPO, "docs", "report", "b3_calibrated_confidence_report.md")

GATE_CERT_RECALL = 95.0
GATE_WEAK_RECALL = 88.0
GATE_FALSE_ALARM = 20.0

WEAK_FIELDS = ("nama_kegiatan_sertifikasi", "nomor_bukti_fisik_nomor_sertifikasi")


def run_pipeline(raw_text: str, calibrated: bool) -> dict:
    extracted = extract_certificate_fields(raw_text)
    extracted = apply_combined_v4_2(extracted, raw_text)
    if calibrated:
        extracted = calibrate_v4_2_confidence(extracted, raw_text)
    mapped = map_fields_to_form(extracted, raw_text, bukti_fisik="Sertifikat")
    return mapped


def cert_eval(mapped: dict, gt_row: dict) -> dict:
    wrong_fields = []
    for f in EVAL_FIELDS:
        gv = (gt_row.get(f) or "").strip()
        if not gv or gv == "-":
            continue
        ev = mapped.get(f) or mapped.get("tingkat") if f == "tingkat" else mapped.get(f)
        # tingkat adalah form field; EVAL_FIELDS menyertakan tingkat
        ev = mapped.get(f)
        pred = (ev.value if ev else None) or ""
        if not match_field(gv, pred, f)["exact"]:
            wrong_fields.append(f)
    return {"wrong": bool(wrong_fields), "wrong_fields": wrong_fields}


def flagged(mapped: dict) -> list[str]:
    flags = []
    for f, ev in mapped.items():
        if ev is None:
            continue
        if field_needs_review(f, ev.value, ev.confidence):
            flags.append(f)
    return flags


def summarize(results: dict) -> dict:
    wrong_certs = [s for s, r in results.items() if r["wrong"]]
    perfect_certs = [s for s, r in results.items() if not r["wrong"]]
    flagged_wrong = [s for s in wrong_certs if results[s]["flags"]]
    flagged_all = [s for s, r in results.items() if r["flags"]]
    flagged_perfect = [s for s in perfect_certs if results[s]["flags"]]

    weak = {}
    for f in WEAK_FIELDS:
        errs = [s for s, r in results.items() if f in r["wrong_fields"]]
        flagged_errs = [s for s in errs if f in results[s]["flags"]]
        weak[f] = {
            "errors": len(errs),
            "flagged": len(flagged_errs),
            "recall_pct": (len(flagged_errs) / len(errs) * 100) if errs else 100.0,
        }

    return {
        "n_certs": len(results),
        "wrong_certs": len(wrong_certs),
        "perfect_certs": len(perfect_certs),
        "flagged_certs": len(flagged_all),
        "cert_review_recall_pct": (len(flagged_wrong) / len(wrong_certs) * 100) if wrong_certs else 100.0,
        "review_precision_pct": (len(flagged_wrong) / len(flagged_all) * 100) if flagged_all else 0.0,
        "false_alarm_rate_pct": (len(flagged_perfect) / len(perfect_certs) * 100) if perfect_certs else 0.0,
        "weak": weak,
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    texts = load_texts()
    gt = load_gt()

    stats = {}
    details = {}
    for label, calibrated in (("v4_2_static", False), ("v4_2_calibrated", True)):
        results = {}
        for stem, text in texts.items():
            try:
                mapped = run_pipeline(text, calibrated)
            except Exception as e:  # noqa: BLE001
                results[stem] = {"wrong": True, "wrong_fields": [], "flags": [], "error": f"{type(e).__name__}: {e}"}
                continue
            ev = cert_eval(mapped, gt.get(stem, {}))
            results[stem] = {**ev, "flags": flagged(mapped)}
        stats[label] = summarize(results)
        details[label] = results

    s0, s1 = stats["v4_2_static"], stats["v4_2_calibrated"]
    gates = {
        "cert_recall_pct": s1["cert_review_recall_pct"],
        "cert_recall_gate": GATE_CERT_RECALL,
        "cert_recall_pass": s1["cert_review_recall_pct"] >= GATE_CERT_RECALL,
        "weak_recall_pct": {
            f: s1["weak"][f]["recall_pct"] for f in WEAK_FIELDS
        },
        "weak_recall_gate": GATE_WEAK_RECALL,
        "weak_recall_pass": all(s1["weak"][f]["recall_pct"] >= GATE_WEAK_RECALL for f in WEAK_FIELDS),
        "false_alarm_pct": s1["false_alarm_rate_pct"],
        "false_alarm_gate": GATE_FALSE_ALARM,
        "false_alarm_pass": s1["false_alarm_rate_pct"] <= GATE_FALSE_ALARM,
    }
    summary = {
        "created": datetime.now().isoformat(),
        "stats": stats,
        "gates": gates,
        "details": details,
        "gt": os.path.basename(GT_CSV),
    }

    with open(os.path.join(OUT_DIR, "summary_review_v4_2.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    lines = [
        "# B3 — Kalibrasi Confidence & Safety Net Review (v4.2, N=74)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | flag via `field_needs_review` (conf < 0.80).",
        "",
        "## Ringkasan",
        "",
        "| Metrik | v4.2 statis | B3 kalibrasi | Gate |",
        "|---|---|---|---|",
        f"| Certificate-level review recall | {s0['cert_review_recall_pct']:.1f}% | **{s1['cert_review_recall_pct']:.1f}%** | >= {GATE_CERT_RECALL:.0f}% |",
        f"| Review precision | {s0['review_precision_pct']:.1f}% | **{s1['review_precision_pct']:.1f}%** | laporan |",
        f"| False alarm rate (cert 100% benar) | {s0['false_alarm_rate_pct']:.1f}% | **{s1['false_alarm_rate_pct']:.1f}%** | <= {GATE_FALSE_ALARM:.0f}% |",
        "",
        "| Weak field recall | v4.2 statis | B3 kalibrasi | Gate |",
        "|---|---|---|---|",
    ]
    for f in WEAK_FIELDS:
        w0, w1 = s0["weak"][f], s1["weak"][f]
        lines.append(
            f"| {f} | {w0['recall_pct']:.1f}% ({w0['flagged']}/{w0['errors']}) | "
            f"**{w1['recall_pct']:.1f}%** ({w1['flagged']}/{w1['errors']}) | >= {GATE_WEAK_RECALL:.0f}% |"
        )
    g = gates
    lines += [
        "",
        f"**Verdict: {'PASS' if all([g['cert_recall_pass'], g['weak_recall_pass'], g['false_alarm_pass']]) else 'FAIL'}**",
        "",
        f"- Cert recall: {'PASS' if g['cert_recall_pass'] else 'FAIL'} ({g['cert_recall_pct']:.1f}% vs {g['cert_recall_gate']:.0f}%)",
        f"- Weak-field recall: {'PASS' if g['weak_recall_pass'] else 'FAIL'} "
        f"({g['weak_recall_pct']} vs {g['weak_recall_gate']:.0f}%)",
        f"- False alarm: {'PASS' if g['false_alarm_pass'] else 'FAIL'} ({g['false_alarm_pct']:.1f}% vs {g['false_alarm_gate']:.0f}%)",
        "",
        "## Trade-off",
        "",
        "Safety net vs biaya review: recall tinggi berarti lebih banyak cert di-flag",
        "untuk verifikasi manusia. B3 menurunkan confidence hanya pada pola lemah",
        "(literal corpus 0.55, repair OCR 0.78, single-date 0.75, disambig 0.84)",
        "— nilai interval eksplisit & router base tetap 0.95+/0.98.",
        "",
    ]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines))

    print(f"cert recall:   static {s0['cert_review_recall_pct']:.1f}% -> B3 {s1['cert_review_recall_pct']:.1f}% (gate >= {GATE_CERT_RECALL:.0f}%)")
    print(f"weak recall:   static { {f: s0['weak'][f]['recall_pct'] for f in WEAK_FIELDS} } -> B3 { {f: s1['weak'][f]['recall_pct'] for f in WEAK_FIELDS} }")
    print(f"false alarm:   static {s0['false_alarm_rate_pct']:.1f}% -> B3 {s1['false_alarm_rate_pct']:.1f}% (gate <= {GATE_FALSE_ALARM:.0f}%)")
    print(f"precision:     static {s0['review_precision_pct']:.1f}% -> B3 {s1['review_precision_pct']:.1f}%")
    print(f"VERDICT: {'PASS' if all([g['cert_recall_pass'], g['weak_recall_pass'], g['false_alarm_pass']]) else 'FAIL'}")
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_review_v4_2.json")


if __name__ == "__main__":
    main()
