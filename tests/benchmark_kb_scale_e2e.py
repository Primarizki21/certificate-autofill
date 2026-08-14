"""KB-SCALE-005 — Proyeksi akurasi & biaya produksi end-to-end (dengan vs tanpa KB).

SCALE-001 hitung hemat CALLS, belum kualitas akhir. Di sini digabungkan
(di korpus 74, 0 LLM runtime — label = nilai terukur, bukan asumsi):

- routed → router: 100% exact (terukur 45/45)
- non-routed KB hit → entry KB: 97.2% benar (SCALE-001: 136/4835 salah)
- non-routed KB miss → LLM: 59% exact (terukur v9: 17/29)

Biaya: LLM calls x 176 eff tok/cert (v9, terukur) — hemat % biaya.

Grid: N {500, 5000} x skew {70/30, 80/20, 90/10}. Reuse replay_workload utk
dapat saved/miss/wrong per kombinasi.

GATE: (1) akurasi dgn KB >= tanpa KB (no-regress), (2) hemat biaya >= 50%
di 80/20 N=5000.

Usage:
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_kb_scale_e2e
"""

import json
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.benchmark_kb_scale import (CONFIRMS, SEED, TOP_SHARE, alpha_for_skew,
                                      build_keys, replay_workload)
from tests.ood_probe import load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"kb_scale_e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "kb_scale_e2e.md")

ROUTER_ACC = 1.00  # terukur 45/45 routed cert
LLM_ACC = 0.5862   # terukur 17/29 non-routed cert
KB_ACC = 0.9719    # SCALE-001: 1 - 136/4835 salah hit
TOKENS_CALL = 176  # eff tok/cert v9 (terukur)
VOLUMES = [500, 5000]
SKEWS = [0.70, 0.80, 0.90]
GATE_VOL = 5000
GATE_SKEW = 0.80


def project(r: dict, n: int) -> dict:
    """Akurasi & biaya akhir untuk satu workload replay (alur ROUTER→KB→LLM)."""
    non_routed = r["non_routed_total"]
    saved = r["saved_llm"]
    miss = r["non_routed_miss"]
    routed = n - non_routed
    # routed → router (100%); non-routed → KB hit (97.2%) atau LLM (58.6%)
    correct_kb = routed * ROUTER_ACC + saved * KB_ACC + miss * LLM_ACC
    correct_nokb = routed * ROUTER_ACC + non_routed * LLM_ACC
    calls_nokb = non_routed
    calls_kb = miss
    return {
        "acc_kb": correct_kb / n,
        "acc_nokb": correct_nokb / n,
        "calls_nokb": calls_nokb,
        "calls_kb": calls_kb,
        "tokens_nokb": calls_nokb * TOKENS_CALL,
        "tokens_kb": calls_kb * TOKENS_CALL,
        "cost_saved_pct": 1 - calls_kb / calls_nokb if calls_nokb else 0.0,
    }


def render_md(results: dict) -> str:
    lines = [
        "# KB-SCALE-005 — Proyeksi akurasi & biaya produksi end-to-end",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | SEED={SEED} | "
        f"confirm {CONFIRMS}x | 0 LLM runtime | korpus 74 (label terukur)",
        "",
        f"**Model (nilai terukur):** router exact {ROUTER_ACC:.0%} (45/45) | "
        f"KB serve benar {KB_ACC:.1%} (SCALE-001) | LLM exact {LLM_ACC:.1%} "
        f"(17/29 non-routed) | token/call {TOKENS_CALL} (v9).",
        "",
        "| N | Skew | Akurasi tanpa KB | Akurasi dgn KB | LLM calls tanpa KB | dgn KB | Token tanpa KB | dgn KB | Hemat biaya |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for n in VOLUMES:
        for s in SKEWS:
            r = results[(n, s)]
            lines.append(f"| {n} | {s:.0%} | {r['acc_nokb'] * 100:.1f}% | "
                         f"{r['acc_kb'] * 100:.1f}% | {r['calls_nokb']} | {r['calls_kb']} | "
                         f"{r['tokens_nokb']} | {r['tokens_kb']} | {r['cost_saved_pct'] * 100:.0f}% |")
    g = results[(GATE_VOL, GATE_SKEW)]
    gate1 = g["acc_kb"] >= g["acc_nokb"]
    gate2 = g["cost_saved_pct"] >= 0.50
    verdict = "PASS" if (gate1 and gate2) else "FAIL"
    lines += [
        "",
        "## GATE (80/20, N=5000)",
        "",
        f"- Akurasi dgn KB ({g['acc_kb'] * 100:.1f}%) >= tanpa KB "
        f"({g['acc_nokb'] * 100:.1f}%) → {'PASS' if gate1 else 'FAIL'}",
        f"- Hemat biaya ({g['cost_saved_pct'] * 100:.0f}%) >= 50% → "
        f"{'PASS' if gate2 else 'FAIL'}",
        f"- **VERDICT: {verdict}**",
        "",
        "## Interpretasi",
        "",
        "- **KB tidak menurunkan akurasi**: serve KB (97.2%) > LLM fallback "
        "(58.6%) → akurasi akhir dgn KB >= tanpa KB di semua kombinasi.",
        "- Hemat biaya = hemat calls (KB menggantikan LLM di key populer) — "
        "KB = cache yang LEBIH akurat dari LLM (key populer = jawaban "
        "terverifikasi 3x).",
        "- Proyeksi memakai label korpus 74 (bukan sintetis); distribusi "
        "request = simulasi. Validasi akhir tetap audit.py di data riil.",
    ]
    return "\n".join(lines)


def main() -> None:
    texts = load_texts()
    keys = build_keys(texts)
    freqs = {}
    for stem, t in sorted(texts.items()):
        key, _, _ = __import__("tests.kb.audit", fromlist=["pipeline_label"]).pipeline_label(stem, t, "plain")
        if key:
            freqs[key] = freqs.get(key, 0) + 1
    results = {}
    for n in VOLUMES:
        for s in SKEWS:
            alpha = alpha_for_skew(keys, freqs, s)
            rng = random.Random(SEED)
            r = replay_workload(keys, freqs, alpha, rng, n)
            results[(n, s)] = project(r, n)
            print(f"N={n} skew={s:.0%}: acc {results[(n, s)]['acc_nokb'] * 100:.1f}% -> "
                  f"{results[(n, s)]['acc_kb'] * 100:.1f}% | biaya hemat "
                  f"{results[(n, s)]['cost_saved_pct'] * 100:.0f}%")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "summary_kb_scale_e2e.json"), "w") as f:
        json.dump({f"{n}_{int(s * 100)}": r for (n, s), r in results.items()},
                  f, indent=2)
    with open(OUT_MD, "w") as f:
        f.write(render_md(results))
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_kb_scale_e2e.json")


if __name__ == "__main__":
    main()
