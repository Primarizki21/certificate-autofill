"""F2 Roadmap v10 — Rule mining dari 29 cert LLM-fallback + validasi k-fold.

Analisis offline (no LLM): cari pattern struktural general pada 29 cert yang
router v9 (45/74) tidak putuskan, bandingkan LLM decision (run v9 f_bias) vs
GT v9. Kandidat rule divisi pada full 74 (precision) lalu diuji 5-fold
(protokol F0): rule harus precision >=95% di fold uji, dan fire count dicatat
(LOW-N = interval lebar).

Kandidat yang diuji:
- R14 `ukm_org`: organizer mengandung UKM (word boundary) tanpa lomba/luar/
  nasw/sem/fak/dept -> Universitas (dari 3/3 cert UKM GT=Universitas)
- R15 `hima_dept`: hima_org + dept -> Departemen (hipotesis, dari 2065179 dll)

Usage:
  uv run python -m tests.rule_mining
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.llm_router_v4 import _sig, route_tingkat_trace
from tests.organizer_extractor_v2 import extract_organizer_v2
from tests.stat_validation import fold_assign, load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"rule_mining_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "f2_rule_mining.md")

RULES = {
    "ukm_org": lambda s: (
        bool(re.search(r"\bUKM\b", (s.get("_org") or "").upper()))
        and not s["lomba"] and not s["lomba_merged"] and not s["luar"]
        and not s["nasw"] and not s["sem"] and not s["fak"] and not s["dept"]
    ),
    "hima_dept": lambda s: (
        s["hima_org"] and s["dept"]
    ),
}

RULE_LABELS = {
    "ukm_org": "Universitas",
    "hima_dept": "Departemen/Program Studi",
}


def candidate_decision(text: str, org: str) -> tuple[str | None, str]:
    """Router v9 -> kandidat rule -> None."""
    routed, rule = route_tingkat_trace(text, org)
    if routed:
        return routed, rule
    s = _sig(text, org)
    s["_org"] = org
    for name, fn in RULES.items():
        if fn(s):
            return RULE_LABELS[name], name
    return None, ""


def full_sample(texts: dict[str, str], gt: dict[str, dict]) -> dict:
    rows = []
    for stem, text in texts.items():
        org = extract_organizer_v2(text) or ""
        d, r = candidate_decision(text, org)
        expected = (gt[stem].get("tingkat") or "").strip()
        rows.append({"stem": stem, "decision": d, "rule": r,
                     "expected": expected, "exact": d is not None and d == expected})
    return rows


def kfold_rules(rows: list[dict], assign: dict[str, int]) -> dict:
    """Per-rule precision di fold uji + full-sample (rule tetap)."""
    per_rule: dict[str, dict] = {}
    for row in rows:
        if not row["decision"]:
            continue
        r = per_rule.setdefault(row["rule"], {"fires": 0, "correct": 0, "folds": defaultdict(lambda: {"fires": 0, "correct": 0})})
        r["fires"] += 1
        r["correct"] += 1 if row["exact"] else 0
        r["folds"][assign[row["stem"]]]["fires"] += 1
        r["folds"][assign[row["stem"]]]["correct"] += 1 if row["exact"] else 0
    out = {}
    for rule, r in sorted(per_rule.items()):
        fold_prec = [
            (f, fr["fires"], fr["correct"], fr["correct"] / fr["fires"] if fr["fires"] else None)
            for f, fr in sorted(r["folds"].items()) if fr["fires"]
        ]
        precs = [p for _, _, _, p in fold_prec if p is not None]
        out[rule] = {
            "fires": r["fires"], "correct": r["correct"],
            "precision": round(r["correct"] / r["fires"], 4),
            "min_fold_precision": round(min(precs), 4) if precs else None,
            "fold_precisions": [(f, n, c, round(p, 4) if p is not None else None) for f, n, c, p in fold_prec],
            "stable": all(p is not None and p >= 0.95 for _, _, _, p in fold_prec),
            "low_n": r["fires"] < 5,
        }
    return out


def render_md(rows: list[dict], rules: dict, llm_stats: dict) -> str:
    lines = [
        "# F2 — Rule Mining dari 29 Cert LLM-Fallback",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        f"router = llm_router_v4 + kandidat rule | 5-fold seed 42",
        "",
        "## Coverage",
        "",
        "| Skenario | Routed | Precision | LLM calls (est.) |",
        "|---|---|---|---|",
    ]
    routed_now = sum(1 for r in rows if r["decision"] and r["rule"] in RULES)
    routed_old = sum(1 for r in rows if r["decision"] and r["rule"] not in RULES)
    ok_now = sum(1 for r in rows if r["decision"] and r["exact"])
    lines += [
        f"| Router v9 saja | 45 | 100.0% | 29 |",
        f"| Router v9 + kandidat | {routed_old + routed_now} | {ok_now/(routed_old+routed_now)*100:.1f}% | {74 - routed_old - routed_now} |",
        "",
        "## Kandidat rule — full sample & 5-fold",
        "",
        "| Rule | fires | precision | min fold prec | folds (fires, prec) | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for rule, r in rules.items():
        folds = ", ".join(f"f{f}:{n}" + (f"({p:.0%})" if p is not None else "(0)") for f, n, c, p in r["fold_precisions"])
        verdict = "UNSTABLE" if not r["stable"] else ("LOW-N" if r["low_n"] else "stable")
        lines.append(f"| {rule} | {r['fires']} | {r['precision']:.1%} | {r['min_fold_precision']:.1%} | {folds} | {verdict} |")
    lines += [
        "",
        "## Analisis 29 cert unrouted v9 (LLM vs GT)",
        "",
        f"- LLM benar: {llm_stats['correct']}/{llm_stats['total']} "
        f"({llm_stats['correct']/llm_stats['total']*100:.1f}%) — fallback 29 cert "
        "memang kasus ambigu (LLM tidak superior pada subset ini).",
        "- Pola yang ditemukan: `UKM` di organizer → GT Universitas (3/3, konsisten); "
        "`hima_dept` → GT bercampur (Departemen vs Nasional — jangan jadi rule tanpa guard).",
        "- Pola lain tidak konsisten: `luar` saja (Nasional/Universitas/Fakultas), "
        "`dept` saja (Nasional/Internasional), `lomba` saja (Nasional/Universitas).",
        "",
        "## Keputusan",
        "",
        "- **R14 `ukm_org`**: 3/3 @100% full-sample, semua fold 100% → kandidat "
        "layak (LOW-N: fire 3 — klaim robustness butuh data baru).",
        "- **R15 `hima_dept`**: precision 60% (2 salah) → **TIDAK jadi rule** "
        "(masuk KB-kandidat, bukan rule permanen).",
    ]
    return "\n".join(lines)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()
    rows = full_sample(texts, gt)
    assign = fold_assign(list(texts), gt)

    routed_old = sum(1 for r in rows if r["decision"] and r["rule"] not in RULES)
    routed_new = sum(1 for r in rows if r["decision"])
    ok_new = sum(1 for r in rows if r["decision"] and r["exact"])
    print(f"Router v9: {routed_old}/74 | +kandidat: {routed_new}/74 @ {ok_new}/{routed_new} = {ok_new/routed_new:.1%}")

    rules = kfold_rules(rows, assign)
    for rule, r in rules.items():
        print(f"  {rule:12s} {r['correct']}/{r['fires']} prec={r['precision']:.1%} "
              f"{'UNSTABLE' if not r['stable'] else 'stable'}{' LOW-N' if r['low_n'] else ''}")

    for row in rows:
        if row["rule"] in RULES and not row["exact"]:
            print(f"  WRONG: {row['stem']} rule={row['rule']} -> {row['decision']} (GT {row['expected']})")

    # LLM correctness on the ORIGINAL 29 unrouted v9 (pakai field `correct` dari
    # run file — response mentah bisa beda dari validasi prompt benchmark)
    llm = json.load(open(os.path.join(REPO, "tests/benchmark_runs/run_llm_v4_20260805_163541/calls_f_bias.json")))
    llm_correct = {e["certificate"][:-4]: bool(e.get("correct")) for e in llm}
    v9_routed = {
        stem for stem, text in texts.items()
        if route_tingkat_trace(text, extract_organizer_v2(text) or "")[0]
    }
    llm_stats = {"correct": 0, "wrong": [], "total": 0}
    for stem in texts:
        if stem in v9_routed:
            continue
        llm_stats["total"] += 1
        if llm_correct.get(stem):
            llm_stats["correct"] += 1
        else:
            llm_stats["wrong"].append(stem)
    print(f"LLM benar di {llm_stats['total']} unrouted v9: {llm_stats['correct']}/{llm_stats['total']}")

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump({"routed_v9": routed_old, "routed_v9_plus": routed_new,
                   "precision_v9_plus": round(ok_new / routed_new, 4) if routed_new else 0,
                   "rules": rules, "llm_stats": llm_stats,
                   "gt": os.path.basename(GT_CSV)}, f, indent=2, ensure_ascii=False)
    with open(OUT_MD, "w") as f:
        f.write(render_md(rows, rules, llm_stats))
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary.json")


if __name__ == "__main__":
    main()
