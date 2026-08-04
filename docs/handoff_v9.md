# Handoff v9 — v8 Executed: Router Fix + LLM Bias Win, Layout Rejected

> Supersedes `docs/handoff_v8.md`. v8 was executed end-to-end (Phase 0-3, 5-7 of
> the v8 plan) with commits per experiment. This handoff records the actual
> results and the production integration.

---

## Current Baseline

| Metric | v7 P4 e_hybrid | **v8 f_bias (winner)** |
|--------|:-------------:|:----------------------:|
| Tingkat exact | 77.0% (57/74) | **82.4% (61/74)** |
| MACRO exact | 54.2% | **55.2%** |
| Eff. tokens/cert | 202 | 214 |
| LLM calls / 74 | 39 | **35** |
| Router decisions | 35 (100% prec) | **39 (100% prec)** |
| GT | raw | fixed_v8 |

Best run: `tests/benchmark_runs/run_llm_v4_20260804_115212/` (7 variants, router
on, GT v8 final).

---

## Context & Quick Reference

> Status: **eksperimental** — pendekatan ini bisa dikembangkan lebih lanjut
> (OCR, model GPU setelah ada data label, LLM API routing, dll). Handoff ini
> adalah referensi otoritatif; tabel benchmark di AGENTS.md belum diperbarui.

### A. Peta file kunci

| Area | File | Peran |
|---|---|---|
| Korpus teks | `tests/benchmark_runs/run_20260728_131835/extracted_texts/*.txt` | Input semua benchmark (74 stem) |
| Manifest PDF | `tests/layout_manifest.json` | stem → path PDF (74) |
| Benchmark runner | `tests/benchmark_llm_v4.py` | 7 variant (a–g), `--router on --organizer-variant phrase_v2` |
| Render OCR | `app/services/pdf_fast_path.py` `render_pdf_pages_to_png_bytes(zoom=3.0)` | PNG untuk OCR |
| OCR lama | `app/services/ocr_fallback.py` | RapidOCR + Tesseract (JANGAN sentuh sebelum pemenang OCR) |
| LLM client | `app/services/llm_tingkat.py` | Ollama + prompt f_bias; `ENABLE_LLM_TINGKAT` (default off) |
| Router | `app/services/tingkat_router.py` | rule-based tingkat, 39/74 @100% |
| Report | `docs/report/report_data.json` + `scripts/generate_report.py` | laporan data-driven |

### B. Environment & command benchmark

```bash
# Ollama (bila belum jalan)
setsid bash scripts/start_ollama.sh > /tmp/ollama.log 2>&1 &

# Benchmark (GT + korpus ditentukan via env)
GT_CSV_PATH=Ground_Truth_Sertifikat_v8.csv GT_TEXTS_DIR=tests/benchmark_runs/<korpus> \
  uv run python -m tests.benchmark_llm_v4 --organizer-variant phrase_v2 --router on
```

- `GT_VERSION` auto-derive dari nama CSV; `tests/benchmark_runs/` gitignored (hasil lokal).

### C. Korpus teks & membangun korpus OCR

- Format korpus: `stem.txt` (stem = nama PDF tanpa ekstensi); baris `#` diabaikan `read_text_file`.
- Scan vs teks: 25 PDF berteks embedded (pymupdf ≥60 char), 49 scan → fallback OCR.
- Bangun korpus baru: manifest `layout_manifest.json` → PDF bytes →
  `render_pdf_pages_to_png_bytes(pdf_bytes, zoom=3.0)` → OCR tiap PNG → tulis `stem.txt`.
- Ukur improvement: field accuracy subset scan (organizer/nomor/tingkat) + CER/WER antar korpus.

### D. Baca hasil benchmark

- `<run>/summary_variant_f_bias.json` — tingkat/macro exact
- `<run>/token_usage_f_bias.json` — tokens, calls, latency
- `<run>/router_decisions.json` — keputusan rule + precision
- `<run>/report.md` — ringkasan semua variant

### E. Update laporan (eksperimen baru)

1. Tambah entry ke `experiments[]` di `report_data.json`:
```json
{"id":"ocr_a","phase":"ocr","label":"OCR Trial A (PaddleOCR 3.0)","variant":"f_bias",
 "tingkat":"82.4%","macro":"55.2%","tokens_cert":214,"calls":35,
 "router":"39/74 @100%","gt":"fixed_v8","date":"Aug 4","notes":"..."}
```
2. `uv run python scripts/generate_report.py` → docx+md+xlsx dirakit ulang (tidak append).

### F. Gotchas

- Model Ollama: `llama3.1:8b` (bukan 3.2).
- `benchmark_runs/` gitignored — angka otoritatif di `report_data.json`/handoff.
- `EVAL_FIELDS` dipatch in-place di benchmark (mutasi list module).

### G. Jangan lakukan

- Ubah `Ground_Truth_Sertifikat.csv` (raw = history; `v8` = final).
- Jalankan ulang `scripts/generate_gt_review.py` (menimpa keputusan di `gt_review.xlsx`).
- Sentuh `ocr_fallback.py` produksi sebelum gate OCR lulus.
- Mulai model GPU (LayoutLMv3/DocParser/Donut/PaddleOCR-VL) sebelum ada 200–500 label.
- Ubah file v3 (`tests/llm_extractor_v3.py`) selama eksperimen.

---

## What Was Executed (history — ringkas; tidak wajib dibaca bila hanya eksekusi OCR)

| Phase | Commit | Ringkasan |
|---|---|---|
| P0 Harness | `c337b12` | repair benchmark (xlsx rows, taxonomy, metadata); baseline ±1pp |
| P1 GT audit | `8d5578f` | v8 CSV (3 koreksi) + tingkat evidence check; ceiling-adj 78.9% |
| P2 Router | `a2d0600` | contains-match + TINGKAT NASIONAL; 39/74 @100%, calls -53% |
| P3 Prompt | `0aa9679` | `f_bias` menang 82.4%; `g_evidence` regresi → ditolak |
| P4 Layout | `514b81f` | ditolak — OCR-bound (25/74 berteks embedded) |
| P5 Produksi | `b19d1c0` | `tingkat_router` + `llm_tingkat` + `organizer_v2`; UKM→Lainnya; 30 test pass |
| R1 Report gen | `e1ebb98` | `report_data.json` + `scripts/generate_report.py` |
| R2 GT review | `cc9a6b8` | `gt_review.xlsx` |
| G1 GT final | `8ba2561` | terapkan keputusan user ke v8 CSV |

---

## Final Ship Gate

| Metric | Target | Actual | Status |
|--------|:------:|:------:|:------:|
| Tingkat exact | >= 45% | 82.4% | PASS |
| MACRO exact | >= 50% | 55.2% | PASS |
| Eff. tokens/doc | <= 200 | 214 | MARGINAL |
| 100K-request tokens | <= 20M | 21.4M | MARGINAL |
| LLM call reduction | >= 40% | 53% | PASS |
| High-confidence rule precision | >= 95% | 100% | PASS |
| Date / certificate-number regression | none | none | PASS |

The token target is slightly exceeded (214 vs 200). Per the v8 rule
"preserve the accuracy floor first", the f_bias prompt ships as-is; a token
optimization is a follow-up, not a blocker.

---

## Docs / Reports

- Report workspace: `docs/report/` (see `README.md` for the docx/md convention).
- **Data-driven generator** (since `e1ebb98`):
  - Source: `docs/report/report_data.json` (meta, `experiments[]`, document blocks).
  - `scripts/generate_report.py` rebuilds all 4 reports **in full** (no append):
    `benchmark_methods`, `evaluation_methodology`, `phase_v4_methodology`,
    `phase_v4_results_summary` (docx + md + xlsx), tables auto-derived from
    `experiments[]`.
  - `scripts/build_report_data.py` — one-time migration of pre-append content.
    Do NOT need to run again; edit `report_data.json` directly.
  - **Workflow for a new experiment:** add one entry to `experiments[]` in
    `report_data.json` → `uv run python scripts/generate_report.py` → the new
    experiment lands in the correct section/table automatically.
- `docs/report/gt_review.xlsx` — manual GT review sheet (**DONE**, keputusan
  user sudah diterapkan ke v8 CSV via `scripts/apply_gt_review.py`; diff di
  `docs/report/gt_review_diff.txt`). Jangan jalankan ulang
  `scripts/generate_gt_review.py` (akan menimpa keputusan).
- `docs/gt_verification_report.txt` — regenerated with tingkat evidence checks.

## Commits

| Commit | Experiment |
|--------|-----------|
| `339a8cc` | R0: report workspace + md mirrors |
| `c337b12` | P0: harness repair, baseline reproduced |
| `8d5578f` | P1: GT audit + v8 CSV + verifier |
| `a2d0600` | P2: router contains-match + TINGKAT NASIONAL |
| `0aa9679` | P3: f_bias / g_evidence, f_bias wins |
| `514b81f` | P4: layout representation — rejected |
| `b19d1c0` | P5: production integration + UKM->Lainnya |
| `e1ebb98` | R1: data-driven report generator (report_data.json + scripts) |
| `cc9a6b8` | R2: gt_review.xlsx generator + review sheet |
| `8ba2561` | G1: apply GT review decisions -> v8 CSV final (Magang UKM label + tingkat confirmed) |

## Next Session — Execution Plan (sesi berikutnya)

### 1. GT review — ✅ SELESAI

- Keputusan user sudah diterapkan ke `Ground_Truth_Sertifikat_v8.csv`:
  tingkat final (`1966887`/`1981676` Nasional, `2954283` Internasional,
  `2030372` Nasional, `Airno` Nasional, `FIT` Internasional) + 3× Magang UKM
  `nama_kegiatan` → `Magang UKM Universitas Airlangga`. Raw CSV tidak diubah.
- Re-benchmark di GT final (`run_llm_v4_20260804_115212`): **f_bias 82.4% /
  55.2% / 214 tok** — identik, label Magang tidak menggeser angka.
- Tidak ada lagi action GT yang menunggu.

### 2. Eksperimen OCR — PaddleOCR 3.0 (keputusan user: ganti OCR)

**Alasan:** contoh garbled telah dikonfirmasi manual (Girifest `NOM0R:06/001/E`,
Venedict `UoinersitasAirlangga`, KARSA tanggal terserap). Hanya 25/74 PDF
berteks embedded; input quality = OCR-bound (organizer exact 16.2%).

**Riset (bahan referensi):**
| Paper | Relevansi |
|---|---|
| [2507.05595] PaddleOCR 3.0 Technical Report | Toolkit OCR+layout+table, PP-OCRv5, Apache, CPU-capable → **pilihan utama** |
| [2510.14528] PaddleOCR-VL (0.9B VLM) | Parsing dokumen langsung, 94.5% OmniDocBench → GPU, **tunda** |
| [2601.21957] PaddleOCR-VL-1.5 | Multi-task 0.9B VLM, robust in-the-wild → GPU, **tunda** |
| [2407.11985] Marksheet Parser pakai PaddleOCR | Preceden langsung: parsing form/sertifikat |
| [2505.20429] PreP-OCR | Restoration + post-OCR correction, CER -63.9~70.3% |
| [2508.21693] Line-Level OCR (Kraken+PARSeq) | Lebih baik untuk teks rapat sertifikat |
| [2508.14557] Internal Document Redundancy | OCR lebih baik via redundansi internal |
| [2508.06988] TADoc | Dewarping (CER 0.172 saat gagal) |
| [2509.11720] RT-DETR layout detection | Deteksi region header/body/signature |
| [2304.12484] DocParser / [2403.07553] Donut | OCR-free (skip OCR) → GPU, **tunda** |

**Trial structure** (setiap percobaan = 1 eksperimen terstruktur, bukan append):
1. Baseline: korpus RapidOCR+Tesseract saat ini (sudah ada).
2. **Trial A:** PaddleOCR 3.0 default (PP-OCRv5) pada semua cert.
3. **Trial B:** PaddleOCR + normalisasi line-merge (target token tergabung
   `BEMFKM`, `SERT2128BEM2026`).
4. **Trial C** (bila perlu): + preprocessing (binarize/contrast).

Tiap trial: bangun korpus baru (`GT_TEXTS_DIR=...`), jalankan benchmark → run
dir baru, tambah 1 entri `experiments[]` di `report_data.json`, commit.
Ukur per trial: CER/WER pada subset garbled, organizer/nomor/tingkat exact,
latency.

**Files:** `tests/ocr_engine.py` (seam ganti engine), `tests/benchmark_ocr.py`;
`backend/app/services/ocr_fallback.py` hanya disentuh setelah pemenang.
Dependency baru: `paddleocr`/`paddlepaddle` (pip) — eksperimen dulu di `tests/`.
**Gate:** organizer/nomor naik pada subset scan, tanpa regresi pada cert
berteks, latency < 2×.

### 3. Referensi biaya produksi (LLM API — untuk pilih model sesuai cost)

**Pricing per 1M token (USD, Agustus 2026):**

| Model | Input | Output | Cached | Tier |
|---|---|---|---|---|
| GPT-oss 20B (OpenAI open-weight) | **$0.08** | $0.35 | — | budget |
| Gemini 2.5 Flash-Lite | **$0.10** | $0.40 | $0.01 | budget |
| **DeepSeek V4 Flash** | **$0.14** | **$0.28** | $0.0028 | budget — best value |
| GPT-4o-mini | $0.15 | $0.60 | $0.075 | budget |
| GPT-4.1-nano | ~$0.10 | ~$0.40 | — | budget |
| Gemini 3.5 Flash-Lite | $0.30 | $2.50 | $0.15 | mid |
| DeepSeek V4 Pro | $0.435 | $0.87 | $0.0036 | mid reasoning |
| Claude Haiku 3.5 | $0.80 | $4.00 | — | mid |

> Catatan: Gemini 2.0 Flash deprecated (shut down Juni 2026). DeepSeek
> mengumumkan harga 2× saat peak window (09:00–12:00 & 14:00–18:00 WIB) —
> status: belum aktif. Angka harga bisa berubah; cek dokumen resmi provider.

**Estimasi workload kita** (f_bias, router on, ~214 eff tok/cert, ~99% input,
100K sertifikat ≈ 21.4M token):
- DeepSeek V4 Flash ≈ **$3.0** / 100K certs
- Gemini 2.5 Flash-Lite ≈ **$2.2** / 100K certs
- GPT-oss 20B ≈ **$1.8** / 100K certs

**Kesimpulan arsitektur termurah:** OCR CPU (RapidOCR → PaddleOCR 3.0, ~0
biaya) + rule/router (0 compute) + LLM API hanya untuk cert ambigu (router
sudah -53%). Model GPU (LayoutLMv3 126M, DocParser 70M, Donut 200M,
PaddleOCR-VL 0.9B) = GPU + fine-tune → **tunda** sampai ada 200–500 sertifikat
berlabel yang membenarkan biayanya.

### 4. Lanjutan lain (masih dari v9 sebelumnya)

- Token optimization f_bias (target ≤200 eff tok/cert).
- Kumpulkan 200–500 sertifikat terkoreksi sebelum fine-tune/classifier.
- Ukur duplicate-traffic (content-hash reuse) & Ollama concurrency sebelum
  keputusan scaling.
- A2 v2 full-field LLM integration tetap ditunda sampai path tingkat stabil.
