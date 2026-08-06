# Handoff v14 — DocTR Probe FAIL (nomor); Hybrid per-field = kandidat berikutnya

> Supersedes `docs/handoff_v13.md`. Sesi ini:
> - **OCR-006 — DocTR probe**: 10 scan cert terkontrol → **GATE FAIL pada nomor**
>   (14.3% vs baseline like-for-like 28.6%; baseline resmi scan 57.6%).
>   Dates & organizer PASS. DocTR = kandidat **hybrid per-field**, bukan
>   pengganti penuh RapidOCR+Tesseract.
> - Exp 5 tetap tutup (ledger EXP5-001). Baseline evaluasi tetap GT v9 + matcher v2.
> - Produksi `backend/` tidak disentuh.

---

## OCR-006 — DocTR Probe (db_mobilenet_v3_large + crnn_mobilenet_v3_small)

### Desain
Probe terkontrol (handoff v13 gate): 10 sertifikat **scan** tetap, spread
kategori, termasuk kasus tajam dari miss set Exp5 (`2439919` UB, `FIT_Faiz`,
`NIC_Faiz`). Engine DocTR (mindee v1.0.1, keluarga model CRNN/SAR/ViTSTR —
belum pernah diuji sebelumnya). CPU, `assume_straight_pages=True`.

Containment WSL 8GB: reuse `tests/paddle_probe_safe.py --engine doctr`
(subprocess fresh per cert + RLIMIT_AS 8GB + watchdog RSS parent).

> Temuan infra: RLIMIT_AS <8GB memecah torch DocTR (VA reservation → malloc
> failed saat inferens). Watchdog RSS = containment utama, RLIMIT_AS ≥ RAM host.

### Hasil run (`tests/benchmark_runs/ocr_experiment/probe_doctr/`)

- Build: **10/10 ok**, 0 error, 0 watchdog kill. RSS ~1.3GB/cert, ~7.5s/cert
  (model init ~3.2s/cert — subprocess fresh).
- Evaluasi vs GT v9 + matcher v2 (subset scan 10):

| Field | DocTR exact | DocTR fuzzy | Baseline rapid_tess* | Gate |
|---|---|---|---|---|
| nomor | **14.3%** | 14.3% | **28.6%** | regresi ❌ |
| tanggal_mulai | 88.9% | 88.9% | 88.9% | = PASS ✅ |
| tanggal_selesai | 88.9% | 88.9% | 88.9% | = PASS ✅ |
| organizer | 10.0% | **70.0%** | 0.0% / 60.0% | naik ✅ |
| MACRO | 40.0% | 53.3% | 40.0% / 53.3% | ≈ |

\* like-for-like: `baseline_10/` = 10 txt baseline rapid_tess sama, GT v9 +
matcher v2 (baseline resmi 74 scan GT v8: nomor 57.6%, dates 85.7%, org 14.3%).

### Verdict
**OCR-006 GATE FAIL** — nomor regresi parah. Root check raw OCR:
`106/STF.E/HOLOGY7.0/x1t/2024` → DocTR `6/ST : E/ - L G 7. X1/2 o`
(digit hancur; NIP/NIM juga drop digit). Sama seperti semua engine non-baseline
sebelumnya (paddle/easyocr FAIL di nomor). DocTR justru **terbaik untuk
dates + organizer fuzzy** — bukan pengganti penuh, tapi kandidat hybrid.

### Re-try condition (ledger OCR-006)
Hybrid **per-field**: DocTR untuk dates + organizer, baseline RapidOCR+Tesseract
tetap untuk nomor (mis. merge 2-pass / field-aware router). Full replacement
DocTR ditutup.

---

## What Was Done

1. `tests/ocr_engine.py` — +engine `doctr` (`_load_doctr`, `ocr_doctr`,
   `DOCTR_DET_ARCH`/`DOCTR_RECO_ARCH` = db_mobilenet_v3_large +
   crnn_mobilenet_v3_small, torch thread=1 utk WSL 8GB).
2. `tests/paddle_probe_safe.py` — `--engine doctr` (model_init timing,
   choices +doctr). Harness yang sama → containment WSL otomatis.
3. `tests/benchmark_doctr_probe.py` (baru) — probe 10 stem tetap + eval GT v9
   (reuse `benchmark_ocr.cmd_eval`). Runner mandiri, produksi tak tersentuh.
4. Run: `ocr_experiment/probe_doctr/` (extracted_texts + ocr_meta + eval.json
   + eval_baseline10.json). Run dir gitignored.
5. `docs/experiments_ledger.md` — +**OCR-006** (FAIL nomor, hybrid = re-try).
6. `docs/report/runs_summary.md` + `.csv` — regenerate (54 runs, probe_doctr masuk).

`pytest tests/` (--import-mode=importlib) → **31 passed**. `python -m
tests.ocr_engine` demo OK (engine baru lazy, tak mengganggu env tanpa
python-doctr).

---

## Keputusan yang DIBUTUHKAN USER

1. **Hybrid per-field (DocTR dates+organizer / baseline nomor)** — layak coba?
   (Edit di `tests/` dulu, gate nomor ≥ baseline + organizer naik.)
2. **Promosi produksi** organizer_v2 + router rules + matcher (menunggu sejak v11/v12).

---

## Key Files

| File | Peran |
|---|---|
| `tests/ocr_engine.py` | +engine `doctr` (CPU mobilenet, thread-guard) |
| `tests/paddle_probe_safe.py` | +`--engine doctr` (containment WSL) |
| `tests/benchmark_doctr_probe.py` | Probe 10 scan + eval GT v9 (baru) |
| `tests/benchmark_runs/ocr_experiment/probe_doctr/` | Hasil run (gitignored) |
| `docs/experiments_ledger.md` | +OCR-006 (FAIL, hybrid = re-try) |
| `backend/app/services/ocr_fallback.py` | Produksi (RapidOCR+Tesseract) — tetap, tak disentuh |

---

## Jangan Lakukan

- Ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Run benchmark tanpa `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv` (atau CSV v9)
- Uji CnOCR / MMOCR (ledger OCR-005), re-run full DocTR replacement (OCR-006)
- Sentuh `backend/` tanpa keputusan user
- RLIMIT_AS <8GB untuk DocTR (memecah torch — pakai watchdog RSS)
