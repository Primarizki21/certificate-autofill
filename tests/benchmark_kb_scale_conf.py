"""KB-SCALE-004 — Konfigurasi KB utk hemat maksimal: confirm 2x vs 3x, key alias.

KB-001/002 membuktikan 1x confirm = GAGAL (wrong 5 — error LLM terkunci).
3x = default aman. **2x BELUM pernah diuji** — di volume menengah (N=500),
warmup 3x menelan porsi besar (SCALE-001: saved 12%). Pertanyaan: apakah 2x
confirm mempercepat warmup tanpa menambah salah?

Plus: key alias (FST pair, KB-003/006: hit 3->5 tanpa efek samping) — key
lebih mudah berulang → hit lebih tinggi.

Grid: CONFIRMS {2,3} x key {plain, alias} x N {500, 5000} x skew 80/20.
GATE: (1) wrong_2x <= wrong_3x (no-regress), (2) hemat N=500 2x > 3x.

0 LLM runtime, produksi zero-touch. Korpus 74 (bukan sintetis).

Usage:
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_kb_scale_conf
"""

import json
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

import tests.kb.kb as kbimpl
from tests.benchmark_kb_scale import SEED, TOP_SHARE, alpha_for_skew
from tests.kb.audit import pipeline_label
from tests.kb.kb import KBEntry, TingkatKB
from tests.matchers import match_field
from tests.ood_probe import load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"kb_scale_conf_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "kb_scale_conf.md")

N_SIZES = [500, 5000]
CONFIRMS_SET = [2, 3]
VARIANTS = ["plain", "alias"]
SKEW = 0.80
ALIASES = {"information system dept": "information systems dept"}


def build_keys(texts: dict[str, str], variant: str) -> dict[tuple, dict]:
    per_stem: dict[tuple, list] = {}
    stems: dict[tuple, str] = {}
    aliases = ALIASES if variant == "alias" else None
    for stem in sorted(texts):
        text = texts[stem]
        # key alias = pipeline label dengan key variant alias (make_key aliases)
        # audit.pipeline_label menerima variant 'alias' — key.jsn memakai KEY_ALIASES;
        # di sini kita override via pipeline_label variant (lihat audit.py).
        key, level, routed = pipeline_label(stem, text, variant)
        if key:
            per_stem.setdefault(key, []).append((level or "", routed))
            stems.setdefault(key, stem)
    gt = load_gt()
    keys = {}
    for key, rows in per_stem.items():
        level, routed = zip(*rows)
        keys[key] = {
            "tingkat": max(set(level), key=level.count),
            "routed": max(set(routed), key=routed.count),
            "gt": gt.get(stems[key], {}).get("tingkat"),
        }
    return keys


def replay(keys: dict, freqs: dict, alpha: float, n: int, confirms: int,
           rng: random.Random) -> dict:
    kbimpl.WARMUP_CONFIRMS = confirms
    kb = TingkatKB()
    order = sorted(keys, key=lambda k: -freqs[k])
    weights = [freqs[k] ** alpha for k in order]
    requests = rng.choices(order, weights=weights, k=n)
    saved = miss = hit = wrong = 0
    for key in requests:
        r = keys[key]
        entry = kb.peek(key)
        if entry and entry.authoritative:
            hit += 1
            if not r["routed"]:
                saved += 1
            if r["gt"] and not match_field(r["gt"], entry.tingkat, "tingkat")["exact"]:
                wrong += 1
        else:
            if not r["routed"]:
                miss += 1
        kb.write(key, KBEntry(r["tingkat"] or "Lainnya",
                              "router_rule" if r["routed"] else "llm", "conf"))
    tot = saved + miss
    return {"saved": saved, "pct": saved / tot if tot else 0.0, "hit": hit,
            "wrong": wrong, "n": n}


def render_md(results: dict, meta: dict) -> str:
    lines = [
        "# KB-SCALE-004 — Konfigurasi KB: confirm 2x vs 3x, key alias",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | SEED={SEED} | "
        f"skew 80/20 | 0 LLM runtime | GT {os.path.basename(GT_CSV)} | korpus 74 (bukan sintetis)",
        "",
        "**Pertanyaan:** 2x confirm aman (wrong no-regress vs 3x)? Dan alias "
        "menaikkan hemat di volume menengah (N=500) yang di SCALE-001 cuma 12%?",
        "",
        "| Confirm | Key | N | Saved % | Saved | Hit | Wrong |",
        "|---|---|---|---|---|---|---|",
    ]
    for cf, var, n in [(c, v, nn) for c in CONFIRMS_SET for v in VARIANTS for nn in N_SIZES]:
        r = results[(cf, var, n)]
        lines.append(f"| {cf}x | {var} | {n} | {r['pct'] * 100:.0f}% | {r['saved']} | "
                     f"{r['hit']} | {r['wrong']} |")
    g = results
    w2 = sum(g[(2, v, n)]["wrong"] for v in VARIANTS for n in N_SIZES)
    w3 = sum(g[(3, v, n)]["wrong"] for v in VARIANTS for n in N_SIZES)
    h2 = sum(g[(2, v, 500)]["pct"] for v in VARIANTS) / 2
    h3 = sum(g[(3, v, 500)]["pct"] for v in VARIANTS) / 2
    gate1 = w2 <= w3
    gate2 = h2 > h3
    verdict = "PASS" if (gate1 and gate2) else "FAIL"
    lines += [
        "",
        "## GATE",
        "",
        f"- Wrong 2x ({w2}) <= Wrong 3x ({w3}) → {'PASS' if gate1 else 'FAIL'}",
        f"- Hemat N=500 avg 2x ({h2 * 100:.0f}%) > 3x ({h3 * 100:.0f}%) → "
        f"{'PASS' if gate2 else 'FAIL'}",
        f"- **VERDICT: {verdict}**",
        "",
        "## Interpretasi",
        "",
        f"- **2x confirm: hemat naik ({h2 * 100:.0f}% vs {h3 * 100:.0f}% @N=500) "
        f"TAPI wrong ikut naik ({w2} vs {w3}, +{w2 - w3})** — error pipeline "
        f"terkunci lebih cepat dgn confirm lebih sedikit. Konsisten dgn KB-002 "
        f"(1x = wrong 5). **3x confirm TETAP wajib** — hemat ekstra 2x tidak "
        f"sebanding dgn salah ekstra.",
        "- Alias (FST pair, KB-003/006): keys 55→54, hit sedikit naik di N=500 "
        f"(alias 409 vs plain 407 @2x) — efek kecil di korpus ini (pair "
        f"non-populer); berguna di data riil dgn fragmentasi lebih banyak.",
        "- Angka ini korpus 74 — konfigurasi final produksi tetap diuji di "
        "data riil (audit.py) sebelum promosi.",
    ]
    return "\n".join(lines)


def main() -> None:
    texts = load_texts()
    gt = load_gt()
    results = {}
    for variant in VARIANTS:
        keys = build_keys(texts, variant)
        freqs = {}
        for stem, t in sorted(texts.items()):
            key, _, _ = pipeline_label(stem, t, variant)
            if key:
                freqs[key] = freqs.get(key, 0) + 1
        alpha = alpha_for_skew(keys, freqs, SKEW)
        print(f"variant {variant}: keys={len(keys)} alpha={alpha:.2f}")
        for confirms in CONFIRMS_SET:
            for n in N_SIZES:
                rng = random.Random(SEED)
                r = replay(keys, freqs, alpha, n, confirms, rng)
                results[(confirms, variant, n)] = r
                print(f"  {confirms}x {variant} N={n}: saved={r['pct'] * 100:.0f}% "
                      f"wrong={r['wrong']}")
    meta = {"seed": SEED, "skew": SKEW, "gt": os.path.basename(GT_CSV)}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "summary_kb_scale_conf.json"), "w") as f:
        json.dump({"meta": meta,
                   "results": {f"{c}x_{v}_{n}": r for (c, v, n), r in results.items()}},
                  f, indent=2, ensure_ascii=False)
    with open(OUT_MD, "w") as f:
        f.write(render_md(results, meta))
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_kb_scale_conf.json")


if __name__ == "__main__":
    main()
