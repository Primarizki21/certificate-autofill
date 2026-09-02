"""ORG-TESS-V8-001 validation: CV, bootstrap, OOD, anchors, safety net.

This report-only harness consumes frozen baseline and isolated v8 eval JSONs. It
never changes production code or the frozen matcher/ground truth.
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backend"))

from tests.evaluation_framework import load_csv
from tests.matchers import match_field
from tests.organizer_tess_v8 import extract_organizer_v8_result
from app.services.form_mapper import field_needs_review

GT_PATH = REPO / "Ground_Truth_Sertifikat_v9.csv"
PURE_BASE = REPO / "tests/benchmark_runs/ocr_experiment/tesseract_pure_all74_v4/eval.json"
PURE_V8 = REPO / "tests/benchmark_runs/ocr_experiment/tesseract_pure_all74_org_tess_v8/eval.json"
PRIMARY_BASE = REPO / "tests/benchmark_runs/ocr_experiment/tesseract_primary_v4/eval.json"
PRIMARY_V8 = REPO / "tests/benchmark_runs/ocr_experiment/tesseract_primary_v4_org_tess_v8/eval.json"
PURE_TEXTS = REPO / "tests/benchmark_runs/ocr_experiment/tesseract_pure_all74_v4/extracted_texts"
PRIMARY_TEXTS = REPO / "tests/benchmark_runs/ocr_experiment/tesseract_primary_v4/extracted_texts"
MODULE_PATH = REPO / "tests/organizer_tess_v8.py"
OUT_DIR = REPO / "tests/benchmark_runs/ocr_experiment/org_tess_v8_validation"
OUT_JSON = OUT_DIR / "validation.json"
OUT_MD = REPO / "docs/report/org_tess_v8_validation.md"
SEED = 42
N_FOLDS = 5
N_BOOT = 1000


def load_eval(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def detail_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["_meta"]["stem"]: item for item in payload["detailed_results"]}


def organizer_exact(item: dict[str, Any]) -> bool:
    return bool(item["penyelenggara_kegiatan"]["exact"])


def assign_stratified_folds(stems: list[str], details: dict[str, dict[str, Any]]) -> dict[str, int]:
    rng = random.Random(SEED)
    strata: dict[str, list[str]] = defaultdict(list)
    for stem in stems:
        meta = details[stem]["_meta"]
        strata["scan" if meta.get("scan") else "embedded"].append(stem)
    assignment: dict[str, int] = {}
    for values in strata.values():
        rng.shuffle(values)
        for index, stem in enumerate(values):
            assignment[stem] = index % N_FOLDS
    return assignment


def fold_precision(
    details: dict[str, dict[str, Any]],
    folds: dict[str, int],
) -> dict[str, Any]:
    by_source: dict[str, dict[int, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for stem, item in details.items():
        source = item["penyelenggara_kegiatan"]["source"]
        by_source[source][folds[stem]].append(organizer_exact(item))
    result: dict[str, Any] = {}
    for source, fold_values in sorted(by_source.items()):
        fold_rows = []
        for fold in range(N_FOLDS):
            values = fold_values.get(fold, [])
            fold_rows.append({
                "fold": fold + 1,
                "n": len(values),
                "precision": round(sum(values) / len(values), 4) if values else None,
            })
        all_values = [value for values in fold_values.values() for value in values]
        observed = [row["precision"] for row in fold_rows if row["precision"] is not None]
        result[source] = {
            "n": len(all_values),
            "exact": sum(all_values),
            "precision": round(sum(all_values) / len(all_values), 4) if all_values else None,
            "min_fold_precision": min(observed) if observed else None,
            "low_n": len(all_values) < 5,
            "folds": fold_rows,
        }
    return result


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def bootstrap(values: list[float], paired_deltas: list[float]) -> dict[str, Any]:
    rng = random.Random(SEED)
    means: list[float] = []
    delta_means: list[float] = []
    for _ in range(N_BOOT):
        sample = [values[rng.randrange(len(values))] for _ in values]
        delta_sample = [paired_deltas[rng.randrange(len(paired_deltas))] for _ in paired_deltas]
        means.append(sum(sample) / len(sample))
        delta_means.append(sum(delta_sample) / len(delta_sample))
    return {
        "n_bootstrap": N_BOOT,
        "seed": SEED,
        "organizer_exact_mean": round(sum(values) / len(values), 4),
        "organizer_exact_ci95": [round(percentile(means, 0.025), 4), round(percentile(means, 0.975), 4)],
        "delta_mean": round(sum(paired_deltas) / len(paired_deltas), 4),
        "delta_ci95": [round(percentile(delta_means, 0.025), 4), round(percentile(delta_means, 0.975), 4)],
    }


def replace_entities(text: str) -> str:
    return re.sub(
        r"Universitas Airlangga|UNAIR",
        lambda match: "Universitas Negeri Surabaya" if match.group(0).startswith("Universitas") else "UNS",
        text,
        flags=re.IGNORECASE,
    )


def inject_noise(text: str, rate: float, rng: random.Random) -> str:
    confusion = {"5": "S", "S": "5", "8": "B", "B": "8", "0": "O", "O": "0", "1": "I", "I": "1"}
    chars = list(text)
    eligible = [index for index, char in enumerate(chars) if char.upper() in confusion]
    count = round(len(eligible) * rate)
    for index in rng.sample(eligible, min(count, len(eligible))):
        chars[index] = confusion[chars[index].upper()]
    return "".join(chars)


def ood_results(text_dir: Path, gt: dict[str, dict[str, str]]) -> dict[str, Any]:
    stems = sorted(gt)
    entity_rows = []
    noise_rows = []
    for stem in stems:
        path = text_dir / f"{stem}.txt"
        raw = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")).strip()
        gt_org = gt[stem]["penyelenggara_kegiatan"]
        mutated_gt = replace_entities(gt_org)
        mutated = replace_entities(raw)
        entity_pred = extract_organizer_v8_result(mutated).value or ""
        entity_match = match_field(mutated_gt, entity_pred, "penyelenggara_kegiatan")
        entity_rows.append(bool(entity_match["exact"]))
        for rate in (0.10, 0.25, 0.50):
            noisy = inject_noise(raw, rate, random.Random(SEED + int(rate * 1000) + len(stem)))
            pred = extract_organizer_v8_result(noisy).value or ""
            match = match_field(gt_org, pred, "penyelenggara_kegiatan")
            noise_rows.append({"rate": rate, "exact": bool(match["exact"])})
    return {
        "entity_mutation": {
            "n": len(entity_rows),
            "exact": sum(entity_rows),
            "exact_acc": round(sum(entity_rows) / len(entity_rows), 4) if entity_rows else 0.0,
        },
        "ocr_noise": {
            str(rate): {
                "n": sum(1 for row in noise_rows if row["rate"] == rate),
                "exact": sum(1 for row in noise_rows if row["rate"] == rate and row["exact"]),
                "exact_acc": round(
                    sum(1 for row in noise_rows if row["rate"] == rate and row["exact"])
                    / sum(1 for row in noise_rows if row["rate"] == rate),
                    4,
                ),
            }
            for rate in (0.10, 0.25, 0.50)
        },
    }


def anchor_audit(gt: dict[str, dict[str, str]]) -> dict[str, Any]:
    source = MODULE_PATH.read_text(encoding="utf-8")
    event_literals = sorted({name.strip() for name in (row["nama_kegiatan_sertifikasi"] for row in gt.values()) if len(name.strip()) >= 8 and name.strip().upper() in source.upper()})
    required_anchors = {
        "indonesian_organizer_phrase": "diselenggarakan\\s*oleh" in source,
        "english_organizer_phrase": "organized\\s*by" in source,
        "signer_role_anchor": "_ROLE_RE" in source,
        "date_anchor": "_DATE_TOKEN_RE" in source,
        "number_guard": "_NUMBER_PREFIX_RE" in source,
    }
    return {
        "event_literals_found": event_literals,
        "event_literal_count": len(event_literals),
        "required_structural_anchors": required_anchors,
        "pass": not event_literals and all(required_anchors.values()),
    }


def safety_net(v8_details: dict[str, dict[str, Any]]) -> dict[str, Any]:
    mismatch = 0
    protocol_review_mismatch = 0
    runtime_review_mismatch = 0
    protocol_review = 0
    runtime_review = 0
    for item in v8_details.values():
        field = item["penyelenggara_kegiatan"]
        is_mismatch = not field["exact"]
        low_protocol = field["confidence"] < 0.85 or not field["pred"]
        low_runtime = field_needs_review("penyelenggara_kegiatan", field["pred"], field["confidence"])
        mismatch += is_mismatch
        protocol_review += low_protocol
        runtime_review += low_runtime
        protocol_review_mismatch += is_mismatch and low_protocol
        runtime_review_mismatch += is_mismatch and low_runtime
    return {
        "n": len(v8_details),
        "mismatch": mismatch,
        "protocol_threshold": 0.85,
        "protocol_review": protocol_review,
        "protocol_review_recall": round(protocol_review_mismatch / mismatch, 4) if mismatch else 1.0,
        "runtime_threshold": 0.80,
        "runtime_review": runtime_review,
        "runtime_review_recall": round(runtime_review_mismatch / mismatch, 4) if mismatch else 1.0,
    }


def gate_comparison(base: dict[str, Any], v8: dict[str, Any]) -> dict[str, Any]:
    fields = ["nomor_bukti_fisik_nomor_sertifikasi", "waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]
    base_details = detail_map(base)
    v8_details = detail_map(v8)
    row_regressions = {field: 0 for field in fields}
    aggregate = {}
    for field in fields:
        base_count = sum(item[field]["exact"] for item in base_details.values())
        v8_count = sum(item[field]["exact"] for item in v8_details.values())
        aggregate[field] = {"baseline": base_count, "v8": v8_count, "delta": v8_count - base_count}
        row_regressions[field] = sum(item[field]["exact"] and not v8_details[stem][field]["exact"] for stem, item in base_details.items())
    scan_base = base["framework_5field"]["scan"]["macro_avg"]["exact_acc"]
    scan_v8 = v8["framework_5field"]["scan"]["macro_avg"]["exact_acc"]
    return {
        "non_organizer_fields": aggregate,
        "row_level_regressions": row_regressions,
        "scan_framework_baseline": scan_base,
        "scan_framework_v8": scan_v8,
        "scan_framework_no_regression": scan_v8 >= scan_base,
        "date_number_no_regression": all(row["delta"] >= 0 for row in aggregate.values()) and not any(row_regressions.values()),
    }


def corpus_report(name: str, base: dict[str, Any], v8: dict[str, Any], text_dir: Path, gt: dict[str, dict[str, str]]) -> dict[str, Any]:
    base_details = detail_map(base)
    v8_details = detail_map(v8)
    stems = sorted(v8_details)
    folds = assign_stratified_folds(stems, v8_details)
    exact_values = [float(organizer_exact(v8_details[stem])) for stem in stems]
    deltas = [float(organizer_exact(v8_details[stem])) - float(organizer_exact(base_details[stem])) for stem in stems]
    return {
        "name": name,
        "n": len(stems),
        "baseline_exact": sum(organizer_exact(base_details[stem]) for stem in stems),
        "v8_exact": sum(organizer_exact(v8_details[stem]) for stem in stems),
        "baseline_framework_scan": base["framework_5field"]["scan"]["macro_avg"]["exact_acc"],
        "v8_framework_scan": v8["framework_5field"]["scan"]["macro_avg"]["exact_acc"],
        "cv": {
            "folds": [
                {
                    "fold": fold + 1,
                    "n": sum(folds[stem] == fold for stem in stems),
                    "baseline_exact": sum(organizer_exact(base_details[stem]) for stem in stems if folds[stem] == fold),
                    "v8_exact": sum(organizer_exact(v8_details[stem]) for stem in stems if folds[stem] == fold),
                }
                for fold in range(N_FOLDS)
            ],
            "source_precision": fold_precision(v8_details, folds),
        },
        "bootstrap": bootstrap(exact_values, deltas),
        "ood": ood_results(text_dir, gt),
        "safety_net": safety_net(v8_details),
        "gates": gate_comparison(base, v8),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# ORG-TESS-V8-001 — Empirical Validation",
        "",
        "> Dataset frozen: `Ground_Truth_Sertifikat_v9.csv`; evaluator: matcher v2; seed: 42; bootstrap: 1000x.",
        "> Scope: staging-only Tesseract organizer candidate. Production backend unchanged.",
        "",
        "## Gate Summary",
        "",
        "| Corpus | Baseline exact | v8 exact | Gate | Scan framework no-regression | Date/number no-regression |",
        "|---|---:|---:|---|---|---|",
    ]
    for name, corpus in result["corpora"].items():
        gates = corpus["gates"]
        threshold = 45 if name == "pure" else 50
        gate = corpus["v8_exact"] >= threshold
        lines.append(f"| {name} | {corpus['baseline_exact']}/74 | {corpus['v8_exact']}/74 | {'PASS' if gate else 'FAIL'} (≥{threshold}) | {'PASS' if gates['scan_framework_no_regression'] else 'FAIL'} | {'PASS' if gates['date_number_no_regression'] else 'FAIL'} |")
    lines += ["", "## 1. Stratified 5-Fold CV", "", "Folds are stratified by scan versus embedded corpus and assigned deterministically. Rules are fixed; no fold is used to refit the extractor.", ""]
    for name, corpus in result["corpora"].items():
        lines += [f"### {name}", "", "| Fold | N | Baseline exact | v8 exact |", "|---:|---:|---:|---:|"]
        lines += [f"| {row['fold']} | {row['n']} | {row['baseline_exact']} | {row['v8_exact']} |" for row in corpus["cv"]["folds"]]
        lines += ["", "| Rule/source | N | Exact | Precision | Min-fold precision | Low-N (<5) |", "|---|---:|---:|---:|---:|---|"]
        for source, stats in corpus["cv"]["source_precision"].items():
            min_fold = "n/a" if stats["min_fold_precision"] is None else f"{stats['min_fold_precision']:.2%}"
            lines.append(f"| `{source}` | {stats['n']} | {stats['exact']} | {stats['precision']:.2%} | {min_fold} | {'YES' if stats['low_n'] else 'NO'} |")
        lines.append("")
    lines += ["## 2. Bootstrap Confidence Interval", "", "| Corpus | Exact mean | 95% CI | Delta mean vs baseline | Delta 95% CI |", "|---|---:|---:|---:|---:|"]
    for name, corpus in result["corpora"].items():
        boot = corpus["bootstrap"]
        lines.append(f"| {name} | {boot['organizer_exact_mean']:.2%} | [{boot['organizer_exact_ci95'][0]:.2%}, {boot['organizer_exact_ci95'][1]:.2%}] | {boot['delta_mean']:.2%} | [{boot['delta_ci95'][0]:.2%}, {boot['delta_ci95'][1]:.2%}] |")
    lines += ["", "## 3. OOD Stress Test", "", "Entity mutation replaces Airlangga/UNAIR with Surabaya/UNS. OCR noise uses deterministic 5↔S, 8↔B, 0↔O, 1↔I substitutions.", ""]
    for name, corpus in result["corpora"].items():
        ood = corpus["ood"]
        lines += [f"### {name}", "", "| Probe | N | Exact | Accuracy |", "|---|---:|---:|---:|"]
        entity = ood["entity_mutation"]
        lines.append(f"| Entity mutation | {entity['n']} | {entity['exact']} | {entity['exact_acc']:.2%} |")
        for rate, row in ood["ocr_noise"].items():
            lines.append(f"| OCR noise {float(rate):.0%} | {row['n']} | {row['exact']} | {row['exact_acc']:.2%} |")
        lines.append("")
    anchor = result["anchor_audit"]
    lines += ["## 4. Structural Semantic Anchor Audit", "", f"- Event-title literals in extractor source: **{anchor['event_literal_count']}** ({', '.join(anchor['event_literals_found']) or 'none'}).", f"- Required anchors: `{anchor['required_structural_anchors']}`.", f"- Verdict: **{'PASS' if anchor['pass'] else 'FAIL'}**; rules use structural phrase, signer-role, date, and number guards.", "", "## 5. Calibrated Confidence & Safety Net", ""]
    for name, corpus in result["corpora"].items():
        safety = corpus["safety_net"]
        lines.append(f"- **{name}**: {safety['mismatch']} organizer mismatches; protocol threshold 0.85 flags {safety['protocol_review']}/{safety['n']} with recall {safety['protocol_review_recall']:.2%}; runtime threshold 0.80 flags {safety['runtime_review']}/{safety['n']} with recall {safety['runtime_review_recall']:.2%}.")
    lines += ["", "## Verdict", "", f"- Pure gate: **{'PASS' if result['gates']['pure'] else 'FAIL'}** (target ≥45/74).", f"- Primary gate: **{'PASS' if result['gates']['primary'] else 'FAIL'}** (target ≥50/74).", f"- Four-layer evidence is recorded above; failed gates remain staging knowledge and are not promoted to production.", ""]
    return "\n".join(lines)


def main() -> None:
    gt = {Path(row["nama_file"]).stem: row for row in load_csv(str(GT_PATH))}
    corpora = {
        "pure": corpus_report("pure", load_eval(PURE_BASE), load_eval(PURE_V8), PURE_TEXTS, gt),
        "primary": corpus_report("primary", load_eval(PRIMARY_BASE), load_eval(PRIMARY_V8), PRIMARY_TEXTS, gt),
    }
    anchor = anchor_audit(gt)
    gates = {
        "pure": corpora["pure"]["v8_exact"] >= 45,
        "primary": corpora["primary"]["v8_exact"] >= 50,
    }
    result = {"experiment": "ORG-TESS-V8-001", "corpora": corpora, "anchor_audit": anchor, "gates": gates}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({"gates": gates, "out_json": str(OUT_JSON), "out_md": str(OUT_MD)}, indent=2))


if __name__ == "__main__":
    main()
