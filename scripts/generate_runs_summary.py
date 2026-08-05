"""Generate docs/report/runs_summary.md + .csv dari tests/benchmark_runs/.

Registry ringkas semua benchmark run + angka otoritatif untuk jalur context
loading sesi berikutnya: handoff_v10.md -> runs_summary -> experiments_ledger
-> codegraph. Idempotent & toleran terhadap format run lama (ner/hybrid/v3).

Usage:
  uv run python scripts/generate_runs_summary.py
"""

import csv
import json
import os
import re

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNS_ROOT = os.path.join(REPO, "tests", "benchmark_runs")
OUT_MD = os.path.join(REPO, "docs", "report", "runs_summary.md")
OUT_CSV = os.path.join(REPO, "docs", "report", "runs_summary.csv")
N_CERTS = 74

FIELD_LABELS = {
    "nama_kegiatan_sertifikasi": "nama_kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi": "nomor",
    "penyelenggara_kegiatan": "organizer",
    "waktu_mulai_pelaksanaan": "tanggal_mulai",
    "waktu_selesai_pelaksanaan": "tanggal_selesai",
    "tingkat": "tingkat",
}

# Run yang punya deskripsi kurasi (muncul di seksi "Authoritative runs").
AUTHORITATIVE = {
    "run_20260728_131835": "Baseline corpus produksi (teks RapidOCR+Tesseract, 74 txt)",
    "run_llm_v4_20260804_115212": "v8 f_bias winner lama (GT final fixed_v8)",
    "run_llm_v4_20260805_163541": "v9 organizer_v2 + router fix (GT v8)",
    "run_llm_v4_20260805_163541 (reval)": "v9 winner re-baseline GT v9 + matcher v2",
    "ocr_experiment/baseline_rapid": "OCR baseline: RapidOCR only (host)",
    "ocr_experiment/baseline_rapid_tess": "OCR baseline produksi-equivalent (RapidOCR+Tesseract)",
    "ocr_experiment/trial_a_paddle26": "OCR trial: paddleocr 2.9 + paddle 2.6 (GATE FAIL)",
    "ocr_experiment/trial_a_easyocr": "OCR trial: EasyOCR CPU max-side 960 (GATE FAIL)",
    "ocr_experiment/trial_a_easyocr_gpu": "OCR trial: EasyOCR GPU full-res (GATE FAIL, not adopted)",
}

# f_bias winner utk seksi "f_bias winner — field exact".
WINNER_RUN = "run_llm_v4_20260805_163541"


def _date_from_name(name: str) -> str:
    m = re.search(r"(\d{8})_(\d{6})", name)
    if m:
        d = m.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return ""


def _kind(name: str) -> str:
    if name.startswith("run_llm_v4"):
        return "llm_v4"
    if name.startswith("run_llm_v3"):
        return "llm_v3"
    if name.startswith("run_hybrid_pp"):
        return "hybrid_pp"
    if name.startswith("run_fulltext_llm"):
        return "llm_fulltext"
    if name.startswith("run_ner_v1"):
        return "ner_v1"
    if name.startswith("run_20260728"):
        return "baseline_regex"
    if name.startswith("layout_texts"):
        return "corpus"
    return "other"


def _pct(v) -> str:
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _macro(s: dict):
    try:
        return float(s["macro_avg"]["exact_acc"])
    except Exception:
        return None


def _field_acc(s: dict, field: str):
    try:
        return float(s[field]["exact_acc"])
    except Exception:
        return None


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _best_variant_summary(run_dir: str):
    """Pilih summary_variant_*.json representatif: f_bias > tingkat tertinggi > pertama."""
    if not os.path.isdir(run_dir):
        return None, None
    files = sorted(
        f for f in os.listdir(run_dir) if f.startswith("summary_variant_") and f.endswith(".json")
    )
    if not files:
        return None, None
    variants = [f[len("summary_variant_"):-len(".json")] for f in files]
    chosen = "f_bias" if "f_bias" in variants else None
    if chosen is None:
        best, best_t = variants[0], -1.0
        for v in variants:
            s = _load(os.path.join(run_dir, f"summary_variant_{v}.json"))
            t = _macro(s) if s else 0
            if t is not None and t > best_t:
                best, best_t = v, t
        chosen = best
    return chosen, _load(os.path.join(run_dir, f"summary_variant_{chosen}.json"))


def _any_summary(run_dir: str):
    """Untuk run non-variant: cari summary_*.json dengan macro_avg, atau
    results.json['summary'] (run lama baseline/ner)."""
    if not os.path.isdir(run_dir):
        return None
    for f in sorted(os.listdir(run_dir)):
        if f.startswith("summary_") and f.endswith(".json"):
            s = _load(os.path.join(run_dir, f))
            if s and isinstance(s, dict) and "macro_avg" in s:
                return f, s
    r = _load(os.path.join(run_dir, "results.json"))
    if isinstance(r, dict) and isinstance(r.get("summary"), dict) and "macro_avg" in r["summary"]:
        return "results.json", r["summary"]
    return None, None


def _token_usage(run_dir: str, variant: str | None):
    for cand in (
        [f"token_usage_{variant}.json"] if variant else []
    ) + ["token_usage.json", "token_usage_hybrid_llm.json"]:
        t = _load(os.path.join(run_dir, cand))
        if t and "total_tokens" in t:
            return t
    return None


def _router_stats(run_dir: str):
    r = _load(os.path.join(run_dir, "router_decisions.json"))
    if not r:
        return None
    dec = [x for x in r if x.get("decision")]
    if not dec:
        return {"coverage": 0, "precision": 0.0}
    prec = sum(1 for x in dec if x.get("exact")) / len(dec)
    return {"coverage": len(dec), "precision": prec}


def scan_run(run_dir: str) -> dict:
    name = os.path.basename(run_dir)
    rec = {
        "run_dir": name,
        "date": _date_from_name(name),
        "kind": _kind(name),
        "model": "",
        "prompt_version": "",
        "gt": "",
        "router": "",
        "organizer": "",
        "variant": "",
        "tingkat": "—",
        "macro": "—",
        "tokens_cert": "—",
        "calls": "—",
        "latency_ms": "—",
        "notes": "",
    }
    cfg = _load(os.path.join(run_dir, "config.json"))
    if cfg:
        rec["model"] = cfg.get("model", "")
        rec["prompt_version"] = cfg.get("prompt_version", "")
        rec["gt"] = cfg.get("gt_version", "") or os.path.basename(cfg.get("csv_path", ""))
        rec["router"] = cfg.get("router", "")
        rec["organizer"] = cfg.get("organizer_variant", "")

    variant, s = _best_variant_summary(run_dir)
    if s is None:
        _, s = _any_summary(run_dir)
    if s:
        rec["macro"] = _pct(_macro(s))
        rec["tingkat"] = _pct(_field_acc(s, "tingkat"))
    if variant:
        rec["variant"] = variant

    tok = _token_usage(run_dir, variant)
    if tok:
        rec["calls"] = str(tok.get("total_calls", "—"))
        tt = tok.get("total_tokens")
        rec["tokens_cert"] = str(round(tt / N_CERTS)) if isinstance(tt, (int, float)) else "—"
        rec["latency_ms"] = str(tok.get("avg_latency_ms", "—"))

    rs = _router_stats(run_dir)
    if rs and rs["coverage"]:
        rec["notes"] = f"router {rs['coverage']}/74 @{rs['precision'] * 100:.0f}%"

    return rec


def scan_ocr_trials() -> list[dict]:
    ocr_root = os.path.join(RUNS_ROOT, "ocr_experiment")
    recs = []
    if not os.path.isdir(ocr_root):
        return recs
    for name in sorted(os.listdir(ocr_root)):
        d = os.path.join(ocr_root, name)
        if not os.path.isdir(d):
            continue
        meta = _load(os.path.join(d, "ocr_meta.json"))
        ev = _load(os.path.join(d, "eval.json"))
        rec = {
            "run_dir": f"ocr_experiment/{name}",
            "date": "",
            "kind": "ocr_trial",
            "model": (meta or {}).get("engine", ""),
            "prompt_version": "",
            "gt": "fixed_v8",
            "router": "",
            "organizer": "",
            "variant": "",
            "tingkat": "—",
            "macro": "—",
            "tokens_cert": "—",
            "calls": "—",
            "latency_ms": "—",
            "notes": "",
        }
        if meta:
            rec["date"] = (meta.get("created") or "")[:10]
            lat = meta.get("latency") or {}
            if lat:
                rec["latency_ms"] = str(round(lat.get("avg_seconds", 0) * 1000))
            rec["notes"] = f"scan={meta.get('scan_count')} emb={meta.get('embedded_count', '?')}"
        if ev:
            scan = ev.get("scan") or {}
            rec["macro"] = _pct((scan.get("macro_avg") or {}).get("exact_acc"))
            org = (scan.get("penyelenggara_kegiatan") or {}).get("exact_acc")
            nom = (scan.get("nomor_bukti_fisik_nomor_sertifikasi") or {}).get("exact_acc")
            rec["notes"] = (rec["notes"] + "; " if rec["notes"] else "") + (
                f"scan org {_pct(org)} nomor {_pct(nom)}"
            )
        recs.append(rec)
    return recs


def main():
    runs = []
    if os.path.isdir(RUNS_ROOT):
        for name in sorted(os.listdir(RUNS_ROOT)):
            d = os.path.join(RUNS_ROOT, name)
            if not os.path.isdir(d) or _kind(name) == "corpus":
                continue
            runs.append(scan_run(d))
    ocr = scan_ocr_trials()
    runs += ocr
    runs = [r for r in runs if r["kind"] != "other" or r["macro"] != "—"]

    # ---- MD ----
    lines = []
    lines.append("# Benchmark Runs Summary")
    lines.append("")
    lines.append("> Registry ringkas dari `tests/benchmark_runs/`. Baca bersama "
                 "`docs/handoff_v10.md` + `docs/experiments_ledger.md` + codegraph "
                 "untuk context lengkap sesi eksperimen.")
    lines.append("> Regenerate: `uv run python scripts/generate_runs_summary.py`")
    lines.append("")
    lines.append(f"**Total run terindeks:** {len(runs)} (korpus `layout_texts_*` di-skip). "
                 f"Dataset 74 sertifikat.")
    lines.append("")

    lines.append("## Authoritative runs")
    lines.append("")
    lines.append("| Run | Deskripsi | Tingkat | MACRO | Tok/cert | Calls |")
    lines.append("|---|---|---|---|---|---|")
    for key, desc in AUTHORITATIVE.items():
        rec = next((r for r in runs if r["run_dir"] == key), None)
        if key.endswith(" (reval)"):
            reval = _load(os.path.join(RUNS_ROOT, key[:-len(" (reval)")], "summary_gt_v9_reval.json"))
            if reval:
                ma = reval.get("macro_avg", {})
                tk = (reval.get("fields", {}).get("tingkat", {})).get("exact_acc")
                lines.append(f"| `{key}` | {desc} | {_pct(tk)} | {_pct(ma.get('exact_acc'))} | — | — |")
                continue
            lines.append(f"| `{key}` | {desc} | — | — | — | — |")
            continue
        if rec is None:
            lines.append(f"| `{key}` | {desc} | — | — | — | — |")
            continue
        lines.append(f"| `{key}` | {desc} | {rec['tingkat']} | {rec['macro']} | "
                     f"{rec['tokens_cert']} | {rec['calls']} |")
    lines.append("")

    # f_bias winner field metrics
    win = next((r for r in runs if r["run_dir"] == WINNER_RUN), None)
    if win:
        s = _load(os.path.join(RUNS_ROOT, win["run_dir"], "summary_variant_f_bias.json"))
        lines.append(f"## f_bias winner — field exact ({WINNER_RUN})")
        lines.append("")
        lines.append("| Field | exact | fuzzy |")
        lines.append("|---|---|---|")
        for field, label in FIELD_LABELS.items():
            d = (s or {}).get(field, {})
            lines.append(f"| {label} | {_pct(d.get('exact_acc'))} | {_pct(d.get('fuzzy_acc'))} |")
        ma = (s or {}).get("macro_avg", {})
        lines.append(f"| **MACRO** | {_pct(ma.get('exact_acc'))} | {_pct(ma.get('fuzzy_acc'))} |")
        lines.append("")

    # GT v9 + matcher v2 re-baseline field metrics
    reval = _load(os.path.join(RUNS_ROOT, WINNER_RUN, "summary_gt_v9_reval.json"))
    if reval:
        lines.append(f"## GT v9 + matcher v2 re-baseline — field exact ({WINNER_RUN})")
        lines.append("")
        lines.append("> Re-evaluasi extracted_fields vs Ground_Truth_Sertifikat_v9.csv + "
                     "matcher v2 (handoff v12). Angka GT v8/matcher v1: MACRO exact 58.9%.")
        lines.append("")
        lines.append("| Field | exact | fuzzy |")
        lines.append("|---|---|---|")
        for field, label in FIELD_LABELS.items():
            d = reval.get("fields", {}).get(field, {})
            lines.append(f"| {label} | {_pct(d.get('exact_acc'))} | {_pct(d.get('fuzzy_acc'))} |")
        rma = reval.get("macro_avg", {})
        lines.append(f"| **MACRO** | {_pct(rma.get('exact_acc'))} | {_pct(rma.get('fuzzy_acc'))} |")
        lines.append("")

    # OCR trials
    ocr_recs = [r for r in runs if r["kind"] == "ocr_trial"]
    if ocr_recs:
        lines.append("## OCR experiment (subset scan, field-eval exact)")
        lines.append("")
        lines.append("| Run | Engine | MACRO scan | latency | notes |")
        lines.append("|---|---|---|---|---|")
        for r in ocr_recs:
            lines.append(f"| `{r['run_dir']}` | {r['model']} | {r['macro']} | "
                         f"{r['latency_ms']}ms | {r['notes']} |")
        lines.append("")

    # Registry
    lines.append("## Full run registry")
    lines.append("")
    lines.append("| run_dir | date | kind | variant | tingkat | macro | tok/cert | calls | router | notes |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        lines.append(f"| `{r['run_dir']}` | {r['date']} | {r['kind']} | {r['variant']} | "
                     f"{r['tingkat']} | {r['macro']} | {r['tokens_cert']} | {r['calls']} | "
                     f"{r['router']} | {r['notes']} |")
    lines.append("")

    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines).rstrip() + "\n")

    # ---- CSV ----
    cols = ["run_dir", "date", "kind", "model", "prompt_version", "gt", "router",
            "organizer", "variant", "tingkat", "macro", "tokens_cert", "calls",
            "latency_ms", "notes"]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in runs:
            w.writerow(r)

    print(f"runs indexed: {len(runs)}")
    print(f"  md  -> {OUT_MD}")
    print(f"  csv -> {OUT_CSV}")
    n_failed = sum(1 for r in runs if r["macro"] == "—" and r["kind"] not in ("ocr_trial",))
    print(f"  runs tanpa macro (older/no summary): {n_failed}")


if __name__ == "__main__":
    main()
