# Handoff v31 — AKT-002 (deteksi nama_kegiatan, GATE PASS +29.7pt)

> Supersedes `docs/handoff_v30.md`. Sesi ini = eksekusi frontier #1 v30:
> AKT-002 — deteksi nama_kegiatan v2 (0 LLM, tests-only). Berbasis taksonomi
> AKT-001 (kosong = masalah DETEKSI). Hasil: nama_kegiatan exact
> **6.8% → 36.5%** (+29.7pt), MACRO **63.0% → 68.8%** — GATE PASS, 0 regress.

---

## Hasil sesi

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. Dump 5 cert exact (wajib no-regress) + teks kasus kunci | sertif_colab, SSF, Hitech, IRIS PF, 2954421; 1963507 = judul kutip | DONE |
| 2. `tests/benchmark_akt2.py` — `extract_activity_v2` (16 anchor + repair merge + strip junk) di atas `offline_prod` | 1 file tests/ baru, 0 produksi disentuh | DONE |
| 3. Trial iterasi (3x): bug `KEPADA` false-positive (\bpada), `Dalamkompetisi` capital, repair `of`/`yang`/`oleh` bound, IGNORECASE global merusak camel-split | Semua ter-fix via per-cert debug | DONE |
| 4. Run final, GT v9 + matcher v2 | nama_kegiatan exact **5→27/74 (36.5%, +29.7pt)**, fuzzy 17.6→56.8%, MACRO **63.0→68.8%**, 22 fix / 0 regress | **GATE PASS** |
| 5. OOD noise (QA): 10/25% injeksi confusi | drop ekstra 10% +2.7pt, 25% +8.1pt (anchor teks-bergantung); gain absolut positif semua level | CATATAN |
| 6. QA | pytest **58 passed**; report_data `akt_002_detection` + generate_report + runs_summary | DONE |

---

## Temuan penting sesi ini

1. **DETEKSI = kunci nama_kegiatan** (konfirmasi AKT-001): 22 fix dari anchor
   pattern + repair OCR-merge, tanpa sentuh evaluator/scoring. Anchor paling
   produktif: `entitled/titled` (5 cert Ananda), kutipan agenda/kegiatan
   (SERTIF76, UNITY, 1963507, E-certificate), `Dalam acara/kegiatan` + stop
   set, `\bpada X yang dilaksanakan` (2954631, ACTION).
2. **Konflik konvensi GT teratasi**: 1963507 — GT pilih JUDUL KUTIP
   (`"Webinar mengenai Global Warming"`), bukan nama sebelum kutip
   (`Mawacana`). Rule kutip di-prioritaskan sebelum anchor `Dalam kegiatan`.
3. **Guard `\bpada`**: "DIBERIKANKEPADA PrimarizkiAhmad" — substring "pada"
   dalam "KEPADA" menangkap NAMA ORANG (2954933/SERTIF76 rusak). Word
   boundary fix. Lesson: anchor kata umum (pada/dalam) wajib \b + negative
   lookahead.
4. **Matcher quirk (jangan dieksploitasi)**: nilai ber-junk bisa dapat exact
   credit via `abbreviation_match` (rasio huruf ≤0.6), nilai bersih justru
   tidak (2954631 "Competitionof" — ratio 0.9 > 0.6). Metrik protokol tetap;
   jangan tambah junk demi credit. 2954631 akhirnya EXACT bersih via repair
   `of` bound.
5. **Bug regex ditangkap saat iterasi**: `re.IGNORECASE` GLOBAL memecah
   camel-split `(?<=[a-z])(?=[A-Z])` → spasi antar SEMUA huruf (hancurkan
   seluruh ekstraksi). Perbaikan: flags per-pattern, IGNORECASE inline
   `[Dd]alam`.
6. **OOD noise jujur**: anchor teks-bergantung (pola sama R1/R4 organizer) —
   drop ekstra 10% +2.7pt / 25% +8.1pt, tapi gain absolut tetap positif semua
   level. Bila di-port produksi → pola KEEP/GUARD (needs_review F6).

---

## Frontier berikutnya (urutan saran)

1. **Port produksi AKT-002** — keputusan user (pola PROD-002: flag
   `ENABLE_ACTIVITY_V2` default OFF + re-eval pasca-port + smoke PDF).
   Anchor = GUARD needs_review (noise-rapuh).
2. **AKT-003 (opsional)**: sisa kosong 30 — pola belum tertangkap (judul
   besar di teks, `Magang UKM X`, `Kompetisi Ilmiah Mahasiswa (KIM)`, cert
   "dengan ini memberikan penghargaan"). Ceiling ~52/74.
3. **GT v10** — fix inkonsistensi GT v9 (FMIPA "dan", HIMA pendek/panjang).
4. **R1/R4 + GUARD F6** — port needs_review → organizer 63.5→66.2%.
5. **Scoring organizer_v2** — data >74 (ORG-005 FAIL). **KB** TUTUP (v27).

### Peta dokumen (agar agent sesi berikutnya tidak salah alamat)

- **AKT** (activity name) → `docs/experiments_ledger.md` (AKT-001 report-only
  + AKT-002 PASS) + `docs/report/akt1_activity_taxonomy.md` +
  `docs/report/akt2_activity_detection.md` + report_data `akt_002_detection`.
- **ORG/PROD** → ledger + report_data (org_002_f1, org_003_v3, org_004_format,
  prod_002_port) → `scripts/generate_report.py`.

## Frontier tertunda (sama v24-v30)

- F4 fingerprint dedup, F5 distillation, F7 infra OCR queue, Eksperimen A
  (LLM per-field), R1/R4 + GUARD F6, HYB-001 OCR hybrid, AKT-003.

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Eksperimen tetap di `tests/` (produksi: PROD-002 flag default OFF)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..006, LLM-001..003, ROUTER-001, NC-001/002, ORG-005
- Pytest: `uv run python -m pytest tests/ -q` (58 passed)
- `results_comparison.xlsx` tidak di-commit — regenerate lokal bila perlu

## Key Files

| File | Peran |
|---|---|
| `tests/benchmark_akt2.py` | AKT-002 — extractor activity v2 + benchmark (GATE PASS) |
| `docs/report/akt2_activity_detection.md` | Report AKT-002 (fix per cert + OOD noise) |
| `tests/akt1_activity_taxonomy.py` | AKT-001 (v30) — taksonomi nama_kegiatan |
| `docs/experiments_ledger.md` | AKT-002 PASS + AKT-001 (v30) |
| `backend/app/services/organizer_normalize.py` | PROD-002 (v29) |
