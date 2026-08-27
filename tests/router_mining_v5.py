"""ROUTER-005: Mining Sinyal & Router Expansion pada 24 Sertifikat Unrouted.

Mengeksplorasi sinyal bersih dari:
1. clean_organizer (organizer_v4 via normalize_organizer)
2. clean_activity (activity_v5 via extract_activity)
3. signer / contextual tokens pada raw_text

Validasi: 5-fold cross validation (fold_assign dari tests.stat_validation).
Gates:
- Full sample precision == 100.0% (0 false positive)
- Min-fold precision == 100.0%
- Coverage delta >= +2 certs (LLM calls <= 22)
- 0 regresi pada 50 certs routed baseline

Usage:
    uv run python -m tests.router_mining_v5
"""

import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.activity_extractor import extract_activity
from app.services.organizer_normalize import normalize_organizer
from app.services.organizer_v2 import extract_organizer_v2
from app.services.tingkat_router import _sig, route_tingkat_trace
from tests.ood_probe import load_gt, load_texts
from tests.stat_validation import fold_assign

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"router_mining_v5_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "router_expansion_v5.md")


def inspect_unrouted(texts: dict[str, str], gt: dict[str, dict]) -> list[dict]:
    """Ekstrak detail lengkap 24 certs yang unrouted."""
    unrouted_rows = []
    for stem, text in texts.items():
        org = normalize_organizer(extract_organizer_v2(text), text) or ""
        act = extract_activity(text) or ""
        routed, rule = route_tingkat_trace(text, org)
        gt_tingkat = (gt[stem].get("tingkat") or "").strip()
        s = _sig(text, org)
        s["_org"] = org
        s["_act"] = act

        if not routed:
            unrouted_rows.append({
                "stem": stem,
                "gt_tingkat": gt_tingkat,
                "clean_organizer": org,
                "clean_activity": act,
                "sig": s,
                "raw_snippet": text[:300].replace("\n", " "),
            })
    return unrouted_rows


def evaluate_candidates(texts: dict[str, str], gt: dict[str, dict], candidates: dict) -> dict:
    """Evaluasi rule kandidat terhadap 74 certs & 5-fold CV."""
    assign = fold_assign(list(texts.keys()), gt)
    results = {}

    for cand_name, (cand_fn, cand_target) in candidates.items():
        firings = []
        full_correct = 0
        full_wrong = 0
        fold_counts = {i: {"correct": 0, "wrong": 0, "total": 0} for i in range(5)}

        for stem, text in texts.items():
            org = normalize_organizer(extract_organizer_v2(text), text) or ""
            act = extract_activity(text) or ""
            base_routed, base_rule = route_tingkat_trace(text, org)
            gt_tingkat = (gt[stem].get("tingkat") or "").strip()

            # Rule kandidat hanya dievaluasi pada unrouted atau dicek vs base
            s = _sig(text, org)
            s["_org"] = org
            s["_act"] = act
            s["_text"] = text

            fired = cand_fn(s)
            if fired:
                f_fold = assign.get(stem, 0)
                is_correct = (cand_target == gt_tingkat)
                firings.append({
                    "stem": stem,
                    "gt": gt_tingkat,
                    "target": cand_target,
                    "correct": is_correct,
                    "base_routed": base_routed,
                    "base_rule": base_rule,
                    "fold": f_fold,
                })
                if is_correct:
                    full_correct += 1
                    fold_counts[f_fold]["correct"] += 1
                else:
                    full_wrong += 1
                    fold_counts[f_fold]["wrong"] += 1
                fold_counts[f_fold]["total"] += 1

        total_fires = full_correct + full_wrong
        prec = (full_correct / total_fires * 100) if total_fires else 0.0
        min_fold_prec = 100.0
        for f, fc in fold_counts.items():
            if fc["total"] > 0:
                f_p = fc["correct"] / fc["total"] * 100
                if f_p < min_fold_prec:
                    min_fold_prec = f_p

        # Cek new coverage (hanya unrouted di base)
        new_fires = [f for f in firings if not f["base_routed"]]
        new_correct = sum(1 for f in new_fires if f["correct"])
        new_wrong = sum(1 for f in new_fires if not f["correct"])

        results[cand_name] = {
            "target": cand_target,
            "total_firings": total_fires,
            "full_correct": full_correct,
            "full_wrong": full_wrong,
            "precision": prec,
            "min_fold_prec": min_fold_prec,
            "new_firings_count": len(new_fires),
            "new_correct": new_correct,
            "new_wrong": new_wrong,
            "firings": firings,
            "fold_counts": fold_counts,
            "gate_pass": (prec == 100.0 and min_fold_prec == 100.0 and len(new_fires) >= 2 and new_wrong == 0),
        }

    return results


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()

    unrouted = inspect_unrouted(texts, gt)
    print("=" * 80)
    print(f"ROUTER-005: 24 UNROUTED CERTIFICATES BREAKDOWN (Total: {len(unrouted)})")
    print("=" * 80)
    for i, r in enumerate(unrouted, 1):
        print(f"{i:2d}. [{r['stem']}] -> GT: {r['gt_tingkat']}")
        print(f"    Clean Org: {r['clean_organizer']!r}")
        print(f"    Clean Act: {r['clean_activity']!r}")
        print(f"    Signals:   lomba={r['sig']['lomba']}, hima={r['sig']['hima']}, dept={r['sig']['dept']}, univ={r['sig']['univ']}, luar={r['sig']['luar']}, fak={r['sig']['fak']}, bem={r['sig']['bem']}, sem={r['sig']['sem']}")
        print("-" * 80)

    # Definisikan pola kandidat rule berdasarkan sinyal
    candidates = {
        # Kandidat 1: PKKMB Activity keyword -> Universitas
        "pkkmb_activity": (
            lambda s: (
                bool(re.search(r"\bPKKMB\b|PENGENALAN KEHIDUPAN KAMPUS", s["_text"].upper()))
                or bool(re.search(r"\bPKKMB\b|PENGENALAN KEHIDUPAN KAMPUS", s["_act"].upper()))
            ),
            "Universitas",
        ),
        # Kandidat 2: Program Studi murni di Organizer (tanpa lomba/luar/nasw) -> Departemen/Program Studi
        "prodi_org_pure": (
            lambda s: (
                bool(re.search(r"PROGRAM STUDI|\bPRODI\b", (s.get("_org") or "").upper()))
                and not s["lomba"] and not s["lomba_merged"] and not s["nasw"] and not s["sem"]
            ),
            "Departemen/Program Studi",
        ),
        # Kandidat 3: HIMA murni internal (tanpa lomba/luar/nasw/sem/univ/fak) -> Departemen/Program Studi
        "hima_pure_internal": (
            lambda s: (
                s["hima_org"]
                and not s["lomba"] and not s["lomba_merged"] and not s["luar"] and not s["nasw"]
                and not s["dept"] and not s["sem"] and not s["fak"] and not s["univ"]
            ),
            "Departemen/Program Studi",
        ),
        # Kandidat 4: IRIS BSO di FTMM (Fakultas)
        "iris_ftmm_bso": (
            lambda s: (
                bool(re.search(r"\bIRIS\b|INTELLIGENT SYSTEM", s["_text"].upper()))
                and bool(re.search(r"FTMM|ADVANCED TECHNOLOGY", s["_text"].upper()))
                and not s["lomba"] and not s["nasw"]
            ),
            "Fakultas",
        ),
        # Kandidat 5: BEM FTMM internal (tanpa lomba/luar/nasw/sem) -> Fakultas
        "bem_ftmm_internal": (
            lambda s: (
                bool(re.search(r"BEM\s*FTMM", (s.get("_org") or "").upper()))
                and not s["lomba"] and not s["lomba_merged"] and not s["nasw"]
            ),
            "Fakultas",
        ),
        # Kandidat 6: Signer Dekan internal (tanpa lomba/luar/nasw/univ/dept/hima) -> Fakultas
        "dekan_signer_internal": (
            lambda s: (
                bool(re.search(r"\bDEKAN\b|\bFAKULTAS\b|\bFTMM\b", s["_text"].upper()))
                and not s["lomba"] and not s["lomba_merged"] and not s["nasw"]
                and not s["luar"] and not s["univ"] and not s["dept"] and not s["hima"]
            ),
            "Fakultas",
        ),
        # Kandidat 7: External platform (Dicoding, Kemendikbud, AIESEC) -> Nasional
        "external_platform": (
            lambda s: (
                bool(re.search(r"AIESEC|DICODING|COURSERA|KOMINFO|KEMENDIKBUD", s["_text"].upper()))
                and not s["fak"] and not s["dept"]
            ),
            "Nasional",
        ),
    }

    eval_res = evaluate_candidates(texts, gt, candidates)

    print("\n" + "=" * 80)
    print("ROUTER-005: CANDIDATE RULES 5-FOLD CV EVALUATION")
    print("=" * 80)
    for cname, cdata in eval_res.items():
        print(f"Candidate: {cname} -> Target: {cdata['target']}")
        print(f"  Full Fired:  {cdata['total_firings']} (Correct: {cdata['full_correct']}, Wrong: {cdata['full_wrong']}) -> Prec: {cdata['precision']:.1f}%")
        print(f"  Min Fold:    {cdata['min_fold_prec']:.1f}%")
        print(f"  New Unrouted:{cdata['new_firings_count']} (New Correct: {cdata['new_correct']}, New Wrong: {cdata['new_wrong']})")
        print(f"  Gate Status: {'PASS' if cdata['gate_pass'] else 'FAIL'}")
        if cdata["full_wrong"] > 0:
            print("  False Positives:")
            for f in cdata["firings"]:
                if not f["correct"]:
                    print(f"    - {f['stem']}: got {f['target']}, expected {f['gt']}")
        print("-" * 80)

    # Save summary
    with open(os.path.join(OUT_DIR, "summary_router_v5.json"), "w") as f:
        json.dump({k: {k2: v2 for k2, v2 in v.items() if k2 != "firings"} for k, v in eval_res.items()}, f, indent=2)


if __name__ == "__main__":
    main()
