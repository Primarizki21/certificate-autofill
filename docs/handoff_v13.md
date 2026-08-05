# Handoff v13 — Exp 5 FAIL (token); OCR Re-analysis: DocTR kandidat baru

> Supersedes `docs/handoff_v12.md`. Sesi ini:
> - **Exp 5 (multi-field LLM: tingkat+organizer 1 call)**: **GATE FAIL** pada
>   token (195 > 176). Variant C (LLM organizer hanya untuk cert organizer-miss,
>   oracle GT = ceiling experiment). Accuracy naik tapi budget token tak
>   tercapai — multi-field di luar anggaran.
> - **OCR re-analysis** (saran user): 3 tool dievaluasi → **DocTR = kandidat
>   terbaik untuk probe**. CnOCR redundant (keluarga PP-OCR, sama RapidOCR di
>   pipeline), MMOCR stale + dependency berat.
> - **Matcher/GT tetap GT v9 + matcher v2** (baseline evaluasi tak berubah).

---

## Exp 5 — Multi-field LLM (tingkat + organizer, 1 call): GATE FAIL

### Desain
Prompt berbasis f_bias (pemenang v9) + instruksi ekstraksi penyelenggara.
Variant C (ceiling experiment): LLM organizer HANYA untuk cert yang pipeline
organizer-nya MISS (tidak exact & tidak fuzzy pasca matcher v2). Cert yang
sudah exact/fuzzy tetap pakai f_bias (no-regress). Oracle selection pakai GT
→ mengukur CEILING, bukan runtime selector (runtime selector = follow-up).

- Cert rule-routed → tingkat rule, organizer pipeline, tanpa call (45 cert)
- Cert ke-LLM & organizer miss → multi-field prompt (8 cert)
- Cert ke-LLM & organizer OK → f_bias biasa (21 cert)

### Hasil run (`tests/benchmark_runs/run_llm_v5_exp5_20260805_211624`)

| Metric | Baseline v9 | Exp5 verbose | Exp5 compact | Gate |
|---|---|---|---|---|
| tingkat exact | 83.8% | **83.8%** ✅ | **81.1%** ❌ | ≥83.8% |
| organizer exact | 39.2% | **41.9%** | **43.2%** | naik |
| organizer fuzzy | 79.7% | **85.1%** | **85.1%** | naik |
| MACRO exact | 60.2% | **60.7%** | **60.4%** | naik |
| LLM calls | 29 | **29** ✅ | **29** ✅ | ≤29 |
| tokens/cert | 176 | **195** ❌ | **185** ❌ | ≤176 |

- **Verbose**: tingkat no-regress, organizer naik (+2.7 exact, +5.4 fuzzy),
  tapi token 195 > 176 (prompt multi-field ~150 tok/call lebih panjang dari
  f_bias → +1407 token total = +19/cert).
- **Compact** (instruksi organizer 109→28 tok, max_tokens 80→50): token turun
  ke 185 tapi **tingkat regress −2.7pt** — instruksi terlalu dipangkas, LLM
  kehilangan fokus tingkat.
- **Kesimpulan**: gate token ≤176 tak tercapai — menambah field kedua punya
  cost intrinsik +10–19 tok/cert. Compress lebih jauh merusak tingkat.

### Detail miss set (20 cert)
8 cert dapat multi-field call → 4 jadi exact, 9 jadi exact/fuzzy. Multi-field
berhasil fix: `2439919 (UB)`, `Primarizki_kim_unair_2024`, `Hitech_Faiz`,
`SDC Uniska`. **TIDAK** fix 7× `Faculty of Science and Technology ... Dept.`
(GT valid — LLM multi gagal produce dept penuh; masih pipeline-gap).

### Verdict
**EXP5-001 GATE FAIL** (token ≤176 tak tercapai). Kode eksperimen tetap di
`tests/llm_extractor_v5.py` + `tests/benchmark_exp5.py`, tercatat di ledger,
tidak dipakai produksi. Re-try hanya bila budget token dilonggarkan (≤200)
atau pindah ke model/API yang lebih hemat prompt.

---

## OCR Re-analysis — DocTR kandidat baru (saran user)

### Latar
OCR sebelumnya ditutup (handoff v10, ledger OCR-001..004): PaddleOCR OOM,
EasyOCR/paddle semua GATE FAIL pada **nomor** (digit OCR buruk vs baseline
59.6%). Pipeline produksi = RapidOCR + Tesseract (`ocr_fallback.py`).

### 3 Tool dievaluasi

| Tool | Keluarga model | Maintenance | Berat/deps | Veredict |
|---|---|---|---|---|
| **CnOCR** (breezedeus) | PP-OCR (ONNX) | aktif (v2.3.3) | ringan (ONNX, model 2.3–12MB) | **SKIP — redundant**: keluarga model SAMA dengan RapidOCR yang sudah di pipeline (`rapidocr-onnxruntime`). Tak menambah sinyal baru. |
| **MMOCR** (open-mmlab) | DBNet/CRNN/SAR | **stale** — PyPI terakhir Jul 2023 (~3 th) | berat: butuh mmcv/mmengine/mmdet, konfig kompleks | **SKIP**: risiko dependency hell di WSL 8GB, tanpa maintenance, akurasi uji komunitas kalah EasyOCR/PPOCR di teks sejajar. |
| **DocTR** (mindee) | **CRNN / SAR / ViTSTR / PARSeq** — keluarga baru | **aktif** (v1.0.1 Feb 2026, 5.8k stars) | torch (sudah ada di proyek), ada varian MobileNet utk CPU | **KANDIDAT**: keluarga model belum pernah dicoba, English/Latin out-of-box, layout-aware (block/line/word), 2-stage det+rec swappable. |

### Kenapa DocTR layak probe
1. **Keluarga model baru** — bukan ulang PaddleOCR/EasyOCR yang sudah FAIL.
2. **Active maintenance** — v1.0.1 Feb 2026, kontras MMOCR stale 2023.
3. **Latin out-of-box** — CRNN/ViTSTR trained untuk teks cetak dokumen (FUNSD/
   CORD benchmark ≈ Google Vision/Textract), cocok sertifikat Bahasa Indonesia.
4. **Layout-aware output** — block/line/word hierarchy → bantu pipeline-gap
   `Faculty of Science and Technology Information System Dept.` (organizer
   multi-kata yang segmennya berserak) + nomor/ tanggal pada cert scan.
5. **Varibel arsitektur** — `db_mobilenet_v3_large + crnn_mobilenet_v3_small`
   untuk CPU (30+ FPS claim), `db_resnet50 + sar_resnet31` untuk akurasi.

### Gate probe (rekomendasi)
- **Probe terkontrol dulu (5–10 cert scan)**: ukur nomor + tanggal + organizer
  DocTR vs RapidOCR+Tesseract baseline. Gate: **nomor ≥59.6%** (baseline saat
  ini) ATAU organizer naik pada subset scan, tanpa OOM di WSL 8GB.
- Hanya kalau probe PASS → run penuh + integrasi `ocr_fallback.py` sebagai
  engine ketiga (produksi butuh keputusan user).

---

## What Was Done

1. `tests/llm_extractor_v5.py` (baru) — prompt multi-field `build_prompt_multi`
   + `parse_multi_response` (+ self-check). Compact setelah optimasi token.
2. `tests/benchmark_exp5.py` (baru) — benchmark Exp 5 variant C, evaluasi
   GT v9 + matcher v2, router on, oracle miss-selection.
3. Run: `run_llm_v5_exp5_20260805_211624` (verbose 195 tok) +
   `run_llm_v5_exp5_20260805_211929` (compact 185 tok).
4. `docs/experiments_ledger.md` — +**EXP5-001** (GATE FAIL token), +**OCR-005**
   (analisis 3 tool → DocTR kandidat).
5. (Belum) `runs_summary.md` + `report_data.json` update — menunggu verdict
   final user (FAIL dicatat, tapi run Exp5 bukan kandidat laporan utama).

`pytest tests/` → **31 passed** (0.14s). Produksi `backend/` TIDAK disentuh.

---

## Keputusan yang DIBUTUHKAN USER

1. **Promosi produksi** (organizer_v2 + router rules + matcher?): masih
   menunggu (dari v11/v12).
2. **Exp 5**: sudah FAIL dicatat. Lanjut tutup? Atau re-try dengan budget
   token ≤200?
3. **DocTR probe**: setuju untuk coba? (Butuh `pip install python-doctr`,
   probe 5–10 cert scan dulu, gate nomor ≥59.6%.)

---

## Key Files

| File | Peran |
|---|---|
| `tests/llm_extractor_v5.py` | Exp 5 prompt multi-field (experiment, FAIL) |
| `tests/benchmark_exp5.py` | Exp 5 benchmark variant C |
| `tests/benchmark_runs/run_llm_v5_exp5_*/` | Hasil run verbose (195) + compact (185) |
| `docs/experiments_ledger.md` | +EXP5-001, +OCR-005 |
| `backend/app/services/ocr_fallback.py` | Produksi OCR saat ini (RapidOCR+Tesseract) — target DocTR probe |

---

## Jangan Lakukan

- Ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Run benchmark tanpa `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Campur matcher ke eksperimen pipeline
- Uji CnOCR (redundant PP-OCR) / MMOCR (stale) — lihat OCR-005
- Sentuh `backend/` tanpa keputusan user
- Re-run Exp 5 tanpa melonggarkan gate token (≤200)
