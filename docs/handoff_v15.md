# Handoff v15 — HYB-001 PASS: Hybrid OCR per-field (DocTR + baseline)

> Supersedes `docs/handoff_v14.md`. Sesi ini:
> - **HYB-001 — Hybrid OCR per-field: PASS semua gate.** Merge DocTR
>   (dates+organizer) + baseline RapidOCR+Tesseract (nomor/activity/role) di
>   level extracted-dict, sebelum form mapper. Produksi `backend/` TIDAK
>   disentuh.
> - OCR-006 (DocTR probe FAIL nomor) → hybrid adalah jalur pemakaian DocTR.
> - Baseline evaluasi tetap GT v9 + matcher v2.

---

## HYB-001 — Hybrid OCR per-field (DocTR dates+organizer / baseline nomor)

### Desain
Tiap sertifikat di-OCR **dua engine**: baseline `ocr_fallback` (RapidOCR+
Tesseract) + DocTR (db_mobilenet_v3_large + crnn_mobilenet_v3_small). Kedua
teks diekstrak `extract_certificate_fields` + `organizer_v2` secara terpisah,
lalu **merge per-field** (rule prioritas statis) → `map_fields_to_form`.

```
dates & organizer  : DocTR dulu, baseline fallback
nomor, activity    : baseline dulu, DocTR fallback
role, keyword/aux  : baseline dulu, DocTR fallback
```

Containment WSL 8GB: `paddle_probe_safe --engine doctr` (subprocess fresh,
RLIMIT_AS 8GB, watchdog RSS). Baseline = korpus `baseline_rapid_tess`
(produksi-equivalent, 74 txt).

### Hasil (GT v9 + matcher v2)

| Subset | Varian | organizer e/f | nomor | dates | MACRO e/f |
|---|---|---|---|---|---|
| **Scan 49** | baseline | 20.4% / 61.2% | 57.6% | 85.7% | 45.8% / 57.2% |
| | DocTR only | 24.5% / 63.3% | 36.4% | 85.7% | 43.3% / 54.7% |
| | **hybrid** | **24.5% / 65.3%** | **57.6%** | **85.7%** | **46.8% / 58.2%** |
| | oracle (=hybrid) | 24.5% / 65.3% | 57.6% | 85.7% | 46.8% / 58.2% |
| Scan 10 (like-for-like) | baseline→hybrid | 0/60%→10/70% | 28.6% (=) | 88.9% (=) | 40.0→42.2% |
| **Embedded 25** | hybrid (fallback baseline) | 20.0% / 64.0% | 68.4% | 85.0% | 50.5% / 66.1% — no-regress |

**Gates (HYB-001):**
- nomor scan ≥ baseline: 57.6% = 57.6% ✅
- dates ≥ baseline: 85.7% = 85.7% ✅
- organizer fuzzy naik: 61.2% → 65.3% ✅ (exact 20.4→24.5%)
- MACRO naik: 45.8% → 46.8% ✅
- embedded no-regress (fallback baseline) ✅
- oracle = hybrid → **rule merge sudah optimal**, tidak ada ceiling dari
  pemilihan source per field (naik lebih jauh butuh extractor/engine lebih baik).

Runtime: +~7.5s/cert (DocTR) di atas baseline ~8.6s/cert → ~16s/cert untuk
scan jika dua engine dijalankan penuh. Bisa di-optimize (DocTR hanya saat
field baseline lemah / lazy).

### Verdict
**HYB-001 PASS** — semua gate met, tanpa sentuh produksi. DocTR adalah
**komponen** (dates+organizer), bukan pengganti. Integrasi produksi = keputusan
user (lihat bawah).

---

## What Was Done

1. `tests/ocr_engine.py` — +engine `doctr` (OCR-006, v14).
2. `tests/paddle_probe_safe.py` — +`--engine doctr` (v14).
3. `tests/benchmark_doctr_probe.py` — probe 10 scan (v14).
4. `tests/benchmark_hybrid_ocr.py` (baru) — build korpus DocTR 49 scan +
   eval 4 varian (baseline/doctr/hybrid/oracle) pada subset scan/embedded,
   GT v9 + matcher v2. Merge rule + self-check `demo()`.
5. Korpus DocTR 49 scan: `ocr_experiment/corpus_doctr/` — 49/49 ok, 0 error,
   RSS ≤2.6GB, ~7.5s/cert. eval.json (DocTR-only 43.3%) + eval_hybrid_{10,49}.json
   + eval_embedded.json.
6. `docs/experiments_ledger.md` — +**HYB-001** (PASS).
7. `docs/report/runs_summary.md` + `.csv` — regenerate (55 runs, corpus_doctr masuk).

`pytest tests/` (--import-mode=importlib) → **31 passed**. `python -m
tests.benchmark_hybrid_ocr` self-check → merge rules ok. Produksi & GT tak
disentuh.

---

## Keputusan yang DIBUTUHKAN USER

1. **Integrasi produksi HYB-001?** Opsi:
   - **(a) Produksi penuh** — `ocr_fallback.py` jalankan 2 engine + merge field
     per cert. Cost ~16s/cert scan. Gain: organizer +4pt, MACRO +1pt.
   - **(b) Lazy** — DocTR hanya dipanggil saat field baseline lemah (mis.
     organizer tak cocok pattern, atau dates kosong). Hemat runtime, kompleksitas router.
   - **(c) Tunda** — kode eksperimen cukup; prioritas lain dulu.
2. **Promosi organizer_v2 + router rules + matcher** (menunggu sejak v11/v12).

---

## Key Files

| File | Peran |
|---|---|
| `tests/benchmark_hybrid_ocr.py` | Hybrid merge + eval (baru) |
| `tests/ocr_engine.py` | +engine `doctr` |
| `tests/paddle_probe_safe.py` | +`--engine doctr` |
| `tests/benchmark_runs/ocr_experiment/corpus_doctr/` | Korpus DocTR 49 + eval (gitignored) |
| `docs/experiments_ledger.md` | +OCR-006 (FAIL), +HYB-001 (PASS) |
| `backend/app/services/ocr_fallback.py` | Produksi — tetap, tak disentuh |

---

## Jangan Lakukan

- Ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Run benchmark tanpa GT v9 (v9 = baseline evaluasi)
- Uji CnOCR / MMOCR / re-run full DocTR replacement (ledger OCR-005/006)
- Sentuh `backend/` tanpa keputusan user (eksperimen selesai PASS, integrasi = user)
- RLIMIT_AS <8GB untuk DocTR (memecah torch — pakai watchdog RSS)
