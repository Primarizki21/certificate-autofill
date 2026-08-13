# Handoff v30 — AKT-001 (taksonomi nama_kegiatan, report-only) + arah AKT-002

> Supersedes `docs/handoff_v29.md`. Sesi ini = track baru **AKT** (activity
> name): taksonomi mismatch `nama_kegiatan_sertifikasi` (6.8% exact, field
> terlemah) — report-only (preceden F1B), bukan eksperimen gate. Hasil:
> **masalah = DETEKSI, bukan normalisasi** (berbeda fundamental dari organizer).

---

## Hasil sesi

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. Inspeksi awal (dump extracted vs GT, 74 cert) | exact 5 · fuzzy 8 · wrong 61; 61/69 non-exact = `(kosong)` → deteksi, bukan normalisasi | DONE |
| 2. `tests/akt1_activity_taxonomy.py` — taksonomi (mirror F1b, kategori activity-name + kolom `in_text`) | 1 file tests/ baru, 0 produksi disentuh | DONE |
| 3. Run taksonomi pada jalur produksi PROD-002 (flag ON), GT v9 + matcher v2 | **kosong 57** (52/57 GT ada di teks), salah_kegiatan 4, kurang_lengkap 3, kelebihan 3, format_ocr 2 | PASS (report-only) |
| 4. Spot check `in_text` (12 kasus kosong) | Anchor pattern nyata di teks: `Dalam acara X`, `pada ajang X dengan tema`, `As a participant at X`, `Dalam memperingati X yang diselenggarakan` | VALID |
| 5. QA | pytest **58 passed** (tak berubah — tool baru report-only); diff = 2 file baru, 0 modif | DONE |

---

## Temuan penting sesi ini

1. **`nama_kegiatan` = masalah DETEKSI (kosong 57/69), bukan normalisasi.**
   `extract_activity_name` hanya fire pada pola sempit (`seminar X yang
   diselenggarakan`, `talkshow X`, keyword hardcode AIRNOLOGY/KAKIWIMA/SPECTA/
   BRIEF). Mayoritas cert pakai anchor lain yang tak tertangkap.
2. **52/57 kasus kosong: GT MUNCUL di teks raw** (compact/overlap ≥0.5) →
   deteksi regex **feasible**, tinggal pattern coverage + repair OCR-merge.
   Hanya 5 kasus yang nama kegiatannya tidak terwakili di teks (butuh LLM/OCR).
3. **Anchor pattern baru yang terlihat di teks** (bahan AKT-002):
   - `Dalam acara X` (2030372 Economic Week, 2954707 Competition of Design)
   - `pada ajang X dengan tema` (gammafest GAMMAFEST 2025)
   - `As a participant at X, themed` (data slayer Data Slayer 2.0)
   - `Dalam memperingati X yang diselenggarakan` (1930354 Hari Anak Nasional)
4. **False-positive keyword hardcode** (salah_kegiatan 4): `SPECTA` fire di
   PRIMARIZKI_binary_2025 (GT = BINARY), PKKMB fire di VENEDICT_panitia_karsa
   (GT = KARSA FTMM 2024), `Mawacana` fire di 1963507 (GT = Webinar) — perlu
   guard: keyword hanya fallback bila tak ada pattern lain yang match.
5. **Junk suffix** (kelebihan 3): `Untuk Kategori Sma/sederajat Dan Mahasiswa`
   (Dataquest×2), `Pada Perlombaan Io T Tech Competition` (BTF) — strip murah.
6. Ceiling: kosong = 83.8%, salah_kegiatan = 12.2%, kurang_lengkap = 10.8%,
   kelebihan = 10.8%, format_ocr = 9.5% (kumulatif kalau semua diperbaiki).

---

## Frontier berikutnya (urutan saran)

1. **AKT-002 — deteksi nama_kegiatan** (eksperimen ber-gate, 0 LLM):
   - Perluas pola regex: anchor `Dalam acara X`, `pada ajang X`, `Dalam
     memperingati X`, `As a participant at X`, `dengan tema "..."` (X = nama).
   - Repair OCR word-merge: pola `_preprocess` organizer_v2 (`dalamkegiatan`,
     `dalamrangkaianacara`, camel-split) di-extend ke teks activity.
   - Guard keyword hardcode: SPECTA/BRIEF/PKKMB hanya fallback (fire bila tak
     ada pattern lain).
   - Strip junk suffix (`Untuk Kategori...`, `Pada Perlombaan...`).
   - Gate: nama_kegiatan exact +5pt (≥11.8%), no-regress field lain, 0 LLM.
   - Ceiling realistis dari kosong 57: target 30-40% (40-60% dari 57).
2. **GT v10** — fix inkonsistensi GT v9 (FMIPA "dan", HIMA pendek/panjang) —
   keputusan user.
3. **R1/R4 + GUARD F6** — port needs_review → organizer 63.5→66.2%.
4. **Scoring organizer_v2** — data >74 atau keputusan rewrite (ORG-005 FAIL).
5. **KB**: TUTUP (v27) — buka bila data riil.

### Peta dokumen (agar agent sesi berikutnya tidak salah alamat)

- **AKT** (activity name) → `docs/experiments_ledger.md` (ledger) +
  `docs/report/akt1_activity_taxonomy.md` (report). Preceden F1B: taksonomi
  report-only TIDAK masuk report_data.json — hanya eksperimen ber-gate yang
  masuk (org_002_f1, org_003_v3, org_004_format, prod_002_port).
- **ORG/PROD** → ledger + report_data.json → `scripts/generate_report.py`.

## Frontier tertunda (sama v24-v29)

- F4 fingerprint dedup, F5 distillation, F7 infra OCR queue, Eksperimen A
  (LLM per-field), R1/R4 + GUARD F6, HYB-001 integrasi OCR hybrid.

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Eksperimen tetap di `tests/` (produksi: PROD-002 flag masih default OFF)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..006, LLM-001..003, ROUTER-001, NC-001/002, ORG-005
- Pytest: `uv run python -m pytest tests/ -q` (58 passed)
- `results_comparison.xlsx` tidak di-commit — regenerate lokal bila perlu

## Key Files

| File | Peran |
|---|---|
| `tests/akt1_activity_taxonomy.py` | AKT-001 — taksonomi nama_kegiatan (report-only) |
| `docs/report/akt1_activity_taxonomy.md` | Report AKT-001 (ceiling + daftar per cert + in_text) |
| `docs/experiments_ledger.md` | AKT-001 PASS + PROD-002 PASS (v29) |
| `backend/app/services/organizer_normalize.py` | PROD-002 (v29) — normalisasi organizer+nomor |
| `tests/benchmark_prod_port.py` | PROD-002 re-eval (v29) |
