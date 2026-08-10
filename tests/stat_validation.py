"""F0 Roadmap v10 — Validasi statistik pipeline v9 (N=74).

Dua bagian, keduanya offline (tanpa LLM/OCR):
1. 5-fold router rule validation: precision per-rule di fold uji (rule tetap,
   tidak di-fit ulang) — deteksi rule yang precision-nya kebetulan (overfit).
2. Bootstrap CI (resample 1000x, replacement): per-field exact/fuzzy + MACRO
   dan precision router — interval 95% untuk klaim metrik v9.

Evaluasi = GT v9 + matcher v2 (sama dengan reval_gt_v9.py). Router =
tests.llm_router_v4 (versi benchmark, identik fungsional dengan produksi).
Organizer input router = CURRENT tests.organizer_extractor_v2 (code hari ini,
bukan snapshot organizer run v9 — snapshot tsb 6/74 berbeda & memicu 2 false
rule di 2160238/Primarizki_kim, terbukti artefak).

Usage:
  uv run python -m tests.stat_validation
"""

import csv
import json
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.evaluation_framework import load_csv
from tests.matchers import match_field
from tests.llm_router_v4 import route_tingkat_trace
from tests.organizer_extractor_v2 import extract_organizer_v2

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
RUN_DIR = os.path.join(REPO, "tests", "benchmark_runs", "run_llm_v4_20260805_163541")
TEXTS_DIR = os.path.join(REPO, "tests", "benchmark_runs", "run_20260728_131835", "extracted_texts")
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"stat_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "stat_validation.md")

EVAL_FIELDS = [
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "penyelenggara_kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi",
    "tingkat",
]

SEED = 42
N_BOOT = 1000
N_FOLDS = 5


def load_gt() -> dict[str, dict]:
    return {
        os.path.splitext(r["nama_file"])[0]: r
        for r in load_csv(GT_CSV)
    }


def load_extracted() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = defaultdict(dict)
    with open(os.path.join(RUN_DIR, "extracted_fields.csv"), newline="") as f:
        for row in csv.DictReader(f):
            out[os.path.splitext(row["filename"])[0]][row["field"]] = row.get("value") or ""
    return out


def load_texts() -> dict[str, str]:
    out = {}
    for fn in os.listdir(TEXTS_DIR):
        if fn.endswith(".txt"):
            stem = os.path.splitext(fn)[0]
            with open(os.path.join(TEXTS_DIR, fn), encoding="utf-8", errors="replace") as f:
                out[stem] = f.read()
    return out


def per_cert_field_eval(extracted: dict[str, dict[str, str]], gt: dict[str, dict]) -> dict[str, dict]:
    """Per cert: per-field {exact, fuzzy} — mirror reval_gt_v9 (skip GT kosong)."""
    out = {}
    for stem, fields in extracted.items():
        row = gt.get(stem)
        if row is None:
            continue
        res = {}
        for field in EVAL_FIELDS:
            gv = (row.get(field) or "").strip()
            if not gv or gv == "-":
                continue
            m = match_field(gv, fields.get(field), field)
            res[field] = {"exact": m["exact"], "fuzzy": m["fuzzy"]}
        out[stem] = res
    return out


def router_decisions(texts: dict[str, str], extracted: dict[str, dict[str, str]], gt: dict[str, dict]) -> dict[str, dict]:
    """Recompute router decisions — organizer = CURRENT code, bukan snapshot run."""
    out = {}
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        org = extract_organizer_v2(text) or ""
        decision, rule = route_tingkat_trace(text, org)
        out[stem] = {
            "decision": decision,
            "rule": rule,
            "expected": (row.get("tingkat") or "").strip(),
            "exact": decision is not None and decision == (row.get("tingkat") or "").strip(),
        }
    return out


def fold_assign(stems: list[str], gt: dict[str, dict]) -> dict[str, int]:
    rng = random.Random(SEED)
    by_class: dict[str, list[str]] = defaultdict(list)
    for s in stems:
        by_class[gt[s].get("tingkat", "")].append(s)
    assign: dict[str, int] = {}
    for cls, members in by_class.items():
        rng.shuffle(members)
        for i, s in enumerate(members):
            assign[s] = i % N_FOLDS
    return assign


def macro_stats(cert_evals: dict[str, dict]) -> dict:
    per_field = {f: Counter() for f in EVAL_FIELDS}
    for res in cert_evals.values():
        for f, r in res.items():
            per_field[f]["total"] += 1
            per_field[f]["exact"] += 1 if r["exact"] else 0
            per_field[f]["fuzzy"] += 1 if r["fuzzy"] else 0
    total = exact = fuzzy = 0
    for f in EVAL_FIELDS:
        pf = per_field[f]
        total += pf["total"]
        exact += pf["exact"]
        fuzzy += pf["fuzzy"]
    return {
        "per_field": {f: dict(per_field[f]) for f in EVAL_FIELDS},
        "macro": {"total": total, "exact": exact, "fuzzy": fuzzy},
    }


def bootstrap_ci(cert_evals: dict[str, dict], router: dict[str, dict], n_boot: int = N_BOOT) -> dict:
    """Resample certs (replacement), CI 2.5/97.5 utk MACRO + per-field + router precision."""
    stems = list(cert_evals)
    rng = random.Random(SEED + 1)
    metrics = {
        "macro_exact": [], "macro_fuzzy": [],
        "router_precision": [], "router_coverage": [],
    }
    for f in EVAL_FIELDS:
        metrics[f"exact_{f}"] = []
        metrics[f"fuzzy_{f}"] = []
    for _ in range(n_boot):
        sample = [rng.choice(stems) for _ in stems]
        m = macro_stats({s: cert_evals[s] for s in sample})
        metrics["macro_exact"].append(m["macro"]["exact"] / m["macro"]["total"])
        metrics["macro_fuzzy"].append(m["macro"]["fuzzy"] / m["macro"]["total"])
        for f in EVAL_FIELDS:
            pf = m["per_field"][f]
            n = pf["total"]
            metrics[f"exact_{f}"].append(pf["exact"] / n if n else 0.0)
            metrics[f"fuzzy_{f}"].append(pf["fuzzy"] / n if n else 0.0)
        routed = [s for s in sample if router[s]["decision"]]
        prec = sum(1 for s in routed if router[s]["exact"]) / len(routed) if routed else 0.0
        metrics["router_precision"].append(prec)
        metrics["router_coverage"].append(len(routed) / len(sample))
    out = {}
    for k, vals in metrics.items():
        vals = sorted(vals)
        out[k] = {
            "mean": round(sum(vals) / len(vals), 4),
            "ci95_low": round(vals[int(0.025 * len(vals))], 4),
            "ci95_high": round(vals[int(0.975 * len(vals))], 4),
        }
    return out


def rule_fold_stats(router: dict[str, dict], assign: dict[str, int]) -> dict:
    """Per-rule precision di setiap fold uji + full-sample (fixed rules, no refit)."""
    per_rule: dict[str, dict] = {}
    for s, d in router.items():
        if not d["decision"]:
            continue
        r = per_rule.setdefault(d["rule"], {"fires": 0, "correct": 0, "folds": defaultdict(lambda: {"fires": 0, "correct": 0})})
        r["fires"] += 1
        r["correct"] += 1 if d["exact"] else 0
        r["folds"][assign[s]]["fires"] += 1
        r["folds"][assign[s]]["correct"] += 1 if d["exact"] else 0
    out = {}
    for rule, r in sorted(per_rule.items()):
        fold_prec = []
        for fold in range(N_FOLDS):
            fr = r["folds"][fold]
            if fr["fires"]:
                fold_prec.append((fold, fr["fires"], fr["correct"], fr["correct"] / fr["fires"]))
        prec_full = r["correct"] / r["fires"]
        min_fp = min((p for _, _, _, p in fold_prec), default=1.0)
        out[rule] = {
            "fires": r["fires"],
            "correct": r["correct"],
            "precision": round(prec_full, 4),
            "fold_precisions": [(f, n, c, round(p, 4)) for f, n, c, p in fold_prec],
            "min_fold_precision": round(min_fp, 4),
            "stable": min_fp >= 0.95,
            "low_n": r["fires"] < 5,
        }
    return out


def render_md(ci: dict, rules: dict, fold_summary: dict) -> str:
    lines = [
        "# Stat Validation — Pipeline v9 (N=74)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        f"router = llm_router_v4 (identik produksi) | bootstrap {N_BOOT}x, 5-fold seed {SEED}",
        "",
        "## Bootstrap CI (per-field exact/fuzzy + MACRO, 95%)",
        "",
        "| Metrik | mean | CI95 low | CI95 high |",
        "|---|---|---|---|",
    ]
    labels = {
        "macro_exact": "MACRO exact", "macro_fuzzy": "MACRO fuzzy",
        "router_precision": "Router precision", "router_coverage": "Router coverage",
    }
    for k, v in ci.items():
        if k.startswith("exact_") or k.startswith("fuzzy_"):
            continue
        lines.append(f"| {labels.get(k, k)} | {v['mean']:.1%} | {v['ci95_low']:.1%} | {v['ci95_high']:.1%} |")
    lines.append("")
    lines.append("| Field | exact mean | exact CI95 | fuzzy mean | fuzzy CI95 |")
    lines.append("|---|---|---|---|---|")
    for f in EVAL_FIELDS:
        e, fu = ci[f"exact_{f}"], ci[f"fuzzy_{f}"]
        lines.append(
            f"| {f} | {e['mean']:.1%} | {e['ci95_low']:.1%}-{e['ci95_high']:.1%} "
            f"| {fu['mean']:.1%} | {fu['ci95_low']:.1%}-{fu['ci95_high']:.1%} |"
        )
    lines += [
        "",
        "## Router — 5-fold per-rule precision (rule tetap, uji di fold)",
        "",
        "Klaim full-sample `100% precision` diuji per fold: rule `stable` = min fold "
        "precision ≥95%. Rule `low_n` = fire <5 di full sample (interval lebar, "
        "jangan diandalkan untuk klaim robustness).",
        "",
        "| Rule | fires | precision | min fold prec | folds (fires, prec) | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for rule, r in rules.items():
        folds = ", ".join(f"f{f}:{n}({p:.0%})" for f, n, c, p in r["fold_precisions"])
        verdict = "UNSTABLE" if not r["stable"] else ("LOW-N" if r["low_n"] else "stable")
        lines.append(
            f"| {rule} | {r['fires']} | {r['precision']:.1%} | {r['min_fold_precision']:.1%} "
            f"| {folds} | {verdict} |"
        )
    lines += [
        "",
        "## Fold summary",
        "",
        "| Fold | routed | correct | precision |",
        "|---|---|---|---|",
    ]
    for fold, s in fold_summary.items():
        lines.append(f"| {fold} | {s['routed']} | {s['correct']} | {s['precision']:.1%} |")
    lines += [
        "",
        "## Interpretasi",
        "",
        "- Rule dengan `UNSTABLE`/`LOW-N`: klaim precision-nya hanya kebetulan di 74 "
        "sample — jangan dipromosikan tanpa validasi data baru (gate Fase 2 roadmap).",
        "- CI MACRO 60.2% baseline: batas bawah interval = target minimum no-regress "
        "untuk semua eksperimen berikutnya.",
    ]
    return "\n".join(lines)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    extracted = load_extracted()
    texts = load_texts()
    stems = sorted(set(gt) & set(extracted) & set(texts))
    print(f"Corpus: {len(stems)} certs")

    router = router_decisions(texts, extracted, gt)
    saved = json.load(open(os.path.join(RUN_DIR, "router_decisions.json")))
    saved_by_stem = {e["certificate"][:-4]: e for e in saved}
    mismatches = [
        s for s, d in router.items()
        if s in saved_by_stem and (
            saved_by_stem[s]["decision"] != d["decision"]
            or saved_by_stem[s]["rule"] != d["rule"]
        )
    ]
    routed_now = sum(1 for d in router.values() if d["decision"])
    routed_saved = sum(1 for e in saved if e["decision"])
    print(f"Router recompute (current organizer) vs snapshot run v9: "
          f"{len(router) - len(mismatches)}/{len(router)} identik | routed now {routed_now} vs "
          f"snapshot {routed_saved} | beda: {mismatches[:6]}")
    if mismatches:
        print("  NOTE: snapshot run v9 memakai organizer lama (pre-85f5cc8); "
              "beda router decision = artefak snapshot, bukan code regression.")

    cert_evals = per_cert_field_eval(extracted, gt)
    m = macro_stats(cert_evals)
    print(f"MACRO (reval): {m['macro']['exact']/m['macro']['total']:.4f} exact, "
          f"{m['macro']['fuzzy']/m['macro']['total']:.4f} fuzzy")

    assign = fold_assign(stems, gt)
    rules = rule_fold_stats(router, assign)
    fold_summary = {}
    for fold in range(N_FOLDS):
        test = [s for s in stems if assign[s] == fold]
        routed = [s for s in test if router[s]["decision"]]
        ok = sum(1 for s in routed if router[s]["exact"])
        fold_summary[f"fold{fold}"] = {"n_test": len(test), "routed": len(routed),
                                       "correct": ok, "precision": ok / len(routed) if routed else 0}

    ci = bootstrap_ci(cert_evals, router)

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump({"macro": m, "ci": ci, "rules": rules, "folds": fold_summary,
                   "n_certs": len(stems), "n_boot": N_BOOT, "seed": SEED,
                   "gt": os.path.basename(GT_CSV), "matcher": "v2",
                   "run": os.path.basename(RUN_DIR)}, f, indent=2, ensure_ascii=False)

    md = render_md(ci, rules, fold_summary)
    with open(OUT_MD, "w") as f:
        f.write(md)
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary.json")
    for rule, r in rules.items():
        print(f"  {rule:20s} prec={r['precision']:.1%} minFold={r['min_fold_precision']:.1%} "
              f"{'UNSTABLE' if not r['stable'] else 'stable'}{' LOW-N' if r['low_n'] else ''}")


if __name__ == "__main__":
    main()
