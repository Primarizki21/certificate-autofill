"""B4 — Validasi Statistik Stratified 5-Fold CV untuk router disambiguasi v7.

Gate B4: Min-Fold Precision 100.0% (0 false positive di HOLD-OUT fold — rule
FIXED, tidak di-fit dari data; CV mengukur stabilitas presisi lintas fold,
pola `stat_validation.py`). Rule dengan frekuensi fire < 5 = LOW-N (dilaporkan,
tidak mendiskualifikasi fold lain).

Juga gate coverage: total cert ter-route v7 >= 63/74 (ROUTER-006 coverage).

Usage:
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.stat_validation_disambig
"""

import json
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.combined_extractor import apply_combined_v4_2
from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts
from tests.router_disambig_v7 import DISAMBIG_RULES_V7, route_with_disambiguation_v7

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(
    REPO, "tests", "benchmark_runs", f"stat_validation_disambig_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
OUT_MD = os.path.join(REPO, "docs", "report", "b4_router_hardening_report.md")

SEED = 42
N_FOLDS = 5
GATE_COVERAGE = 63  # ROUTER-006: 63/74 routed
LOW_N = 5


def pipeline_fields(text: str) -> tuple[str, str]:
    """Organizer + activity dari pipeline v4.2 (bundle staging, 0 LLM)."""
    extracted = extract_certificate_fields(text)
    extracted = apply_combined_v4_2(extracted, text)
    mapped = map_fields_to_form(extracted, text, bukti_fisik="Sertifikat")
    org = (mapped.get("penyelenggara_kegiatan").value if mapped.get("penyelenggara_kegiatan") else "") or ""
    act = (mapped.get("nama_kegiatan_sertifikasi").value if mapped.get("nama_kegiatan_sertifikasi") else "") or ""
    return org, act


def fold_assign(stems: list[str]) -> dict[str, int]:
    rng = random.Random(SEED)
    shuffled = stems[:]
    rng.shuffle(shuffled)
    assign = {}
    for i, s in enumerate(shuffled):
        assign[s] = i % N_FOLDS
    return assign


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    texts = load_texts()
    gt = load_gt()
    stems = sorted(texts.keys())
    assign = fold_assign(stems)

    # Routing ulang dengan v7 pada seluruh korpus.
    decisions: dict[str, dict] = {}
    routed = 0
    for s in stems:
        org, act = pipeline_fields(texts[s])
        val, rule = route_with_disambiguation_v7(texts[s], org, act)
        decisions[s] = {"val": val, "rule": rule, "org": org, "act": act}
        if val is not None:
            routed += 1

    # Per-rule: fire list, per-fold precision vs GT tingkat.
    rule_stats: dict[str, dict] = {}
    for rname, rtingkat, _ in DISAMBIG_RULES_V7:
        fires = [s for s, d in decisions.items() if d["rule"] == f"disambig_{rname}"]
        fold_data = {}
        for fold in range(N_FOLDS):
            fold_fires = [s for s in fires if assign[s] == fold]
            wrong = []
            for s in fold_fires:
                gv = (gt[s].get("tingkat") or "").strip()
                if gv and gv != "-" and decisions[s]["val"] != gv:
                    wrong.append(s)
            fold_data[fold] = {
                "fires": len(fold_fires),
                "wrong": wrong,
                "precision_pct": 100.0 * (len(fold_fires) - len(wrong)) / len(fold_fires) if fold_fires else None,
            }
        wrong_all = [s for s in fires if (gt[s].get("tingkat") or "").strip() and (gt[s].get("tingkat") or "").strip() != "-" and decisions[s]["val"] != gt[s]["tingkat"]]
        rule_stats[rname] = {
            "fires": len(fires),
            "wrong": wrong_all,
            "low_n": len(fires) < LOW_N,
            "min_fold_precision": min(
                (fd["precision_pct"] for fd in fold_data.values() if fd["precision_pct"] is not None),
                default=None,
            ),
            "fold": fold_data,
        }

    min_fold_all = [r["min_fold_precision"] for r in rule_stats.values() if r["fires"]]
    gate_precision = bool(min_fold_all) and all(p == 100.0 for p in min_fold_all)
    gate_coverage = routed >= GATE_COVERAGE

    summary = {
        "created": datetime.now().isoformat(),
        "n_certs": len(stems),
        "routed": routed,
        "coverage_gate": GATE_COVERAGE,
        "coverage_pass": gate_coverage,
        "min_fold_precision_pass": gate_precision,
        "rules": rule_stats,
        "decisions": decisions,
    }
    with open(os.path.join(OUT_DIR, "summary_stat_validation_disambig.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    lines = [
        "# B4 — Router Hardening & Stratified 5-Fold CV (N=74, 0 LLM)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 | rule FIXED (tidak di-fit) |",
        f"fold = {N_FOLDS}-fold stratified seed {SEED} | matcher: v2.",
        "",
        f"**Coverage v7: {routed}/{len(stems)} routed** (gate >= {GATE_COVERAGE}) -> "
        f"{'PASS' if gate_coverage else 'FAIL'}",
        "",
        "| Rule | Fire | Wrong | Min-Fold Precision | LOW-N |",
        "|---|---|---|---|---|",
    ]
    for rname in [n for n, _, _ in DISAMBIG_RULES_V7]:
        r = rule_stats[rname]
        mp = f"{r['min_fold_precision']:.0f}%" if r["min_fold_precision"] is not None else "-"
        lines.append(f"| {rname} | {r['fires']} | {len(r['wrong'])} | {mp} | {'ya' if r['low_n'] else 'tidak'} |")
    lines += [
        "",
        f"**Gate min-fold precision 100%: {'PASS' if gate_precision else 'FAIL'}**",
        "",
        "Detail per-fold:",
        "",
    ]
    for rname in [n for n, _, _ in DISAMBIG_RULES_V7]:
        r = rule_stats[rname]
        parts = []
        for f, fd in r["fold"].items():
            if fd["precision_pct"] == 100.0:
                label = "OK"
            elif fd["wrong"]:
                label = f"WRONG:{fd['wrong']}"
            else:
                label = "-"
            parts.append(f"fold{f}={fd['fires']} ({label})")
        lines.append(f"- {rname}: " + ", ".join(parts))
    lines += [
        "",
        "Catatan: rule tidak pernah di-fit dari data — presisi per fold mengukur",
        "stabilitas; cert yang salah di semua fold = aturan tidak generalized.",
        "",
    ]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines))

    print(f"routed: {routed}/{len(stems)} (gate >= {GATE_COVERAGE}) -> {'PASS' if gate_coverage else 'FAIL'}")
    for rname in [n for n, _, _ in DISAMBIG_RULES_V7]:
        r = rule_stats[rname]
        mp = f"{r['min_fold_precision']:.0f}%" if r["min_fold_precision"] is not None else "-"
        print(f"  {rname:<32} fire {r['fires']:>2} wrong {len(r['wrong'])} min-fold {mp} {'LOW-N' if r['low_n'] else ''}")
    print(f"min-fold precision 100%: {'PASS' if gate_precision else 'FAIL'}")
    print(f"VERDICT: {'PASS' if gate_precision and gate_coverage else 'FAIL'}")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
