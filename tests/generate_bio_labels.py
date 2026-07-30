import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "Ground_Truth_Sertifikat.csv")
TEXTS_DIR = os.path.join(
    os.path.dirname(__file__), "benchmark_runs", "run_20260728_131835", "extracted_texts",
)
OUT_DIR = os.path.join(os.path.dirname(__file__), "bio_labels")

FIELD_TO_ENTITY = {
    "nama_kegiatan_sertifikasi": "EVT",
    "penyelenggara_kegiatan": "ORG",
    "waktu_mulai_pelaksanaan": "DAT",
    "waktu_selesai_pelaksanaan": "DAT",
    "nomor_bukti_fisik_nomor_sertifikasi": "NUM",
}

CSV_COLUMN_MAP = {
    "nama_kegiatan_sertifikasi": "Nama Kegiatan Sertifikasi",
    "waktu_mulai_pelaksanaan": "Waktu Mulai Pelaksanaan",
    "waktu_selesai_pelaksanaan": "Waktu Selesai Pelaksanaan",
    "penyelenggara_kegiatan": "Penyelenggara Kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi": "Nomor Bukti Fisik Nomor Sertifikasi",
}


def read_text(filename):
    stem = os.path.splitext(filename)[0]
    txt_path = os.path.join(TEXTS_DIR, stem + ".txt")
    if not os.path.exists(txt_path):
        return None
    lines = []
    with open(txt_path) as f:
        for line in f:
            if not line.startswith("#"):
                lines.append(line)
    return "".join(lines).strip()


def normalize(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def tokenize(text):
    return text.split()


def find_entity_span(tokens, entity_value):
    if not entity_value or entity_value == "-":
        return None

    nv = normalize(entity_value)
    nt = [normalize(t) for t in tokens]

    nv_flat = "".join(nt)
    nv_clean = nv

    if nv_clean in nv_flat:
        start_char = nv_flat.index(nv_clean)
        end_char = start_char + len(nv_clean)

        cur = 0
        token_start = None
        token_end = None
        for i, t in enumerate(nt):
            tok_start = cur
            tok_end = cur + len(t)
            if token_start is None and tok_end > start_char:
                token_start = i
            if token_end is None and tok_end >= end_char:
                token_end = i + 1
                break
            cur += len(t)

        if token_start is not None and token_end is not None:
            return token_start, token_end

    word_pattern = nv_clean
    for i in range(len(nt)):
        if nt[i] == word_pattern and len(nt[i]) == len(word_pattern):
            return i, i + 1

    for length in range(len(nt), 0, -1):
        for i in range(len(nt) - length + 1):
            combined = "".join(nt[i:i + length])
            if combined == nv_clean:
                return i, i + length
            if len(nv_clean) > 3 and (combined.startswith(nv_clean) or nv_clean.startswith(combined)):
                return i, i + length

    return None


def generate_bio_labels():
    os.makedirs(OUT_DIR, exist_ok=True)

    rows = list(csv.DictReader(open(CSV_PATH, newline="")))
    csv_lookup = {r.get("Nama File", ""): r for r in rows}

    ENTITY_TYPES = ["ORG", "EVT", "DAT", "NUM", "PER"]
    ENTITY_TO_ID = {e: i for i, e in enumerate(ENTITY_TYPES)}
    ID_TO_LABEL = {0: "O"}
    for e in ENTITY_TYPES:
        eid = ENTITY_TO_ID[e]
        ID_TO_LABEL[eid * 2 + 1] = f"B-{e}"
        ID_TO_LABEL[eid * 2 + 2] = f"I-{e}"

    stats = {"total": 0, "matched": 0, "empty_gt": 0, "unmatched": 0}
    per_file = []

    for filename, row in csv_lookup.items():
        text = read_text(filename)
        if text is None:
            continue

        tokens = tokenize(text)
        labels = ["O"] * len(tokens)
        file_matches = []

        for field, entity_type in FIELD_TO_ENTITY.items():
            col = CSV_COLUMN_MAP[field]
            gt_value = row.get(col, "").strip()
            if not gt_value or gt_value == "-":
                stats["empty_gt"] += 1
                continue

            span = find_entity_span(tokens, gt_value)
            if span:
                start, end = span
                labels[start] = f"B-{entity_type}"
                for i in range(start + 1, end):
                    labels[i] = f"I-{entity_type}"
                file_matches.append({
                    "field": field, "entity": entity_type, "start": start, "end": end,
                    "matched_text": " ".join(tokens[start:end]),
                    "gt_value": gt_value[:80],
                })
                stats["matched"] += 1
            else:
                file_matches.append({
                    "field": field, "entity": entity_type, "start": -1, "end": -1,
                    "matched_text": "", "gt_value": gt_value[:80],
                })
                stats["unmatched"] += 1

        stats["total"] += 1

        output = {
            "filename": filename,
            "tokens": tokens,
            "labels": labels,
            "matches": file_matches,
            "n_tokens": len(tokens),
            "n_matched": sum(1 for m in file_matches if m["start"] >= 0),
            "n_fields": len([f for f in FIELD_TO_ENTITY.keys()
                             if row.get(CSV_COLUMN_MAP[f], "").strip() and row[CSV_COLUMN_MAP[f]].strip() != "-"]),
        }
        per_file.append(output)

        out_path = os.path.join(OUT_DIR, os.path.splitext(filename)[0] + ".json")
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2)

    total_fields = (stats["matched"] + stats["unmatched"] + stats["empty_gt"])
    print(f"Files: {stats['total']}")
    print(f"Fields matched: {stats['matched']}/{total_fields} "
          f"({stats['matched']/max(total_fields,1)*100:.1f}%)")
    print(f"Fields unmatched: {stats['unmatched']}")
    print(f"Fields empty GT: {stats['empty_gt']}")

    n_full_matches = sum(1 for p in per_file if p["n_matched"] == p["n_fields"] and p["n_fields"] > 0)
    n_partial = sum(1 for p in per_file if 0 < p["n_matched"] < p["n_fields"])
    n_none = sum(1 for p in per_file if p["n_matched"] == 0 and p["n_fields"] > 0)
    print(f"\nFiles with all fields matched: {n_full_matches}")
    print(f"Files with partial match: {n_partial}")
    print(f"Files with no fields matched: {n_none}")

    worst = sorted([p for p in per_file if p["n_matched"] < p["n_fields"]],
                   key=lambda p: p["n_matched"])
    if worst:
        print(f"\nWorst 10 files (lowest match rate):")
        for p in worst[:10]:
            unmatched = [m["field"] for m in p["matches"] if m["start"] < 0]
            print(f"  {p['filename']}: {p['n_matched']}/{p['n_fields']} "
                  f"matched. Unmatched: {', '.join(unmatched)}")

    summary_path = os.path.join(OUT_DIR, "_summary.json")
    summary = {
        "n_files": stats["total"],
        "n_fields_matched": stats["matched"],
        "n_fields_unmatched": stats["unmatched"],
        "n_fields_empty_gt": stats["empty_gt"],
        "n_full_matches": n_full_matches,
        "n_partial": n_partial,
        "n_none": n_none,
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nOutput: {OUT_DIR}")

    return per_file


if __name__ == "__main__":
    generate_bio_labels()
