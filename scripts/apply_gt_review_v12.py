"""Apply handoff v12 GT fixes to create Ground_Truth_Sertifikat_v9.csv.

Keputusan dari audit docs/report/gt_review_v12.xlsx + konteks teks akurat
(mapping stem-exact). v8 tetap frozen sebagai acuan historis.

Changes:
  - AQEEL_Seminar.pdf         : typo 'Kementriann' -> 'Kementerian'       (user approved)
  - Piagam HIMA S1-AK ...     : typo 'Akuntasi' -> 'Akuntansi'           (user approved)
  - hakim_lomba.png           : typo 'Akuntasi' -> 'Akuntansi'           (pola sama)
  - FIT_Faiz.pdf              : typo 'Informatioon' -> 'Information'     (user approved)
  - NIC_Faiz.pdf              : 'Himpunan Mahasiswa UNIMUS' ->
                                'Himpunan Mahasiswa Statistika UNIMUS'   (user approved)

Usage:
  uv run python scripts/apply_gt_review_v12.py
"""

import csv
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V8_CSV = os.path.join(REPO, "Ground_Truth_Sertifikat_v8.csv")
V9_CSV = os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv")
DIFF_OUT = os.path.join(REPO, "docs", "report", "gt_v9_diff.txt")

FIXES = {
    "AQEEL_Seminar.pdf": (
        "Kementriann Komunikasi dan Informatika Republik Indonesia dan Gerakan Nasional Literasi Digital Siberkreasi",
        "Kementerian Komunikasi dan Informatika Republik Indonesia dan Gerakan Nasional Literasi Digital Siberkreasi",
    ),
    "Piagam HIMA S1-AK 2025-compressed_69.pdf": (
        "Himpunan Mahasiswa S-1 Akuntasi",
        "Himpunan Mahasiswa S-1 Akuntansi",
    ),
    "hakim_lomba.png": (
        "Himpunan Mahasiswa Akuntasi Universitas Airlangga",
        "Himpunan Mahasiswa Akuntansi Universitas Airlangga",
    ),
    "FIT_Faiz.pdf": (
        "Informatics Engineering, Faculty of Informatioon Technology",
        "Informatics Engineering, Faculty of Information Technology",
    ),
    "NIC_Faiz.pdf": (
        "Himpunan Mahasiswa UNIMUS",
        "Himpunan Mahasiswa Statistika UNIMUS",
    ),
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
    rows = read_rows(V8_CSV)
    by_name = {r["Nama File"].strip(): r for r in rows}
    fieldnames = list(next(iter(rows)).keys())

    applied = []
    errors = []
    for fname, (old, new) in FIXES.items():
        if fname not in by_name:
            errors.append(f"{fname}: tidak ada di v8")
            continue
        cur = by_name[fname]["Penyelenggara Kegiatan"]
        if cur != old:
            errors.append(f"{fname}: nilai saat ini tidak sama dengan ekspektasi fix")
            continue
        by_name[fname]["Penyelenggara Kegiatan"] = new
        applied.append((fname, old, new))

    if errors:
        for e in errors:
            print("ERROR:", e)
        raise SystemExit(1)

    write_rows(V9_CSV, [by_name[r["Nama File"].strip()] for r in rows], fieldnames)

    lines = ["GT v9 DIFF (v8 -> v9)", "=" * 60]
    for fname, old, new in applied:
        lines.append(f"\n{fname}\n  '{old}' -> '{new}'")
    with open(DIFF_OUT, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"v9 written: {V9_CSV} ({len(applied)} fixes)")
    for fname, old, new in applied:
        print(f"  {fname}: {old[:35]}... -> {new[:35]}...")
    print(f"diff report: {DIFF_OUT}")


if __name__ == "__main__":
    main()
