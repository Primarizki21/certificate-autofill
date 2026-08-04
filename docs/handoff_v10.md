# Handoff v10 — OCR Ditutup, Next: Robustness + Token Efficiency + CodeGraph Rule

> Supersedes `docs/handoff_v9.md`. Eksperimen OCR (§2 v9) selesai dan DITUTUP —
> semua engine GATE FAIL. Produksi tidak berubah (RapidOCR+Tesseract).
> Sesi berikutnya: bikin pipeline **robust** (terima sertifikat apa pun),
> **hemat token** (<200 tok/cert), **akurat** (>60% MACRO), dan **efisien**.

---

## Current Baseline

| Metric | v8 f_bias | Catatan jujur |
|--------|:---------:|---|
| Tingkat exact | **82.4%** (61/74) | Bagus. Field LLM. |
| MACRO exact | 55.2% (212/384) | Terbebani organizer (16.2%) & nama_kegiatan (24.3%). |
| MACRO fuzzy | **74.7%** (287/384) | String DEKAT — normalisasi adalah kunci. |
| Eff. tokens/cert | 214 | Target ≤200. Semua biaya di prompt (448 tok/call × 35). |
| LLM calls / 74 | 35 | Router cover 39/74 @100% prec. |
| Completion tokens | 4.3 tok/call | Diabaikan — jawaban satu kata. |

**Insight kunci:** gap 19.5pp antara fuzzy (74.7%) dan exact (55.2%) mayoritas
berasal dari **normalisasi string organizer**. Extractor mengembalikan
"Badan Eksekutif Mahasiswa Fakultas Teknologi Maju..." padahal GT "BEM FTMM".
Bisa diperbaiki dengan regex/string rules, tanpa ML.

---

## What Was Done (OCR Experiment — ✅ CLOSED)

4 engine diuji pada korpus 74 sertifikat (field-eval vs GT v8, extractor
produksi + organizer_v2 + mapper):

| Engine (scan) | organizer | nomor | dates | macro | latency | Verdict |
|---|---|---|---|---|---|---|
| **rapid_tess (produksi)** | 14.3% | **57.6%** | **85.7%** | **44.3%** | 8.6s | referensi |
| paddle 3.7 (PP-OCRv6) | — | — | — | — | 50s, 3.8GB | tidak viable (OOM WSL 8GB) |
| paddleocr 2.9 + paddle 2.6 | 18.4% | 39.4% | 80–83% | 39.8% | 7.1s | FAIL nomor |
| EasyOCR CPU (max-side 960) | 20.4% | 15.2% | 74–77% | 34.3% | 12.7s | FAIL nomor/dates |
| EasyOCR GPU (full-res) | 16.3% | 33.3% | 80–83% | 39.3% | 9.7s | FAIL — tidak diadopsi |

**Kesimpulan:** RapidOCR+Tesseract tetap produksi. Semua alternatif regresi pada
nomor (exact-match sensitif). GPU tidak diadopsi (bukan hasil terbaik; prioritas
user = CPU).

### Infrastruktur yang bertahan (reusable)

- `tests/paddle_probe_safe.py` — probe terkontrol (subprocess + RLIMIT_AS + RSS
  sampling); TIDAK bisa membekukan WSL. Temuan: RLIMIT_AS memblokir CUDA di WSL.
- `tests/benchmark_ocr.py` — `--per-cert-process`, `--prepend-embedded`,
  `--max-side`, `--gpu`, `--skip-existing`.
- `tests/ocr_engine.py` — seam engine (rapid/tess/paddle2&3/easy), version-aware.

---

## Process Rule: CodeGraph FIRST (semua edit kode)

**Sebelum edit kode apa pun** (eksperimen ATAU produksi), jalankan
`codegraph_explore` untuk memahami:
- Definisi & pemanggil symbol
- Call path (termasuk dynamic dispatch)
- Blast radius perubahan

Ini menghindari loop grep/read, menangkap caller tersembunyi, dan mengedit dengan
konteks penuh. Berlaku untuk:
- Kode eksperimen (`tests/`) — **sekarang**
- Kode produksi (`backend/`) — **nanti, saat menyentuh produksi**

Cara: SATU `codegraph_explore` per target edit. Output = source verbatim +
call path + blast radius. Perlakukan output sebagai sudah-Read. Jangan grep ulang.

---

## Next Session — Eksperimen

### Eksperimen 1: Organizer Normalization (MACRO uplift) ⭐ IMPACT TERTINGGI
- **Kenapa:** organizer fuzzy 75.7% tapi exact 16.2%. String dekat tapi beda
  bentuk. Contoh mismatch: GT "BEM FTMM" vs extractor "Badan Eksekutif Mahasiswa
  Fakultas Teknologi Maju...", "BEMFTMM" (tergabung), "BEM FTMM Bekerja Sama
  Dengan...", "Which Held From September21... by Himatesda".
- **Apa:** analisis 62 mismatch organizer → kategorisasi; tambah post-processing
  di `tests/organizer_extractor_v2.py`: abbreviation map, strip "Universitas
  Airlangga" (institusi induk), strip trailing context, split merged tokens,
  strip whitespace.
- **Gate:** organizer exact naik, MACRO naik, tidak regresi field lain.
- **Target:** organizer 16.2% → ~35% exact, MACRO 55.2% → ~62%.
- **Effort:** 1-2 jam. Risiko rendah. `codegraph_explore organizer_extractor_v2`.

### Eksperimen 2: Token Optimization (efisiensi)
- **Kenapa:** 214 eff tok/cert vs target ≤200. Semua biaya di prompt
  (448 tok/call × 35 = 15.702). Completion 4.3 tok/call (diabaikan).
- **Apa:** kurangi budget text adaptif di `tests/llm_extractor_v4.py`
  (strong 140→100, normal 200→150, poor_ocr 300→250); atau potong context block
  (~30 tok/call); atau perpendek instruksi.
- **Gate:** tingkat ≥82.4%, MACRO ≥55.2% (tidak regresi).
- **Target:** 214 → ~180 eff tok/cert.
- **Effort:** 1 jam. Risiko rendah. `codegraph_explore build_prompt_tingkat_bias minimize_text`.

### Eksperimen 3: Router Expansion (kurangi LLM calls)
- **Kenapa:** 35 cert ke LLM. Analisis 35 cert tsb: 11 punya sinyal parsial
  (univ_no_fak 7, hima_no_luar 5, bem_no_sem 5, fak_no_univ 3), 24 tanpa sinyal jelas.
- **Apa:** tambah rules kandidat di `tests/llm_router_v4.py`:
  `univ & !fak & !sem & !lomba → Universitas`; `hima & !luar → Departemen/Program
  Studi`; `fak & !univ → Fakultas`. VALIDASI precision di SEMUA 74 (bukan cuma 35).
- **Gate:** precision ≥95%, coverage naik.
- **Target:** 35 → ~25 LLM calls.
- **Effort:** 2-3 jam. Risiko sedang (validasi precision kritis).
  `codegraph_explore route_tingkat _sig _decide`.

### Eksperimen 4: Confidence-Based Field Routing (robust + efisien)
- **Kenapa:** router saat ini route seluruh cert; tapi bisa per-field. Field
  dengan confidence regex tinggi bisa skip LLM.
- **Apa:** setelah ekstraksi regex, cek confidence per-field
  (`ExtractedValue.confidence`); < threshold (0.7) → LLM utk field itu saja.
- **Gate:** tingkat ≥82.4%, LLM calls ≤35, tokens ≤214.
- **Target:** lebih robust (tangani edge case) + lebih sedikit LLM calls.
- **Effort:** 3-4 jam. Risiko sedang. `codegraph_explore map_tingkat_v8 route_tingkat`.

### Eksperimen 5: Multi-Field LLM Extraction (akurasi + hemat token)
- **Kenapa:** LLM cuma ekstrak tingkat, padahal model lihat teks penuh. Bisa juga
  ekstrak organizer dalam SATU call (hemat token + konteks membantu tingkat).
- **Apa:** modifikasi prompt f_bias utk minta tingkat + organizer; parse 2 field;
  organizer LLM sebagai fallback saat confidence regex rendah.
- **Gate:** tingkat ≥82.4%, organizer membaik, tokens ≤214.
- **Target:** tingkat + organizer satu call, token sama/lebih rendah.
- **Effort:** 2-3 jam. Risiko sedang. `codegraph_explore call_ollama infer_tingkat`.

### Eksperimen 6: Content-Hash Caching (efisiensi duplikat)
- **Kenapa:** PDF yang sama di-upload 2x → diproses ulang penuh.
- **Apa:** SHA-256 PDF bytes → cek database utk ekstraksi hash sama → return cache
  (skip OCR + LLM).
- **Gate:** tidak ada perubahan akurasi; latency duplikat → <100ms.
- **Target:** sertifikat duplikat selesai instan.
- **Effort:** 1-2 jam. Risiko rendah. `codegraph_explore run_extraction_pipeline job_processor`.

### Eksperimen 7: Label Collection (investasi jangka panjang)
- **Kenapa:** fine-tune classifier butuh 200-500 label terkoreksi. Ini opsi
  "nuklir" utk hemat token (ganti LLM sepenuhnya).
- **Apa:** basis `gt_review.xlsx` (74 reviewed); upload batch baru → ekstrak →
  review → label; simpan `Ground_Truth_Sertifikat_v10.csv`.
- **Gate:** minimal 200 cert terkoreksi sebelum fine-tune.
- **Effort:** ongoing (review manual). Tanpa kode.

---

## Execution Order (prioritas)

| # | Eksperimen | Effort | Impact | Kerjakan |
|---|---|---|---|---|
| 1 | Organizer normalization | 1-2h | ⭐⭐⭐ MACRO +7pp | PERTAMA |
| 2 | Token optimization | 1h | ⭐⭐ tokens -34 | PERTAMA |
| 3 | Router expansion | 2-3h | ⭐⭐ LLM calls -10 | PERTAMA |
| 6 | Content-hash caching | 1-2h | ⭐ efisiensi duplikat | PERTAMA |
| 5 | Multi-field LLM | 2-3h | ⭐ akurasi + tokens | Setelah 1-3 |
| 4 | Confidence-based routing | 3-4h | ⭐ robust | Setelah 1-3 |
| 7 | Label collection | ongoing | ⭐⭐⭐ future | Paralel |

**Target sesi berikutnya (4-6 jam):** Eksperimen 1 + 2 + 3 + 6. Hasil:
MACRO ~62%, tokens ~180, LLM calls ~25, duplikat ter-cache. Semua edit pakai
`codegraph_explore` dulu.

---

## Yang TIDAK Layak Dilakukan (jujur)

- **Engine OCR lagi** — terbukti tak ada yang menang baseline di dataset ini.
- **Model GPU (LayoutLMv3/Donut)** — butuh 200-500 label dulu.
- **LLM API routing ke model murah** — sudah $3/100K cert (tak signifikan).
- **Multi-field LLM utk SEMUA field** — menambah token, akurasi marginal.
- **Ensemble extraction** — kompleksitas vs benefit terlalu rendah.
- **Parallel Ollama requests** — latency sudah 357ms/call (cukup cepat).

---

## Key Files untuk Sesi Berikutnya

| File | Peran |
|---|---|
| `tests/organizer_extractor_v2.py` | Ekstraksi organizer — tambah normalisasi |
| `tests/llm_extractor_v4.py` | Prompt f_bias — kurangi text budget |
| `tests/llm_router_v4.py` | Router — tambah rules cert tak tercover |
| `tests/evaluation_framework.py` | Field eval — gate checks |
| `backend/app/services/field_extractor.py` | Regex extraction — cek pola nomor |
| `backend/app/services/form_mapper.py` | Field mapping — confidence thresholds |

---

## Jangan Lakukan

- Ubah `Ground_Truth_Sertifikat.csv` (raw = history)
- Mulai model GPU sebelum ada 200-500 label
- Ubah file v3 (`tests/llm_extractor_v3.py`)
- Sentuh `ocr_fallback.py` produksi
- Edit kode tanpa `codegraph_explore` dulu
- Push tanpa review — semua perubahan via PR
