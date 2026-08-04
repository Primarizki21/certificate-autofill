"""Apply reviewed GT decisions to Ground_Truth_Sertifikat_v8.csv.

Decisions come from docs/report/gt_review.xlsx (user-filled). The xlsx holds
free-text keputusan; this script encodes the auditable action list that the
user approved ("oke jalankan rekomendasi") and asserts the tingkat changes
already present in v8. Raw CSV is never modified (kept as history).

Usage:
  uv run python scripts/apply_gt_review.py
"""

import csv
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_CSV = os.path.join(REPO, "Ground_Truth_Sertifikat.csv")
V8_CSV = os.path.join(REPO, "Ground_Truth_Sertifikat_v8.csv")
DIFF_OUT = os.path.join(REPO, "docs", "report", "gt_review_diff.txt")

# Keputusan yang disetujui user (Sheet 4 Review Low-Found -> "oke jalankan
# rekomendasi"): rapikan label nama kegiatan Magang UKM agar literal di teks.
NAMA_FIXES = {
    "2030325_219642_skp.pdf": "Magang UKM Universitas Airlangga",
    "2071996_221065_skp.pdf": "Magang UKM Universitas Airlangga",
    "Sertif sinem_vene_magang UKM.pdf": "Magang UKM Universitas Airlangga",
}

# Tingkat final yang harus ada di v8 (Sheet 1 + Sheet 2 disetujui).
EXPECTED_TINGKAT = {
    "1966887_221065_skp.pdf": "Nasional",
    "1981676_219642_skp.pdf": "Nasional",
    "2954283_219642_skp.pdf": "Internasional",
    "2030372_219642_skp.pdf": "Nasional",
    "Airno_Faiz.pdf": "Nasional",
    "FIT_Faiz.pdf": "Internasional",
}


def read_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    raw = {r["Nama File"]: r for r in read_rows(RAW_CSV)}
    v8 = {r["Nama File"]: r for r in read_rows(V8_CSV)}
    fieldnames = list(next(iter(v8.values())).keys())

    issues = []
    for fname, want in EXPECTED_TINGKAT.items():
        if fname not in v8:
            issues.append(f"{fname}: tidak ada di v8")
        elif v8[fname]["Tingkat"] != want:
            issues.append(f"{fname}: tingkat={v8[fname]['Tingkat']} != {want}")

    changes = []
    for fname, new_nama in NAMA_FIXES.items():
        if fname not in v8:
            issues.append(f"{fname}: tidak ada di v8")
            continue
        old = v8[fname]["Nama Kegiatan Sertifikasi"]
        if old != new_nama:
            changes.append((fname, old, new_nama))
            v8[fname]["Nama Kegiatan Sertifikasi"] = new_nama

    if issues:
        for i in issues:
            print("ERROR:", i)
        raise SystemExit(1)

    if changes:
        write_rows(V8_CSV, list(v8.values()), fieldnames)

    # diff report: raw -> v8-final
    lines = ["GROUND TRUTH REVIEW DIFF (raw -> v8-final)", "=" * 60]
    for fname, field in [("Tingkat", "Tingkat"), ("Nama Kegiatan Sertifikasi", "Nama Kegiatan Sertifikasi")]:
        for fn in sorted(set(list(EXPECTED_TINGKAT) + list(NAMA_FIXES))):
            r, v = raw.get(fn, {}), v8.get(fn, {})
            if not r or not v:
                continue
            if r.get(field) != v.get(field):
                lines.append(f"\n{fn}\n  {field}: '{r.get(field)}' -> '{v.get(field)}'")
    if len(lines) == 2:
        lines.append("  (tidak ada perubahan baris yang tersisa)")
    with open(DIFF_OUT, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"nama_kegiatan changes applied: {len(changes)}")
    for c in changes:
        print("  ", c)
    print(f"diff report: {DIFF_OUT}")


if __name__ == "__main__":
    main()
