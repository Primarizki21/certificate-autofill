"""Hybrid OCR per-field (DocTR dates+organizer / baseline nomor). EXPERIMENT ONLY.

EXP HYB-001 (handoff v14 → v15): DocTR naik organizer+dates tapi nomor hancur;
baseline RapidOCR+Tesseract menang nomor. Merge per-field di level
`dict[str, ExtractedValue]` (output `extract_certificate_fields`) SEBELUM
`map_fields_to_form`, pakai rule prioritas statis:

  tanggal_mulai/selesai : DocTR dulu, baseline fallback
  penyelenggara         : DocTR dulu, baseline fallback
  nomor                 : baseline dulu, DocTR fallback
  nama_kegiatan, role   : baseline dulu, DocTR fallback
  keyword/aux           : baseline dulu, DocTR fallback

Produksi `backend/` TIDAK disentuh. Evaluasi GT v9 + matcher v2
(tests.evaluation_framework + tests.matchers).

Subcommand:
  build : OCR 49 scan cert dengan DocTR -> extracted_texts/ (subprocess fresh,
          RLIMIT_AS 8GB, watchdog RSS — sama probe OCR-006).
  eval  : bandingkan baseline / doctr / hybrid / oracle-max pada subset stem.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "backend"))

from tests.ocr_engine import classify_manifest
from tests.evaluation_framework import (
    EVAL_FIELDS,
    aggregate_results,
    evaluate_row,
    load_csv,
    print_report,
)

MANIFEST = os.path.join(REPO, "tests", "layout_manifest.json")
GT_CSV = os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv")
RUNS_DIR = os.path.join(REPO, "tests", "benchmark_runs", "ocr_experiment")
BASELINE_DIR = os.path.join(RUNS_DIR, "baseline_rapid_tess", "extracted_texts")
MEM_CAP_GB = 8.0

# Field yang ekstraktor produksi isi (dari extract_certificate_fields).
DATE_FIELDS = ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan")
DOC_PRIORITY = {"penyelenggara_kegiatan"} | set(DATE_FIELDS)
BASE_PRIORITY = {
    "nomor_bukti_fisik_nomor_sertifikasi",
    "nama_kegiatan_sertifikasi",
    "raw_role",
    "has_kegiatan_keyword",
    "has_dekan_keyword",
    "has_direktur_kemahasiswaan_keyword",
}

# Field yang DIEVALUASI matcher (nama_kegiatan, dates, organizer, nomor).
EVAL = [f for f in EVAL_FIELDS]


def _read_text(path: str) -> str:
    with open(path) as f:
        return "\n".join(l for l in f.read().splitlines() if not l.startswith("#")).strip()


def extract_all(raw_text: str) -> dict:
    from app.services.field_extractor import extract_certificate_fields, ExtractedValue
    from app.services.organizer_v2 import extract_organizer_v2

    try:
        extracted = extract_certificate_fields(raw_text)
    except Exception:
        extracted = {}
    try:
        v2 = extract_organizer_v2(raw_text)
    except Exception:
        v2 = None
    if v2:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(v2, 0.84, "organizer_v2")
    extracted["full_text"] = ExtractedValue(raw_text, 1.0, "ocr_text")
    return extracted


def merge_fields(base: dict, doc: dict) -> dict:
    """Rule prioritas per-field. base = baseline, doc = DocTR."""
    out = dict(base)
    for field, doc_val in doc.items():
        base_val = out.get(field)
        if doc_val is None or doc_val.value is None:
            continue
        if base_val is None or base_val.value is None:
            out[field] = doc_val
            continue
        if field in DOC_PRIORITY:
            out[field] = doc_val
        # BASE_PRIORITY: pertahankan baseline.
    return out


def _safe_agg(results: list[dict]) -> dict:
    """aggregate_results crash kalau results kosong (ZeroDivisionError macro).
    Guard minimal untuk subset tanpa teks (mis. embedded tanpa DocTR)."""
    empty = {"total": 0, "exact": 0, "fuzzy": 0, "exact_acc": 0.0, "fuzzy_acc": 0.0,
             "avg_confidence": 0.0, "avg_wer": 0.0, "avg_cer": 0.0}
    if not results:
        return {f: dict(empty) for f in EVAL_FIELDS} | {"macro_avg": dict(empty)}
    return aggregate_results(results)


def eval_dir(texts_dir: str, stem_to_row: dict, stems: list[str]) -> dict:
    from app.services.form_mapper import map_fields_to_form

    results = []
    for stem in stems:
        row = stem_to_row.get(stem)
        if row is None:
            continue
        path = os.path.join(texts_dir, f"{stem}.txt")
        if not os.path.exists(path):
            continue
        raw = _read_text(path)
        extracted = extract_all(raw)
        mapped = map_fields_to_form(extracted, tahun_akademik="2024/2025", bukti_fisik="Sertifikat")
        fr = evaluate_row(mapped, row)
        fr["_meta"] = {"stem": stem}
        results.append(fr)
    return _safe_agg(results)


def eval_hybrid(base_dir: str, doc_dir: str, stem_to_row: dict, stems: list[str]) -> dict:
    from app.services.form_mapper import map_fields_to_form

    results = []
    for stem in stems:
        row = stem_to_row.get(stem)
        if row is None:
            continue
        base_raw = _read_text(os.path.join(base_dir, f"{stem}.txt"))
        doc_path = os.path.join(doc_dir, f"{stem}.txt")
        doc_raw = _read_text(doc_path) if os.path.exists(doc_path) else ""
        base_ex = extract_all(base_raw)
        doc_ex = extract_all(doc_raw)
        merged = merge_fields(base_ex, doc_ex)
        mapped = map_fields_to_form(merged, tahun_akademik="2024/2025", bukti_fisik="Sertifikat")
        fr = evaluate_row(mapped, row)
        fr["_meta"] = {"stem": stem}
        results.append(fr)
    return _safe_agg(results)


def eval_oracle(base_dir: str, doc_dir: str, stem_to_row: dict, stems: list[str]) -> dict:
    """Ceiling: per field ambil hasil yang exact jika salah satu exact. Runtime-irrelevant."""
    from app.services.form_mapper import map_fields_to_form

    results = []
    for stem in stems:
        row = stem_to_row.get(stem)
        if row is None:
            continue
        base_ex = extract_all(_read_text(os.path.join(base_dir, f"{stem}.txt")))
        doc_path = os.path.join(doc_dir, f"{stem}.txt")
        doc_ex = extract_all(_read_text(doc_path) if os.path.exists(doc_path) else "")
        best = dict(base_ex)
        for field in EVAL:
            bv = base_ex.get(field)
            dv = doc_ex.get(field)
            if field in DOC_PRIORITY:
                best[field] = (dv if dv and dv.value else bv)
            else:
                best[field] = (bv if bv and bv.value else dv)
        mapped = map_fields_to_form(best, tahun_akademik="2024/2025", bukti_fisik="Sertifikat")
        fr = evaluate_row(mapped, row)
        fr["_meta"] = {"stem": stem}
        results.append(fr)
    return _safe_agg(results)


def cmd_build(args) -> None:
    from tests.benchmark_doctr_probe import probe_one, PROBE_STEMS

    with open(MANIFEST) as f:
        manifest = json.load(f)
    classification = classify_manifest(manifest)
    scans = sorted(s for s, c in classification.items() if c["scan"])

    run_root = args.out
    texts_dir = os.path.join(run_root, "extracted_texts")
    os.makedirs(texts_dir, exist_ok=True)

    done = 0
    errors = []
    for stem in scans:
        out_file = os.path.join(texts_dir, f"{stem}.txt")
        if os.path.exists(out_file):
            done += 1
            continue
        try:
            r = probe_one(stem, manifest[stem], args.zoom)
        except Exception as e:  # noqa: BLE001
            errors.append({"stem": stem, "error": str(e)})
            continue
        if r.get("status") != "ok":
            errors.append({"stem": stem, "status": r.get("status"), "error": r.get("error")})
            continue
        with open(out_file, "w") as f:
            f.write(f"# Engine: doctr\n# Seconds: {r.get('total_s')}\n\n{r.get('text','')}")
        done += 1
        print(f"{stem}: chars={len(r.get('text',''))} rss={r.get('maxrss_kb',0)//1024}MB")

    meta = {
        "engine": "doctr",
        "arch": {"det": "db_mobilenet_v3_large", "reco": "crnn_mobilenet_v3_small"},
        "created": datetime.now().isoformat(),
        "scan_count": len(scans),
        "done": done,
        "errors": errors,
    }
    with open(os.path.join(run_root, "ocr_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nbuild: ok={done} err={len(errors)} / {len(scans)} -> {texts_dir}")


def cmd_eval(args) -> None:
    from tests.benchmark_doctr_probe import PROBE_STEMS

    rows = load_csv(args.csv)
    stem_to_row = {os.path.splitext((r.get("nama_file") or "").strip())[0]: r for r in rows}

    with open(MANIFEST) as f:
        manifest = json.load(f)
    classification = classify_manifest(manifest)
    if args.stems == "10":
        stems = PROBE_STEMS
    elif args.stems == "49":
        stems = sorted(s for s, c in classification.items() if c["scan"])
    elif args.stems == "embedded":
        stems = sorted(s for s, c in classification.items() if not c["scan"])
    else:
        stems = args.stems.split(",")

    missing = [s for s in stems if s not in stem_to_row]
    if missing:
        raise SystemExit(f"stem tanpa GT: {missing}")

    out = {
        "stems": args.stems,
        "csv": os.path.basename(args.csv),
        "n": len(stems),
        "baseline": eval_dir(args.base, stem_to_row, stems),
        args.doc_label: eval_dir(args.doc, stem_to_row, stems),
        "hybrid": eval_hybrid(args.base, args.doc, stem_to_row, stems),
        "oracle": eval_oracle(args.base, args.doc, stem_to_row, stems),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Saved: {args.out}\n")

    for label in ("baseline", args.doc_label, "hybrid", "oracle"):
        s = out[label]
        print(f"=== {label.upper()} ===")
        for field in EVAL + ["macro_avg"]:
            d = s[field] if field != "macro_avg" else s["macro_avg"]
            if field == "macro_avg":
                print(f"  MACRO exact {d['exact_acc']*100:.1f}% fuzzy {d['fuzzy_acc']*100:.1f}%")
            else:
                print(f"  {field}: exact {d['exact_acc']*100:.1f}% fuzzy {d['fuzzy_acc']*100:.1f}%"
                      f" ({d['exact']}/{d['total']})")
        print()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="OCR 49 scan cert dengan DocTR")
    b.add_argument("--out", default=os.path.join(RUNS_DIR, "corpus_doctr"), help="root output korpus")
    b.add_argument("--zoom", type=float, default=3.0)
    b.set_defaults(func=cmd_build)

    e = sub.add_parser("eval", help="eval baseline/doctr/hybrid/oracle vs GT v9")
    e.add_argument("--base", default=BASELINE_DIR, help="teks baseline rapid_tess")
    e.add_argument("--doc", required=True, help="teks DocTR")
    e.add_argument("--doc-label", default="doctr", help="label engine utk key JSON/print")
    e.add_argument("--stems", default="10", choices=["10", "49", "embedded"], help="subset stem")
    e.add_argument("--csv", default=GT_CSV)
    e.add_argument("--out", required=True, help="path json output")
    e.set_defaults(func=cmd_eval)

    args = p.parse_args()
    args.func(args)


def demo() -> None:
    """Self-check aturan merge per-field (baseline vs DocTR)."""
    from app.services.field_extractor import ExtractedValue

    def ev(v): return ExtractedValue(v, 0.9, "x")

    base = {
        "penyelenggara_kegiatan": ev("BEM FKM UNAIR"),
        "nomor_bukti_fisik_nomor_sertifikasi": ev("123/ABC/2024"),
        "waktu_mulai_pelaksanaan": ev("01/08/2024"),
        "nama_kegiatan_sertifikasi": ev("Seminar X"),
    }
    doc = {
        "penyelenggara_kegiatan": ev("BEM FKM Universitas Airlangga"),
        "nomor_bukti_fisik_nomor_sertifikasi": ev("GARBLED/DIGIT"),
        "waktu_mulai_pelaksanaan": ev("01/08/2024"),
        "nama_kegiatan_sertifikasi": None,
    }
    m = merge_fields(base, doc)
    assert m["penyelenggara_kegiatan"].value == "BEM FKM Universitas Airlangga"  # DocTR priority
    assert m["nomor_bukti_fisik_nomor_sertifikasi"].value == "123/ABC/2024"       # baseline priority
    assert m["waktu_mulai_pelaksanaan"].value == "01/08/2024"
    assert m["nama_kegiatan_sertifikasi"].value == "Seminar X"                     # doc None -> base kept
    print("ok: hybrid_ocr merge rules")


if __name__ == "__main__":
    demo()
    main()
