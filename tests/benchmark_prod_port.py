"""PROD-002 — Re-eval port produksi normalisasi organizer & nomor (0 LLM).

Baseline = `offline_fields` (produksi current: extract_certificate_fields ->
organizer_v2 -> map). Dua jalur dibandingkan, keduanya GT v9 + matcher v2:

- `offline_prod` = jalur PRODUKSI persis `run_extraction_pipeline` flag ON:
  extract_certificate_fields (backend) -> extract_organizer_v2 (backend) ->
  `normalize_organizer`/`normalize_nomor` (backend/app/services/
  organizer_normalize.py) -> map_fields_to_form.
- `offline_ref` = replica EKSPERIMEN (tests/): extract_organizer_v2 (tests) ->
  `_norm_organizer_v3(enabled={R0,PREFIX_HELD,R2,R6})` -> `_norm_org_format`
  -> `_norm_nomor` (R1/R4 SKIP, R3/R5 DROP — keputusan user handoff v29).

Gate:
1. **Port fidelity**: `offline_prod` == `offline_ref` per cert per field
   (hard assert — port verbatim harus identik dengan eksperimen).
2. **No-regress vs produksi current**: organizer >= 39.2%, nomor >= 59.6%,
   MACRO >= 55.7%.
3. Target eksperimen (tanpa R1/R4, 2 fix dikorbankan): organizer ~63.5%
   (47/74), nomor 76.9% (40/52), MACRO ~63.0%.

OOD (mutation/noise) TIDAK diulang: aturan = identik ORG-004 yang sudah
lolos OOD-003/ORG-004 (drop dalam toleransi) — port tidak mengubah aturan.

Usage:
  uv run python -m tests.benchmark_prod_port
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.extraction_pipeline import run_extraction_pipeline  # noqa: F401  (verifikasi import path)
from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from tests.benchmark_org_format import _norm_org_format
from tests.benchmark_org_norm import _norm_nomor
from tests.benchmark_organizer_v3 import _norm_organizer_v3
from tests.matchers import match_field
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts, offline_fields
from tests.organizer_extractor_v2 import extract_organizer_v2 as test_v2

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"prod_port_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "prod_organizer_port.md")

# Rule set final produksi (handoff v29 + KOREKSI R3): R1/R4 skip, R5 drop.
PROD_RULES = {"R0", "PREFIX_HELD", "R2", "R3", "R6"}


def offline_prod(text: str) -> dict[str, str]:
    """Jalur produksi flag ON (identik run_extraction_pipeline)."""
    from app.services.organizer_normalize import normalize_nomor, normalize_organizer
    from app.services.organizer_v2 import extract_organizer_v2 as prod_v2

    extracted = extract_certificate_fields(text)
    v2 = prod_v2(text)
    if v2:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(v2, 0.84, "organizer_v2")
    org = normalize_organizer(extracted.get("penyelenggara_kegiatan").value, text)
    if org:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(org, 0.84, "organizer_v2")
    nomor = normalize_nomor(text)
    if nomor:
        extracted["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(nomor, 0.95, "regex_certificate_number")
    mapped = map_fields_to_form(extracted, tahun_akademik="", bukti_fisik="Sertifikat")
    return {f: (mapped.get(f).value if mapped.get(f) else None) for f in EVAL_FIELDS}


def offline_ref(text: str) -> dict[str, str]:
    """Replica eksperimen (rule set final, R1/R4 skip)."""
    extracted = extract_certificate_fields(text)
    v2 = test_v2(text)
    if v2:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(v2, 0.84, "organizer_v2")
    org = _norm_organizer_v3(extracted.get("penyelenggara_kegiatan").value, text, enabled=PROD_RULES)
    org4 = _norm_org_format(org, text)
    if org4:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(org4, 0.84, "organizer_v2")
    nomor = _norm_nomor(text)
    if nomor:
        extracted["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(nomor, 0.95, "regex_certificate_number")
    mapped = map_fields_to_form(extracted, tahun_akademik="", bukti_fisik="Sertifikat")
    return {f: (mapped.get(f).value if mapped.get(f) else None) for f in EVAL_FIELDS}


def eval_corpus(texts: dict[str, str], gt: dict[str, dict], fn) -> dict:
    per_field = {f: {"total": 0, "exact": 0, "fuzzy": 0} for f in EVAL_FIELDS}
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        fields = fn(text)
        for f in EVAL_FIELDS:
            gv = (row.get(f) or "").strip()
            if not gv or gv == "-":
                continue
            m = match_field(gv, fields.get(f), f)
            pf = per_field[f]
            pf["total"] += 1
            pf["exact"] += 1 if m["exact"] else 0
            pf["fuzzy"] += 1 if m["fuzzy"] else 0
    total = sum(pf["total"] for pf in per_field.values())
    exact = sum(pf["exact"] for pf in per_field.values())
    fuzzy = sum(pf["fuzzy"] for pf in per_field.values())
    return {
        "per_field": per_field,
        "macro_exact": exact / total if total else 0.0,
        "macro_fuzzy": fuzzy / total if total else 0.0,
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()

    base = eval_corpus(texts, gt, offline_fields)
    prod = eval_corpus(texts, gt, offline_prod)
    ref = eval_corpus(texts, gt, offline_ref)

    # GATE 1 — port fidelity: prod == ref per cert per field.
    mismatches = []
    for stem, text in texts.items():
        if stem not in gt:
            continue
        p, r = offline_prod(text), offline_ref(text)
        for f in EVAL_FIELDS:
            if p[f] != r[f]:
                mismatches.append((stem, f, p[f], r[f]))

    # Per-cert organizer/nomor: fix & regress prod vs baseline.
    fixes, regresses = [], []
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        for field in ("penyelenggara_kegiatan", "nomor_bukti_fisik_nomor_sertifikasi"):
            gv = (row.get(field) or "").strip()
            if not gv or gv == "-":
                continue
            b0 = match_field(gv, offline_fields(text).get(field), field)
            v0 = match_field(gv, offline_prod(text).get(field), field)
            if not b0["exact"] and v0["exact"]:
                fixes.append((stem, field, offline_prod(text).get(field), gv))
            if b0["exact"] and not v0["exact"]:
                regresses.append((stem, field, offline_prod(text).get(field), gv))

    regress_fields = [
        f for f in EVAL_FIELDS
        if prod["per_field"][f]["exact"] < base["per_field"][f]["exact"]
    ]

    org_p = prod["per_field"]["penyelenggara_kegiatan"]
    nom_p = prod["per_field"]["nomor_bukti_fisik_nomor_sertifikasi"]
    fidelity_ok = not mismatches
    no_regress = not regress_fields
    gate = fidelity_ok and no_regress

    org_b = base["per_field"]["penyelenggara_kegiatan"]
    nom_b = base["per_field"]["nomor_bukti_fisik_nomor_sertifikasi"]
    print(f"Baseline (produksi current): MACRO exact {base['macro_exact']*100:.1f}% | organizer {org_b['exact']/org_b['total']*100:.1f}% | nomor {nom_b['exact']/nom_b['total']*100:.1f}%")
    print(f"PROD path:  MACRO exact {prod['macro_exact']*100:.1f}% fuzzy {prod['macro_fuzzy']*100:.1f}%")
    print(f"REF replica:MACRO exact {ref['macro_exact']*100:.1f}% fuzzy {ref['macro_fuzzy']*100:.1f}%")
    print(f"GATE1 fidelity prod==ref: {len(mismatches)} mismatch")
    for s, f, p, r in mismatches[:10]:
        print(f"  {s} [{f}]\n    prod: {p!r}\n    ref:  {r!r}")
    print(f"Organizer exact: {org_b['exact']/org_b['total']*100:.1f}% -> {org_p['exact']/org_p['total']*100:.1f}% ({org_p['exact']}/{org_p['total']})")
    print(f"Nomor exact:     {nom_b['exact']/nom_b['total']*100:.1f}% -> {nom_p['exact']/nom_p['total']*100:.1f}% ({nom_p['exact']}/{nom_p['total']})")
    print(f"Fixes: {len(fixes)} | Regresses: {len(regresses)} | regress fields: {regress_fields or 'tidak ada'}")
    print(f"VERDICT: {'GATE PASS' if gate else 'GATE FAIL'}")
    for stem, field, ev, gv in fixes:
        print(f"  FIX {stem} [{field.split('_')[0]}]: {ev!r} | GT: {gv!r}")
    for stem, field, ev, gv in regresses:
        print(f"  REGRESS {stem}: {ev!r} | GT: {gv!r}")

    md = [
        "# PROD-002 — Re-eval Port Produksi Normalisasi Organizer & Nomor",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        "baseline = offline_fields (produksi current) | 0 LLM call | flag ENABLE_ORGANIZER_NORMALIZATION (default OFF)",
        "",
        "## Hasil",
        "",
        "| Metrik | baseline (produksi current) | PROD path | REF replica |",
        "|---|---|---|---|",
    ]
    for f in EVAL_FIELDS:
        b, p, r = base["per_field"][f], prod["per_field"][f], ref["per_field"][f]
        md.append(
            f"| {f} exact | {b['exact']/b['total']*100 if b['total'] else 0:.1f}% | "
            f"{p['exact']/p['total']*100 if p['total'] else 0:.1f}% | "
            f"{r['exact']/r['total']*100 if r['total'] else 0:.1f}% |"
        )
    md += [
        f"| MACRO exact | {base['macro_exact']*100:.1f}% | {prod['macro_exact']*100:.1f}% | {ref['macro_exact']*100:.1f}% |",
        "",
        "## Verdict",
        "",
        f"**{'GATE PASS' if gate else 'GATE FAIL'}** — port fidelity prod==ref: "
        f"{'OK (0 mismatch)' if fidelity_ok else f'{len(mismatches)} mismatch'}; "
        f"no-regress vs baseline: {regress_fields or 'tidak ada'}.",
        "",
        "> Port spec (handoff v29 + KOREKSI R3): KEEP R0/PREFIX_HELD/R2/R3/R6 + F1 alias "
        "+ F3 BEM FKM + nomor D/E; SKIP R1/R4 (2 fix dikorbankan, 0 risiko); DROP R5. "
        "KOREKSI: R3 (strip sampai 'oleh') BUKAN dead code — ablation OOD diukur pre-ORG-004 "
        "tanpa lapisan alias; di port final R3 membuka alias F1 APHSA (1952296/2030335 = 2 fix). "
        "R1 = Rasio_Faiz (suffix faculty), R4 = 2955331 (date suffix).",
        "",
        "## Fix vs baseline (wrong -> exact)",
        "",
        "| stem | field | PROD | GT |",
        "|---|---|---|---|",
    ]
    for stem, field, ev, gv in fixes:
        md.append(f"| {stem} | {field} | {ev} | {gv} |")
    md += ["", "## Regress vs baseline (exact -> wrong)", ""]
    md += [f"| {s} | {f} | {e} | {g} |" for s, f, e, g in regresses] or ["tidak ada"]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(md))

    with open(os.path.join(OUT_DIR, "summary_prod_port.json"), "w") as f:
        json.dump({
            "baseline": base, "prod": prod, "ref": ref, "variant": prod,
            "mismatches": mismatches, "fixes": fixes, "regresses": regresses,
            "regress_fields": regress_fields, "pass_gate": gate,
            "macro_avg": {"exact_acc": prod["macro_exact"], "fuzzy_acc": prod["macro_fuzzy"]},
            "prod_rules": sorted(PROD_RULES),
            "gt": os.path.basename(GT_CSV), "matcher": "v2",
        }, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_prod_port.json")


if __name__ == "__main__":
    main()
