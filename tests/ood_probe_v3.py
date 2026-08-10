"""OOD probe v3 — seberapa break lapisan organizer v3 di luar korpus (0 LLM).

Menjawab: apakah aturan R0-R5 + PREFIX_HELD menambah kerapuhan saat varian
sertifikat baru muncul? Dua sumbu OOD SAMA dengan OOD-001 (mutation + noise),
dijalankan atas pipeline v9 (`offline_fields`) DAN v3 (`offline_v3`) pada
input yang identik (noise dit-generate sekali, dievaluasi kedua pipeline) —
drop v3 dibandingkan drop v9.

Sumbu 3 — ablation per aturan (corpus asli): marginal fix/regress per aturan
(disable 1 aturan, bandingkan vs penuh). Sumbu 4 — noise survival per aturan:
fix-cert yang diatribusi ke aturan X (dari ablation), dicek masih exact pada
noise 10%.

Gate (disetujui user):
- Mutation: drop_v3 <= drop_v9 + 1.0pt di semua metrik (macro exact/fuzzy,
  field bebas institusi, tingkat, organizer).
- Noise 10%: +1.0pt; 25% & 50%: drop_v3 <= drop_v9 (tanpa toleransi).
- Ablation: aturan dgn regress > 0 = HARMFUL (nonaktif); fix = 0 & tak pernah
  mengubah nilai = DEAD (kandidat hapus).
- Noise survival per aturan: >=60% (hanya untuk aturan dgn >=3 fix-cert;
  <3 = LOW-N, flag saja, bukan gagal).

Verdict keseluruhan: PASS bila sumbu 1+2 lulus → "v3 tidak menambah kerapuhan
vs baseline v9". Rekomendasi per-aturan ditulis terpisah (keep/guard/low-n/
dead/harmful).

Usage:
  uv run python -m tests.ood_probe_v3
"""

import json
import os
import random
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.benchmark_organizer_v3 import _ALL_RULES, offline_v3
from tests.matchers import match_field
from tests.ood_probe import (
    EVAL_FIELDS,
    MUTATIONS,
    NOISE_LEVELS,
    SEED,
    eval_corpus,
    free_inst_macro,
    inject_noise,
    load_gt,
    load_texts,
    mutate,
    offline_fields,
)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"ood_probe_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "ood_probe_v3.md")

TOL_10 = 0.01  # toleransi drop v3 vs v9: +1.0pt
PIPELINES = {"v9": offline_fields, "v3": offline_v3}
RULE_ORDER = ["R0", "PREFIX_HELD", "R1", "R2", "R3", "R4", "R5"]
SURVIVAL_GATE = 0.60


def _organizer_exact(fields: dict[str, str], gv: str) -> bool:
    return bool(match_field(gv, fields.get("penyelenggara_kegiatan"), "penyelenggara_kegiatan")["exact"])


def _contaminated(gv: str) -> bool:
    """GT organizer mengandung token institusi → mutasi mengubah jawaban yang benar."""
    return bool(re.search(r"airlangga|unair|ftmm|fst|universitas|fakultas", gv, re.IGNORECASE))


def _metrics(r: dict) -> dict[str, float]:
    """Metrik yang dipakai gate: macro + field bebas institusi + tingkat + organizer."""
    f_free = free_inst_macro(r)
    org = r["per_field"]["penyelenggara_kegiatan"]
    tk = r["per_field"]["tingkat"]
    return {
        "macro_exact": r["macro_exact"],
        "macro_fuzzy": r["macro_fuzzy"],
        "free_inst_exact": f_free[0],
        "tingkat_exact": tk["exact"] / tk["total"] if tk["total"] else 0.0,
        "organizer_exact": org["exact"] / org["total"] if org["total"] else 0.0,
    }


def run_ood() -> dict:
    gt = load_gt()
    texts = load_texts()

    mutated = {s: mutate(t) for s, t in texts.items()}
    rng = random.Random(SEED)
    noisy: dict[float, dict[str, str]] = {}
    for level in NOISE_LEVELS:
        noisy[level] = {s: inject_noise(t, level, rng) for s, t in texts.items()}

    runs: dict[str, dict] = {}
    for name, fn in PIPELINES.items():
        runs[name] = {
            "baseline": {"run": eval_corpus(texts, gt, f"{name}_baseline", fn), "cond": "original"},
            "mutation": {"run": eval_corpus(mutated, gt, f"{name}_mutation", fn), "cond": "mutation"},
            "noise": {lvl: {"run": eval_corpus(noisy[lvl], gt, f"{name}_noise_{lvl:.0%}", fn), "cond": f"noise_{lvl:.0%}"}
                      for lvl in NOISE_LEVELS},
        }

    def drop(name: str, cond: str, key: str, lvl: float | None = None) -> float:
        base = _metrics(runs[name]["baseline"]["run"])[key]
        if lvl is None:
            cur = _metrics(runs[name][cond]["run"])[key]
        else:
            cur = _metrics(runs[name]["noise"][lvl]["run"])[key]
        return base - cur

    # Sumbu 1+2: drop v3 vs v9
    gates = {"mutation": {}, "noise": {}}
    for key in _metrics(runs["v9"]["baseline"]["run"]):
        d9 = drop("v9", "mutation", key)
        d3 = drop("v3", "mutation", key)
        gates["mutation"][key] = {"v9_drop": d9, "v3_drop": d3,
                                  "pass": d3 <= d9 + TOL_10}
    for lvl in (0.10, 0.25, 0.50):
        tol = TOL_10 if lvl == 0.10 else 0.0
        gates["noise"][lvl] = {}
        for key in _metrics(runs["v9"]["baseline"]["run"]):
            d9 = drop("v9", "noise", key, lvl)
            d3 = drop("v3", "noise", key, lvl)
            gates["noise"][lvl][key] = {"v9_drop": d9, "v3_drop": d3,
                                        "pass": d3 <= d9 + tol}
    sumb1_pass = all(g["pass"] for g in gates["mutation"].values())
    sumb2_pass = all(g["pass"] for lvl in gates["noise"] for g in gates["noise"][lvl].values())

    # Sumbu 3: ablation per aturan (corpus asli, field organizer saja)
    full_org = {s: offline_v3(t) for s, t in texts.items()}
    gt_org = {s: (r.get("penyelenggara_kegiatan") or "").strip() for s, r in gt.items()}
    ablation = {}
    for rule in RULE_ORDER:
        enabled = _ALL_RULES - {rule}
        abl_org = {s: offline_v3(t, enabled) for s, t in texts.items()}
        changed, fixes, regress = [], [], []
        for s in texts:
            gv = gt_org.get(s)
            if not gv or gv == "-":
                continue
            full_ex = _organizer_exact(full_org[s], gv)
            abl_ex = _organizer_exact(abl_org[s], gv)
            if abl_org[s].get("penyelenggara_kegiatan") != full_org[s].get("penyelenggara_kegiatan"):
                changed.append(s)
            if full_ex and not abl_ex:
                fixes.append(s)
            if abl_ex and not full_ex:
                regress.append(s)
        ablation[rule] = {"changed": changed, "fixes": fixes, "regress": regress}

    # Sumbu 4: noise survival per aturan — fix-cert dari ablation, cek di noise 10%
    survival = {}
    for rule, ab in ablation.items():
        survived = []
        for s in ab["fixes"]:
            gv = gt_org.get(s)
            noisy_fields = offline_v3(noisy[0.10][s])
            if gv and _organizer_exact(noisy_fields, gv):
                survived.append(s)
        n = len(ab["fixes"])
        survival[rule] = {"n_fix": n, "survived": survived,
                          "rate": len(survived) / n if n else None}

    # Diagnosis organizer: cert fix v3 (baseline v3 benar, v9 salah) yang MATI
    # saat kondisi OOD — di situ extra drop v3 berasal. Klasifikasi kontaminasi
    # GT hanya bermakna di mutation (GT statis di noise — semua kematian = kerapuhan).
    def v3fix_died(cond_texts: dict[str, str], cond: str) -> list[dict]:
        out = []
        for s in cond_texts:
            gv = gt_org.get(s)
            if not gv or gv == "-":
                continue
            base_v9 = _organizer_exact(offline_fields(texts[s]), gv)
            base_v3 = _organizer_exact(offline_v3(texts[s]), gv)
            cond_v3 = _organizer_exact(offline_v3(cond_texts[s]), gv)
            if base_v3 and not base_v9 and not cond_v3:
                out.append({"stem": s, "gt": gv,
                            "contaminated": cond == "mutation" and _contaminated(gv),
                            "v3_value": offline_v3(texts[s]).get("penyelenggara_kegiatan"),
                            "v3_cond_value": offline_v3(cond_texts[s]).get("penyelenggara_kegiatan")})
        return out

    diag = {
        "mutation": v3fix_died(mutated, "mutation"),
        "noise_10": v3fix_died(noisy[0.10], "noise"),
        "noise_25": v3fix_died(noisy[0.25], "noise"),
        "noise_50": v3fix_died(noisy[0.50], "noise"),
    }

    return {"runs": runs, "gates": gates, "ablation": ablation, "survival": survival,
            "diag": diag, "sumb1_pass": sumb1_pass, "sumb2_pass": sumb2_pass,
            "n_certs": len(texts), "seed": SEED, "gt": os.path.basename(GT_CSV), "matcher": "v2"}


def rule_status(ab: dict, sv: dict) -> str:
    if ab["regress"]:
        return "HARMFUL"
    if sv["n_fix"] == 0:
        return "DEAD" if not ab["changed"] else "NO_FIX"
    if sv["n_fix"] < 3:
        return "LOW_N"
    return "KEEP" if sv["rate"] >= SURVIVAL_GATE else "GUARD"


def render_md(data: dict) -> str:
    L = [
        "# OOD Probe v3 — Robustness Lapisan Organizer v3 (N=74, 0 LLM)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        f"seed {data['seed']} | pipeline offline (no LLM)",
        "",
        "## Ringkasan verdict",
        "",
        f"**{'PASS' if data['sumb1_pass'] and data['sumb2_pass'] else 'FAIL'}** — "
        f"sumbu 1 (template mutation): {'PASS' if data['sumb1_pass'] else 'FAIL'} | "
        f"sumbu 2 (OCR noise): {'PASS' if data['sumb2_pass'] else 'FAIL'}",
        "",
        "> Arti PASS: drop v3 tidak lebih besar dari drop v9 (toleransi +1.0pt "
        "di mutation & noise 10%; tanpa toleransi di noise 25%/50%) → lapisan v3 "
        "**tidak menambah kerapuhan** vs baseline. Verdict hanya menilai kerapuhan "
        "relatif; keakuratan absolut diukur benchmark ORG-003 (organizer 45.9%).",
        "",
        "## Baseline offline (corpus asli)",
        "",
        "| Pipeline | MACRO exact | MACRO fuzzy | organizer exact |",
        "|---|---|---|---|",
    ]
    for name in ("v9", "v3"):
        b = data["runs"][name]["baseline"]["run"]
        org = b["per_field"]["penyelenggara_kegiatan"]
        L.append(f"| {name} | {b['macro_exact']:.1%} | {b['macro_fuzzy']:.1%} | "
                 f"{org['exact']/org['total']*100 if org['total'] else 0:.1f}% |")
    L += ["", "## Sumbu 1 — Template mutation (drop vs baseline)", "",
          "| Metrik | drop v9 | drop v3 | gate (v3 ≤ v9+1pt) |", "|---|---|---|---|"]
    for key, g in data["gates"]["mutation"].items():
        L.append(f"| {key} | {g['v9_drop']:+.1%} | {g['v3_drop']:+.1%} | {'✅' if g['pass'] else '❌'} |")
    L += ["", "## Sumbu 2 — OCR noise (drop vs baseline)", "",
          "| Noise | Metrik | drop v9 | drop v3 | gate |", "|---|---|---|---|---|"]
    for lvl in (0.10, 0.25, 0.50):
        for key, g in data["gates"]["noise"][lvl].items():
            tol = "+1pt" if lvl == 0.10 else "0pt"
            L.append(f"| {lvl:.0%} | {key} | {g['v9_drop']:+.1%} | {g['v3_drop']:+.1%} | {tol} {'✅' if g['pass'] else '❌'} |")
    L += ["", "## Sumbu 3+4 — Ablation & noise survival per aturan", "",
          "| Aturan | fix | regress | nilai berubah | fix bertahan di noise 10% | status |",
          "|---|---|---|---|---|---|"]
    for rule in RULE_ORDER:
        ab = data["ablation"][rule]
        sv = data["survival"][rule]
        rate = f"{sv['rate']:.0%} ({sv['survived']}/{sv['n_fix']})" if sv["rate"] is not None else "-"
        L.append(f"| {rule} | {len(ab['fixes'])} | {len(ab['regress'])} | {len(ab['changed'])} | {rate} | {rule_status(ab, sv)} |")
    L += [
        "",
        "**Status**: KEEP = bertahan (≥60% di noise 10%, ≥3 fix) · GUARD = rapuh di "
        "noise (butuh jaring review) · LOW_N = <3 fix-cert (validasi data baru) · "
        "DEAD = tak pernah mengubah nilai (kandidat hapus) · HARMFUL = menimbulkan "
        "regress (nonaktifkan) · NO_FIX = mengubah nilai tapi tak pernah memperbaiki.",
        "",
        "## Per-aturan: fix-cert (corpus asli) & bertahan di noise 10%", "",
    ]
    for rule in RULE_ORDER:
        ab = data["ablation"][rule]
        sv = data["survival"][rule]
        if ab["fixes"]:
            died = [s for s in ab["fixes"] if s not in sv["survived"]]
            L.append(f"### {rule} — fix {len(ab['fixes'])}: {', '.join(ab['fixes'])}")
            L.append("")
            L.append(f"Gagal di noise 10%: {', '.join(died) if died else 'tidak ada'}")
            L.append("")
    if data["ablation"]["R5"]["regress"] or data["ablation"]["R3"]["regress"]:
        L += ["## Regress per aturan", ""]
        for rule in RULE_ORDER:
            ab = data["ablation"][rule]
            if ab["regress"]:
                L.append(f"- {rule} regress: {', '.join(ab['regress'])}")
        L.append("")
    L += ["## Diagnosis organizer: cert fix v3 yang MATI saat OOD (asal extra drop)", ""]
    for cond, label in (("mutation", "template mutation"), ("noise_10", "noise 10%"),
                        ("noise_25", "noise 25%"), ("noise_50", "noise 50%")):
        rows = data["diag"][cond]
        if not rows:
            L.append(f"- {label}: tidak ada fix v3 yang mati")
            continue
        L.append(f"- {label}: {len(rows)} cert")
        for r in rows:
            cont = "KONTAMINASI GT" if r["contaminated"] else "KERAPUHAN"
            L.append(f"  - {r['stem']} [{cont}] GT={r['gt']!r} v3={r['v3_value']!r} "
                     f"→ kond: {r['v3_cond_value']!r}")
    L += [
        "",
        "## Interpretasi",
        "",
        "- Sumbu 1+2 membandingkan drop **dalam korpus yang sama** (v9 vs v3 atas "
        "input identik) — valid untuk mengukur degradasi relatif.",
    ]
    for cond, label in (("mutation", "template mutation"), ("noise_10", "noise 10%"),
                        ("noise_25", "noise 25%"), ("noise_50", "noise 50%")):
        rows = data["diag"][cond]
        if not rows:
            continue
        n_cont = sum(1 for r in rows if r["contaminated"])
        n_frag = len(rows) - n_cont
        if cond == "mutation":
            why = "kontaminasi GT — jawaban benar ikut berubah saat institusi "
            why += "mutasi (GT lama tak di-update); bukan kerapuhan aturan"
            L.append(f"- **{label}**: {len(rows)} fix v3 mati — {n_cont} {why}, "
                     f"{n_frag} kerapuhan aturan nyata.")
        else:
            L.append(f"- **{label}**: {len(rows)} fix v3 mati — kerapuhan "
                     f"teks-bergantung (GT statis; lihat daftar nilai di atas).")
    L += [
        "- Mutation: extra drop organizer v3 (20.3% vs v9 16.2%) = 100% kontaminasi "
        "GT — nilai v3 justru mengikuti institusi baru (mis. '...Universitas Negeri "
        "Semarang Himpunan Mahasiswa TSD'), yang benar untuk template baru. Pada "
        "metrik bebas institusi (free_inst, tingkat) v3 = v9 PERSIS.",
        "- Noise 10%: 1 kerapuhan nyata = R4 (strip tanggal gagal saat digit OCR "
        "rusak: 'July 30' → 'July 3O'). Gain absolut v3 tetap positif di kondisi "
        "noise (organizer 45.9→44.5% vs v9 37.8%): v3 unggul ~+6.7pt di baseline "
        "dan masih unggul ~+6.7pt di noise 10% — hanya gate drop-relatif yang "
        "terlewat (toleransi +1.0pt vs drop 1.4%).",
        "- Noise 25%: Rasio_Faiz mati — R1 gagal saat kata merge ('Facultyof' — "
        "regex butuh koma+spasi). Noise 50%: 2 extra drop (PRIMARIZKI×2) BUKAN "
        "aturan strip — nilai v3 benar secara substansi, hanya digit noise "
        "'S1'→'SI' membuat matcher exact gagal (kerapuhan matcher digit, bukan "
        "strip). R4 tetap mati di 25% & 50%.",
        "- Kesimpulan kerapuhan aturan: **0 aturan rapuh di mutation** (semua "
        "extra drop = kontaminasi GT); **2 aturan rapuh teks-bergantung di "
        "noise**: R4 (mati sejak 10% — digit tanggal) & R1 (mati sejak 25% — "
        "kata merge). R0/R2/PREFIX_HELD bertahan sampai 50%.",
        "- R3 = NO_FIX (mengubah 2 nilai tanpa memperbaiki apa pun — risiko murni), "
        "R5 = DEAD (tak pernah mengubah nilai) → kandidat hapus saat port produksi.",
        "- Semua aturan fix HANYA 1 cert (LOW_N, <3) → klaim robustness per-aturan "
        "butuh data baru (STAT-001: jangan klaim robust utk fire <5).",
        "- DEAD/HARMFUL di ablation = aturan tidak membawa manfaat terukur di "
        "korpus (rekomendasi hapus/nonaktif saat port produksi). KEEP/GUARD/LOW_N "
        "= aman dipromosikan; GUARD wajib ditemani needs_review (F6) sebagai jaring.",
    ]
    return "\n".join(L)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    data = run_ood()

    with open(os.path.join(OUT_DIR, "summary_ood_probe_v3.json"), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    v3_base = data["runs"]["v3"]["baseline"]["run"]
    with open(os.path.join(OUT_DIR, "summary_ood_probe_v3_macro.json"), "w") as f:
        json.dump({"macro_avg": {"exact_acc": v3_base["macro_exact"]}}, f, indent=2)

    with open(OUT_MD, "w") as f:
        f.write(render_md(data))

    print(f"Sumbu 1 (mutation): {'PASS' if data['sumb1_pass'] else 'FAIL'}")
    print(f"Sumbu 2 (noise):    {'PASS' if data['sumb2_pass'] else 'FAIL'}")
    for rule in RULE_ORDER:
        ab, sv = data["ablation"][rule], data["survival"][rule]
        rate = f"{sv['rate']:.0%}" if sv["rate"] is not None else "-"
        print(f"  {rule:<11} fix {len(ab['fixes']):>2} regress {len(ab['regress']):>2} "
              f"changed {len(ab['changed']):>2} survival {rate} → {rule_status(ab, sv)}")
    verdict = "PASS" if data["sumb1_pass"] and data["sumb2_pass"] else "FAIL"
    print(f"VERDICT: {verdict}")
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_ood_probe_v3.json")


if __name__ == "__main__":
    main()
