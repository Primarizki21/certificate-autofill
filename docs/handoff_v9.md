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

## What Was Executed

### Phase 0 — Harness repair
`c337b12` — `results.xlsx` populated, taxonomy tied to explicit
`TAXONOMY_VARIANT` (e_hybrid), report lists all variants, eff. tokens/cert
amortized over 74, GT/text paths overridable via env, router rule traced in
`router_decisions.json`. Baseline reproduced within 1pp.

### Phase 1 — GT audit
`8d5578f` — `Ground_Truth_Sertifikat_v8.csv` (3 audited corrections) +
tingkat scale-evidence check in `verify_ground_truth.py`. Effect was net-zero
on the count (1981676 correct->wrong, 2954283 wrong->correct) but makes the
evaluation honest. Ceiling-adjusted (excl. 3 disputed): 56/71 = 78.9%.

### Phase 2 — Router contains-match + TINGKAT NASIONAL
`a2d0600` — BEM/HIMA detected in uppercase alnum runs with a guard; explicit
`TINGKAT/LOMBA NASIONAL` rule. Routed 39/74 at 100% precision, LLM calls
35 (-53%). e_hybrid on fixed GT: 60/74 = 81.08%.

### Phase 3 — Prompt variants f_bias / g_evidence
`0aa9679` — `f_bias` (English != International, Indonesian context wins) won at
**82.4%**; fixed data-slayer, 2955331, IRIS without regressions. `g_evidence`
(FaR-style evidence output) regressed to 75.7% and was rejected. A compressed
bias version cut tokens to 197 but lost accuracy (78.4%) and was rejected —
accuracy floor takes precedence per v8 rules.

### Phase 4 — Layout-aware input
`514b81f` — markdown (`##` title) and annotated (`[TITLE]`) representations
from PyMuPDF dict. **Rejected**: only 25/74 PDFs have embedded text (rest are
scanned); both variants underperformed plain text (77.0% / 78.4% vs 82.4%) and
markers disturbed the deterministic extractors. Input quality is OCR-bound.

### Phase 5 — Production integration
`b19d1c0` — `backend/app/services/` gained `tingkat_router.py`,
`llm_tingkat.py`, `organizer_v2.py` (ports, no tests dependency).
`form_mapper.map_tingkat_v8` = router -> LLM (if `ENABLE_LLM_TINGKAT`) ->
legacy rules. UKM now maps to `Lainnya`. Full suite: **30 passed**.

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
