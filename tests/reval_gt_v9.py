"""Re-evaluate extracted fields (run v9 winner) against GT v9 + matcher v2.

Offline — tidak re-run LLM. Membaca extracted_fields.csv (hasil final pipeline),
mencocokkan ke Ground_Truth_Sertifikat_v9.csv per field dengan tests.matchers
versi v2, lalu hitung per-field exact/fuzzy + macro.

Usage:
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.reval_gt_v9
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.evaluation_framework import load_csv
from tests.matchers import match_field

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
RUN_DIR = os.path.join(REPO, "tests", "benchmark_runs", "run_llm_v4_20260805_163541")
EXTRACTED = os.path.join(RUN_DIR, "extracted_fields.csv")
OUT_JSON = os.path.join(RUN_DIR, "summary_gt_v9_reval.json")

FIELD_MAP = {
    "nama_kegiatan_sertifikasi": "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan": "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan": "waktu_selesai_pelaksanaan",
    "penyelenggara_kegiatan": "penyelenggara_kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi": "nomor_bukti_fisik_nomor_sertifikasi",
    "tingkat": "tingkat",
}


def main():
    gt_rows = load_csv(GT_CSV)
    gt_by_file = {}
    for r in gt_rows:
        stem = os.path.splitext(r.get("nama_file", ""))[0]
        gt_by_file[stem] = r

    per_field = {f: {"total": 0, "exact": 0, "fuzzy": 0} for f in FIELD_MAP}

    with open(EXTRACTED, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stem = os.path.splitext(row["filename"])[0]
            field = row["field"]
            value = row.get("value")
            if field not in FIELD_MAP or stem not in gt_by_file:
                continue
            gt = gt_by_file[stem].get(field, "").strip()
            if not gt or gt == "-":
                continue
            res = match_field(gt, value, field)
            pf = per_field[field]
            pf["total"] += 1
            pf["exact"] += 1 if res["exact"] else 0
            pf["fuzzy"] += 1 if res["fuzzy"] else 0

    total = exact = fuzzy = 0
    out = {"gt": os.path.basename(GT_CSV), "matcher": "v2", "run": os.path.basename(RUN_DIR),
           "fields": {}, "macro_avg": {}}
    print(f"GT: {os.path.basename(GT_CSV)} | matcher v2 | run: {os.path.basename(RUN_DIR)}")
    print(f"{'field':<34}{'n':>4}{'exact%':>9}{'fuzzy%':>9}")
    for f in FIELD_MAP:
        pf = per_field[f]
        if pf["total"] == 0:
            continue
        e = pf["exact"] / pf["total"] * 100
        fu = pf["fuzzy"] / pf["total"] * 100
        total += pf["total"]
        exact += pf["exact"]
        fuzzy += pf["fuzzy"]
        print(f"{f:<34}{pf['total']:>4}{e:>8.1f}%{fu:>8.1f}%")
        out["fields"][f] = {"total": pf["total"], "exact": pf["exact"], "fuzzy": pf["fuzzy"],
                            "exact_acc": round(e / 100, 4), "fuzzy_acc": round(fu / 100, 4)}

    if total:
        print(f"{'MACRO':<34}{total:>4}{exact/total*100:>8.1f}%{fuzzy/total*100:>8.1f}%")
        out["macro_avg"] = {"total": total, "exact": exact, "fuzzy": fuzzy,
                            "exact_acc": round(exact / total, 4), "fuzzy_acc": round(fuzzy / total, 4)}

    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
