"""Robustness Eval — gabungan Stat Validation + OOD probe, 1 perintah, 1 report.

Menjalankan `stat_validation.main()` (k-fold router + bootstrap CI) dan
`ood_probe.main()` (template mutation + OCR noise) — masing-masing tetap
menulis run dir + report detailnya sendiri (reuse penuh, tanpa duplikasi
logika), lalu menyatukan ringkasan numerik dari kedua `summary.json` ke
`docs/report/robustness_eval.md` + verdict gate untuk eksperimen berikutnya.

Usage:
  uv run python -m tests.robustness_eval
"""

import glob
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

import tests.ood_probe as op
import tests.stat_validation as sv

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_MD = os.path.join(REPO, "docs", "report", "robustness_eval.md")
RUNS = os.path.join(REPO, "tests", "benchmark_runs")


def latest_summary(pattern: str) -> dict:
    dirs = glob.glob(os.path.join(RUNS, pattern))
    if not dirs:
        raise FileNotFoundError(f"tidak ada run dir {pattern}* — jalankan modul sumber dulu")
    latest = max(dirs, key=os.path.getmtime)
    with open(os.path.join(latest, "summary.json")) as f:
        return json.load(f)


def rule_verdicts(rules: dict) -> tuple[list[str], list[str]]:
    unstable = [r for r, d in rules.items() if not d["stable"]]
    low_n = [r for r, d in rules.items() if d["low_n"]]
    return unstable, low_n


def render_md(stat: dict, ood: dict) -> str:
    ci = stat["ci"]
    rules = stat["rules"]
    unstable, low_n = rule_verdicts(rules)
    ood_b = ood["baseline"]
    ood_m = ood["mutation"]
    noise = {r["label"]: r["macro_exact"] for r in ood["noise"]}
    fields_rows = "".join(
        f"| {f} | {ci[f'exact_{f}']['mean']:.1%} | "
        f"{ci[f'exact_{f}']['ci95_low']:.1%}-{ci[f'exact_{f}']['ci95_high']:.1%} |\n"
        for f in sv.EVAL_FIELDS
    )
    low_n_list = ", ".join(low_n) or "—"
    unstable_list = ", ".join(unstable) or "—"
    return f"""# Robustness Eval — Pipeline v9 (k-fold + bootstrap CI + OOD)

> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 |
> pipeline offline (no LLM) | gabungan `stat_validation` + `ood_probe`.

## 1. Stat Validation (5-fold router + bootstrap CI)

- Corpus: {stat['n_certs']} cert, bootstrap {stat['n_boot']}x seed {stat['seed']}, 5-fold.
- MACRO exact: mean **{ci['macro_exact']['mean']:.1%}** (CI95 {ci['macro_exact']['ci95_low']:.1%}–{ci['macro_exact']['ci95_high']:.1%})
- MACRO fuzzy: mean **{ci['macro_fuzzy']['mean']:.1%}** (CI95 {ci['macro_fuzzy']['ci95_low']:.1%}–{ci['macro_fuzzy']['ci95_high']:.1%})
- Router precision: mean **{ci['router_precision']['mean']:.1%}** (CI95 {ci['router_precision']['ci95_low']:.1%}–{ci['router_precision']['ci95_high']:.1%})
- Router coverage: mean **{ci['router_coverage']['mean']:.1%}** (CI95 {ci['router_coverage']['ci95_low']:.1%}–{ci['router_coverage']['ci95_high']:.1%})

| Field exact | mean | CI95 |
|---|---|---|
{fields_rows}| Rule UNSTABLE (min fold prec <95%): {unstable_list} |
| Rule LOW-N (fire <5, jangan klaim robust): {low_n_list} |

## 2. OOD Probe (template mutation + OCR noise)

| Skenario | MACRO exact | Delta vs baseline |
|---|---|---|
| Baseline offline | {ood_b['macro_exact']:.1%} | — |
| Template mutation | {ood_m['macro_exact']:.1%} | {ood_m['macro_exact'] - ood_b['macro_exact']:+.1%} |
| Noise 10% | {noise.get('noise_10%', 0):.1%} | {noise.get('noise_10%', 0) - ood_b['macro_exact']:+.1%} |
| Noise 25% | {noise.get('noise_25%', 0):.1%} | {noise.get('noise_25%', 0) - ood_b['macro_exact']:+.1%} |
| Noise 50% | {noise.get('noise_50%', 0):.1%} | {noise.get('noise_50%', 0) - ood_b['macro_exact']:+.1%} |

## 3. Gate untuk eksperimen berikutnya (sintesis)

- **No-regress**: MACRO exact eksperimen baru wajib ≥ CI95 low baseline
  **{ci['macro_exact']['ci95_low']:.1%}** (bukan hanya ≥ mean {ci['macro_exact']['mean']:.1%}).
- **Rule router baru**: wajib k-fold; rule LOW-N (`{low_n_list}`) jangan
  diklaim robust; jangan dipromosikan tanpa data baru.
- **Noise**: batas praktis 10–25% karakter rusak — eksperimen yang menyentuh
  OCR/normalisasi teks wajib no-regress di level noise 10%.
- **Kerapuhan riil**: tingkat (−4.1pt saat mutation) = kandidat perbaikan
  router/KB; drop organizer/nomor saat mutation = artefak GT, bukan regresi.

## Sumber

- Detail k-fold + bootstrap: `docs/report/stat_validation.md` (run dir
  `tests/benchmark_runs/stat_validation_*`)
- Detail OOD: `docs/report/ood_probe.md` (run dir `tests/benchmark_runs/ood_probe_*`)
"""


def main() -> None:
    sv.main()
    op.main()
    stat = latest_summary("stat_validation_*")
    ood = latest_summary("ood_probe_*")
    with open(OUT_MD, "w") as f:
        f.write(render_md(stat, ood))
    print(f"wrote {OUT_MD}")
    print(f"stat: MACRO {stat['ci']['macro_exact']['mean']:.1%} "
          f"({stat['ci']['macro_exact']['ci95_low']:.1%}-{stat['ci']['macro_exact']['ci95_high']:.1%}) | "
          f"ood: baseline {ood['baseline']['macro_exact']:.1%} mutation {ood['mutation']['macro_exact']:.1%}")


if __name__ == "__main__":
    main()
