# Handoff v16 — NC-001 PASS: Preprocessing nomor (re-render region zoom 6×)

> Supersedes `docs/handoff_v15.md`. Sesi ini:
> - **NC-001 — preprocessing nomor sertifikat: PASS semua gate.** Anchor
>   SEMANTIK (baris `NOMOR`/pola nomor via bbox RapidOCR) → crop → re-render
>   region PDF di zoom 6× → re-OCR baseline rapid_tess. Tanpa hardcode
>   koordinat. Produksi `backend/` TIDAK disentuh.
> - Eksperimen jawaban untuk pertanyaan user "OCR final? bisa diringankan?":
>   engine-swap = closed (OCR-001..006); yang bisa naik = preprocessing nomor.

---

## NC-001 — Preprocessing nomor (re-render region, robust, tanpa koordinat)

### Desain
Nomor sertifikat = bottleneck semua engine (baseline scan 57.6%). Gagasan:
perbaiki kualitas glyph di REGION nomor, bukan ganti engine. Robust tanpa
hardcode koordinat template:

1. Render halaman zoom 3× → RapidOCR → **bbox per baris**.
2. Anchor **semantik**: baris ber-keyword `NOMOR`/`NO.`/`NUMBER`, fallback
   baris ber-pola nomor (`NN/…/YYYY`).
3. Crop region baris itu (margin + ekstensi kanan/bawah utk angka di baris
   berikut) → **re-render langsung dari PDF** (`clip` + matrix zoom 6×) —
   piksel NYATA utk scan native dpi > 216 (33/49 cert; render 3× hanya
   216dpi, di bawah native 220-342dpi).
4. Re-OCR region dgn baseline rapid_tess. Merge = **voting disagreement**:
   crop dipakai HANYA bila nomornya ≠ baseline (`NOMOR : <crop>` prepended,
   extractor menangkap pola ber-label dulu). Anchor tak ditemukan / crop
   tanpa nomor strict → baseline utuh = no-regress by construction.

Ver1 (upscale digital LANCZOS dari render 3×) = **0 gain** — interpolasi
tidak menambah info. Ver2 (re-render zoom 6×, piksel nyata) = **+3.0pt**.

### Hasil (GT v9 + matcher v2, subset scan 49)

| Varian | nomor | dates | organizer e/f | MACRO |
|---|---|---|---|---|
| baseline rapid_tess | 57.6% | 85.7% | 20.4% / 61.2% | 45.8% |
| NC-001 crop (upscale digital) | 57.6% (=) | 85.7% | 20.4% / 61.2% | 45.8% |
| **NC-001 crop (re-render 6×)** | **60.6%** | **85.7%** | **20.4% / 61.2%** | **46.3%** |

Flip nyata: **Falcon_Faiz** `XI1/2024` → `XII/2024` (= GT) — re-render
pulihkan numeral dari piksel nyata (bukti mekanisme). 4 disagreement lain
tetap salah (keterbatasan sumber). anchor_miss 22/49 (rapid tak menemukan
baris nomor di render 3×). Runtime tambahan ~5.2s/cert.

**Gates (NC-001):** nomor 60.6% > 57.6% ✅ · dates 85.7% = ✅ · organizer
20.4%/61.2% = ✅ · MACRO 46.3% > 45.8% ✅ · tanpa hardcode koordinat ✅ ·
embedded tak tersentuh (hanya subset scan) ✅

### Verdict
**NC-001 PASS** — gate met, gain kecil (+3.0pt nomor, +0.5pt MACRO) tapi
mekanisme tervalidasi. Upscale digital (ver1) = jangan dipakai.

---

## Keputusan yang DIBUTUHKAN USER

1. **Integrasi produksi NC-001?** Rekomendasi: **lazy** — re-render crop
   HANYA saat nomor baseline hilang/low-confidence (bukan semua cert), masuk
   sebagai 2-pass number di `ocr_fallback.py`. Cost ~+2-5s/cert HANYA utk
   cert yang butuh. Gain +3.0pt nomor.
2. **Promosi v9** (organizer_v2 ORG-001 + router dept/luar raw_text +
   matcher v2 sebagai standar evaluasi) — menunggu sejak v11/v12, terpisah
   dari OCR.
3. **HYB-001 (DocTR hybrid)**: rekomendasi SKIP produksi — gain tersebar
   (+1pt MACRO), lazy lemah, full mahal (+7.5s/cert). Catat sebagai
   keputusan data-driven.

---

## What Was Done

1. `tests/benchmark_nomor_crop.py` (baru) — build (anchor bbox RapidOCR →
   re-render region zoom 6× → re-OCR rapid_tess → merge voting-disagreement)
   + eval (reuse `benchmark_ocr.cmd_eval`, GT v9) + self-check `demo()`.
2. Korpus `ocr_experiment/corpus_nomor_crop/` — 49/49 ok, cropped=5,
   anchor_miss=22, +5.2s/cert. eval.json (nomor 60.6%, MACRO 46.3%).
3. Baseline re-eval fresh GT v9: `baseline_rapid_tess/eval_v9.json` (nomor
   57.6%) — eval.json lama stale (matcher/GT lama), gate pakai re-eval ini.
4. `docs/experiments_ledger.md` — +**NC-001** (PASS).
5. `docs/report/report_data.json` + generate_report.py (md + docx + xlsx) —
   +entri NC-001; `docs/report/runs_summary.md` + `.csv` — regenerate (56
   runs, corpus_nomor_crop scan=49, nomor 60.6%).
6. Handoff v15 → v16.

`pytest tests/` → **31 passed**. `python -m tests.benchmark_nomor_crop`
self-check → anchor + merge rules ok. Produksi & GT tak disentuh.

> **CATATAN DOCX**: generate_report.py menulis ulang
> `benchmark_methods.docx` + `evaluation_methodology.docx` yang sebelumnya
> sudah `M` (perubahan user yang belum di-commit). Kalau ada edit manual user
> di docx itu, sudah tergantikan oleh regenerasi dari report_data.json —
> perlu diverifikasi/ulangi edit manual bila ada.

---

## Addendum — Konsistensi laporan lengkap (pasca-audit user)

Audit konsistensi 4 sumber (ledger / runs_summary / handoff / report_data-docx)
menemukan: report_data.json kurang entri **OCR-006** (DocTR probe) dan
**HYB-001** (hybrid) → docx report tak memuat seluruh eksperimen. Diperbaiki:

1. `docs/report/report_data.json` — +`ocr_006_doctr` (macro 40.0%) +
   `hyb_001` (macro 46.8%), angka persis dari ledger/handoff → **14 eksperimen**.
2. `baseline_rapid_tess/eval.json` ← re-eval segar GT v9 + matcher v2
   (sebelumnya stale 44.3%/org 14.3% → kini 45.8%/org 20.4%, konsisten dgn
   handoff/HYB/NC-001).
3. `scripts/generate_runs_summary.py` — scan_ocr_trials kini juga membaca
   `eval_hybrid_*.json` → row `[hybrid_10]` 42.2% + `[hybrid_49]` 46.8%
   tampil di runs_summary (sebelumnya hanya DocTR-only 43.3%).
4. `scripts/generate_report.py` — **styling docx**: header tabel indigo
   `1F3864` + teks putih, border lembut, baris selang-seling, highlight baris
   pemenang (progression), heading berwarna accent — profesional, tak
   mengganggu baca.
5. Regenerate report (docx + md + xlsx) + runs_summary → docx kini memuat
   **seluruh 14 eksperimen** (comparison/progression/results).

Keputusan user: trial easy/paddle tetap historis (konsisten dgn ledger
OCR-002..004), hanya baseline referensi yang dibenahi. Docx **di-commit**
kali ini (deliverable report konsisten dgn source-of-truth report_data).

---

## Key Files

| File | Peran |
|---|---|
| `tests/benchmark_nomor_crop.py` | Eksperimen (baru) |
| `tests/benchmark_runs/ocr_experiment/corpus_nomor_crop/` | Korpus + eval (gitignored) |
| `tests/benchmark_runs/ocr_experiment/baseline_rapid_tess/eval_v9.json` | Baseline referensi GT v9 |
| `docs/experiments_ledger.md` | +NC-001 (PASS) |
| `backend/app/services/ocr_fallback.py` | Produksi — tetap, tak disentuh |

---

## Jangan Lakukan

- Ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Run benchmark tanpa GT v9 (v9 = baseline evaluasi)
- Pakai upscale digital utk region nomor (NC-001 ver1 = 0 gain; hanya
  re-render PDF nyata yang menambah piksel)
- Re-run DocTR full-replacement / CnOCR / MMOCR (ledger OCR-005/006)
- Integrasi produksi tanpa keputusan user
