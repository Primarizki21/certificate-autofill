# Execution Plan: Tesseract-to-LLM Extraction Benchmark (Gemini 2.5 Flash, 2.5 Flash-Lite, 3.1 Flash-Lite)

## Context
Evaluasi komparatif direct extraction end-to-end: teks raw OCR Tesseract (korpus terbaik `tesseract_primary_v4`, 74 sertifikat) diekstrak langsung oleh 3 model Google Gemini (`gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3.1-flash-lite`) menjadi 6 field terstruktur JSON tanpa layer regex/rule extraction tradisional. Seluruh metrik akurasi (Matcher v2 vs GT v9), token input/output/cache, latensi, dan estimasi biaya (USD & IDR per kurs Rp17.758,00 per 2 Agustus 2026) dicatat secara presisi dan transparan dalam format `.json`, `.csv`, dan `.md`, dilengkapi 4 lapis pembuktian empiris sesuai protokol AGENTS.md.

---

## Flaw Analysis & Pre-Execution Fixes (Audit Temuan Sebelum Eksekusi)

Sebelum memulai eksperimen, audit komprehensif terhadap plan menemukan 8 flaw kritis berikut yang telah diperbaiki:

1. **Flaw 1 (Security - API Key URL Leakage)**:
   - *Masalah*: Meletakkan `?key={api_key}` pada query string URL menyebabkan API key terekspos di log HTTP, proxy, traceback, dan exception logs.
   - *Fix*: Menggunakan HTTP header `x-goog-api-key: {api_key}` sebagai metode autentikasi utama, dengan query parameter `?key=` hanya sebagai fallback sekunder. API key disanitasi dari semua representasi error dan log.

2. **Flaw 2 (Reproducibility & Determinism - Missing `temperature: 0.0`)**:
   - *Masalah*: Plan awal tidak mendefinisikan `temperature: 0.0`. Default temperature Gemini (~1.0) menghasilkan variasi stokastik antar pemanggilan sehingga benchmark tidak reproduktif.
   - *Fix*: Wajib menyertakan `generationConfig: {"temperature": 0.0, "responseMimeType": "application/json"}` pada payload API.

3. **Flaw 3 (Structured JSON Output Guarantees & Markdown Stripping)**:
   - *Masalah*: Tanpa `responseMimeType: "application/json"`, Gemini dapat menghasilkan format conversational atau membungkus respons dengan markdown fences (` ```json ... ``` `) yang menyebabkan `json.loads` gagal.
   - *Fix*: Menyetel `responseMimeType: "application/json"` di `generationConfig` dan melengkapi parser dengan pembersih regex markdown code block (`r"^```(?:json)?\s*(.*?)\s*```$"`) sebagai safety fallback.

4. **Flaw 4 (Date Format Normalization & Matcher v2 Compatibility)**:
   - *Masalah*: Matcher v2 (`normalize_date`) mengembalikan `None` jika format tanggal ISO `YYYY-MM-DD` atau variasi teks lain dikembalikan LLM. Kegagalan format berakibat mismatch artifisial.
   - *Fix*: Menambahkan normalizer tanggal defensif di `gemini_field_extractor.py` yang menstandardisasi segala variasi tanggal valid (ISO, text ID/EN, slash/dash) menjadi format baku `DD/MM/YYYY` sebelum dievaluasi Matcher v2.

5. **Flaw 5 (Rate Limiting, RPM Exhaustion & Pacing Delay)**:
   - *Masalah*: Retry 2s, 4s, 8s terlalu singkat saat terkena HTTP 429 quota/RPM limit, dan pemanggilan beruntun tanpa jeda berisiko memicu burst rate limit.
   - *Fix*: Menyediakan jeda pacing antar-request (`request_delay`, default 1.2s - 1.5s), parsing header `Retry-After`, serta backoff hingga 15s-30s saat menerima respons 429.

6. **Flaw 6 (Token Accounting Null-Safety)**:
   - *Masalah*: `cachedContentTokenCount` dan `thoughtsTokenCount` pada `usageMetadata` bersifat opsional dan sering tidak ada pada respons non-thinking/non-cached, berisiko memicu `KeyError`.
   - *Fix*: Akses dictionary `usageMetadata` wajib menggunakan metode `.get(..., 0)` yang null-safe, dan pembiayaan `thoughts_tokens` diakumulasikan ke tarif output tokens.

7. **Flaw 7 (4-Layer Empirical Proof Scalability)**:
   - *Masalah*: Menjalankan OOD penuh (mutasi + 3 level noise = 296 panggilan ekstra) untuk semua 3 model akan menghabiskan kuota dan waktu yang tidak perlu.
8. **Flaw 8 (Model Verification & Compatibility)**:
   - *Masalah*: Ketersediaan model `gemini-2.5-flash`, `gemini-2.5-flash-lite`, dan `gemini-3.1-flash-lite` harus diverifikasi terhadap endpoint resmi Google API.
   - *Fix*: Terverifikasi langsung via API query bahwa ketiga nama model tersebut valid dan tersedia di endpoint `v1beta/models`.

9. **Flaw 9 (Critical Blocker - Missing `full_text` in Form Mapper Integration)**:
   - *Masalah*: `map_fields_to_form()` di `backend/app/services/form_mapper.py` membaca `extracted.get("full_text")` untuk memetakan `kelompok_kegiatan`, `jenis_kegiatan`, `jenis_penyelenggara`, dan fallback tingkat. Jika LLM hanya mengembalikan 6 field tanpa `full_text`, mapper akan gagal menghasilkan metadata pendukung secara silent error.
   - *Fix*: Alih-alih meminta LLM memboroskan token output dengan mengembalikan ulang seluruh teks, adapter `gemini_field_extractor.py` secara otomatis menginjeksi teks mentah Tesseract sebagai `extracted["full_text"] = ExtractedValue(raw_ocr_text, 1.0, "tesseract_raw")` sebelum memanggil `map_fields_to_form()`.

---

## Approach

### 1. Modul Client Google Gemini & Token/Cost Ledger (`tests/gemini_client.py`)
- **Tujuan**: Komunikasi langsung ke endpoint Google Generative Language REST API (`https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`) via header `x-goog-api-key` tanpa dependensi pihak ketiga baru (memakai standard library `urllib.request`).
- **Pembacaan Kredensial**: Membaca `.env.google` secara otomatis (`GOOGLE_API_KEY`), dengan fallback `os.environ["GOOGLE_API_KEY"]`. Sanitasi otomatis kunci dari semua error/log.
- **Tabel Tarif Resmi Google Gemini (USD per 1M tokens, Standard Paid Tier)**:
  - `gemini-2.5-flash`: Input: **$0.30**, Output: **$2.50**, Cache Read: **$0.03**
  - `gemini-2.5-flash-lite`: Input: **$0.10**, Output: **$0.40**, Cache Read: **$0.01**
  - `gemini-3.1-flash-lite`: Input: **$0.25**, Output: **$1.50**, Cache Read: **$0.025**
- **Kurs Konversi**: `EXCHANGE_RATE_IDR_PER_USD = 17758.0` (flat per 2026-08-02, dapat di-override via env).
- **Perhitungan Biaya**:
  - `cost_usd = (prompt_tokens * input_rate + (candidates_tokens + thoughts_tokens) * output_rate + cached_tokens * cache_rate) / 1_000_000.0`
  - `cost_idr = cost_usd * EXCHANGE_RATE_IDR_PER_USD`
- **Data Class `GeminiCallResult`**:
  - `response_text: str`
  - `parsed_json: dict | None`
  - `prompt_tokens: int`
  - `candidates_tokens: int`
  - `cached_tokens: int`
  - `thoughts_tokens: int`
  - `total_tokens: int`
  - `cost_usd: float`
  - `cost_idr: float`
  - `latency_s: float`
  - `model: str`
  - `status: str` ("success" | "rate_limited" | "error")
  - `error_message: str | None`
- **Pacing Delay & Adaptive Retry**: Pacing delay default 1.2 detik antar-request. Exponential backoff (interval 2s, 8s, 20s, hingga 30s bila terdeteksi HTTP 429) dengan parsing header `Retry-After`.

### 2. Prompt Engineering & JSON Schema Extraction (`tests/gemini_field_extractor.py`)
- **System Instruction Baku**:
  ```text
  Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
  Tugas Anda: mengekstrak informasi faktual dari teks OCR mentah sertifikat ke dalam format JSON yang presisi.
  Aturan Wajib:
  1. Ekstrak HANYA informasi yang tertulis di teks OCR sertifikat. Jangan berhalusinasi.
  2. Format Tanggal: Wajib "DD/MM/YYYY" (contoh: 24/08/2024). Jika rentang tanggal, pisahkan mulai dan selesai. Jika hanya satu tanggal, isi mulai dan selesai dengan tanggal yang sama.
  3. Nomor Sertifikat: Ambil lengkap beserta tanda garis miring atau titik (contoh: 123/UN3.1/KM/2024).
  4. Penyelenggara: Nama organisasi/lembaga pelaksana (contoh: BEM FTMM Universitas Airlangga, Himpunan Mahasiswa Teknologi Sains Data). JANGAN sebut nama orang/penerima.
  5. Tingkat: Wajib salah satu dari: ["Internasional", "Nasional", "Universitas", "Fakultas", "Departemen/Program Studi", "Lainnya"].
     - BEM Fakultas (FEB/FKM/FTMM) -> Fakultas.
     - HIMA / Himpunan Mahasiswa Departemen -> Departemen/Program Studi.
     - UKM / Ormawa universitas -> Lainnya.
     - Rektorat / BEM Universitas -> Universitas.
     - Lomba/seminar bertingkat nasional -> Nasional.
     - Konferensi/event global -> Internasional.
  6. Peran (raw_role): Peserta, Panitia, Juara, Pembicara, atau Pengurus.
  ```
- **Response Schema JSON**:
  - `nama_kegiatan_sertifikasi` (string, null bila tidak ada)
  - `nomor_bukti_fisik_nomor_sertifikasi` (string, null bila tidak ada)
  - `penyelenggara_kegiatan` (string, null bila tidak ada)
  - `waktu_mulai_pelaksanaan` (string "DD/MM/YYYY", null bila tidak ada)
  - `waktu_selesai_pelaksanaan` (string "DD/MM/YYYY", null bila tidak ada)
  - `tingkat` (string enum, null bila tidak ada)
  - `raw_role` (string, null bila tidak ada)
- **Generation Config & Determinisme**:
  - `temperature: 0.0` (wajib untuk ekstraksi data deterministik & reproduktif).
  - `responseMimeType: "application/json"` (menjamin output JSON murni dari endpoint API).
- **Post-Extraction Defensive Normalizer**:
  - Standardisasi tanggal ke `DD/MM/YYYY` (mengonversi ISO YYYY-MM-DD, nama bulan, dsb. agar kompatibel penuh dengan Matcher v2).
  - Truncation/strip whitespace ekstra.
- **Koneksi ke Form Mapper Produksi & Injeksi full_text Mandatori**:
  - **Injeksi full_text (MANDATORI)**: Sebelum memanggil `map_fields_to_form()`, adapter `gemini_field_extractor.py` wajib menginjeksi teks mentah Tesseract OCR secara eksplisit ke dalam dictionary ekstraksi:
    `extracted["full_text"] = ExtractedValue(value=raw_ocr_text, confidence=1.0, source="tesseract_raw")`
    Hal ini krusial agar fungsi `map_kelompok_dan_jenis()`, `map_tingkat_v8()`, dan `map_jenis_penyelenggara()` pada `form_mapper.py` dapat bekerja dengan benar tanpa menghasilkan silent error atau default `"Kegiatan Lainnya"` / `"--"`.
  - **Konversi Nilai**: Output JSON dikonversi ke `dict[str, ExtractedValue]` dengan confidence score terkalibrasi dari respons LLM (0.90 jika non-null, 0.0 jika null).
  - **Pemanggilan Form Mapper**: Diproses oleh `app.services.form_mapper.map_fields_to_form(extracted, tahun_akademik="2024/2025", bukti_fisik="Sertifikat")`.
### 3. Engine Benchmark & Evaluasi Komparatif (`tests/benchmark_gemini_tesseract.py`)
- **Dataset Input**: Korpus Tesseract-Primary terbaik saat ini:
  - Path: `tests/benchmark_runs/ocr_experiment/tesseract_primary_v4/extracted_texts/` (74 teks sertifikat: 49 scan + 25 embedded).
  - Ground Truth: `Ground_Truth_Sertifikat_v9.csv` (evaluator Matcher v2 frozen di `tests/matchers.py`).
- **Model yang Diuji (3 Model Sekaligus)**:
  1. `gemini-2.5-flash`
  2. `gemini-2.5-flash-lite`
  3. `gemini-3.1-flash-lite`
- **Pencatatan Artefak per Model**:
  - `run_results.json`: metadata konfigurasi, prompt lengkap, raw output LLM per sertifikat, token breakdown, biaya USD/IDR, latensi, dan hasil evaluasi per field (exact, fuzzy, wer, cer).
  - `per_cert_results.csv`: tabel baris per sertifikat (74 baris) memuat nama file, prediksi vs GT per 6 field, token in/out/cache, total cost (USD & IDR), dan latensi.
  - `summary.csv`: agregasi metrik per model (MACRO exact, MACRO fuzzy, per-field exact/fuzzy, total tokens, total USD, total IDR, avg tokens/cert, avg cost/cert).
  - `report.md`: laporan teknis Markdown per run.

### 4. Empat Lapis Pembuktian Empiris (`tests/validate_gemini_4layer.py`)
Sesuai standar wajib AGENTS.md untuk model pemenang / komparasi (dijalankan efisien tanpa pemborosan panggilan API):
- **Lapis 1 (Validasi Statistik - 0 Ekstra API Calls)**:
  - 5-Fold Stratified Cross Validation pada hasil ekstraksi 74 sertifikat dari model pemenang: ukur kestabilan fold, standard deviation, dan min-fold accuracy/precision.
  - Bootstrap Resampling 1000x: hitung 95% Confidence Interval untuk MACRO exact dan per-field accuracy.
- **Lapis 2 (Uji Ketahanan OOD - Pacing & Sample Kontrol)**:
  - Entity Mutation Probe: Uji kemampuan LLM mengekstrak tanggal, nomor, dan kegiatan saat nama instansi/organisasi dimutasi (UNAIR -> UNS, FTMM -> FST). Penurunan akurasi field non-organisasi dibatasi <= 2.0pt.
  - OCR Noise Perturbation: Uji ketahanan terhadap karakter noise OCR (10%, 25%, 50% substitusi leksikal OCR nyata: `5<->S`, `8<->B`, `0<->O`).
  - Opsi: dijalankan pada subset terstratifikasi 15 sertifikat (default) atau 74 sertifikat penuh via `--full`.
- **Lapis 3 (Audit Anchor Semantik Struktural - 0 Ekstra API Calls)**:
  - Audit leksikal independen pada prompt & system instruction: verifikasi bahwa prompt tidak mengandung keyword event hardcoded / de-corpusing audit.
- **Lapis 4 (Safety Net & Calibrated Confidence - 0 Ekstra API Calls)**:
  - Evaluasi mekanisme `needs_review` pada hasil ekstraksi LLM 74 sertifikat (field kosong, confidence < 0.85, atau format tanggal invalid memicu flag review).
  - Target recall review >= 95% pada sertifikat dengan kesalahan prediksi.
### 5. Pelaporan & Sinkronisasi Ledger (`docs/report/`)
- Menghasilkan laporan gabungan: `docs/report/gemini_tesseract_benchmark_report.md`.
- Menghasilkan sheet perbandingan CSV: `docs/report/gemini_models_comparison.csv`.
- Menghasilkan ringkasan konfigurasi dan prompt: `docs/report/gemini_prompt_and_config_registry.md`.
- Memperbarui `docs/experiments_ledger.md` (entri resmi `EXP-LLM-002: Direct Tesseract-to-Gemini 3-Model Extraction`).
- Menjalankan `scripts/generate_runs_summary.py` untuk memperbarui `docs/report/runs_summary.md` dan `docs/report/runs_summary.csv`.

---

## Critical Files & Anchors

1. `tests/gemini_client.py` (New): Client REST API Gemini, token parser (`usageMetadata`), dan kalkulator tarif USD/IDR (kurs 17.758).
2. `tests/gemini_field_extractor.py` (New): System instruction, response schema JSON, validator tanggal/tingkat, dan adapter ke `ExtractedValue` / `form_mapper.py`.
3. `tests/benchmark_gemini_tesseract.py` (New): Harness benchmark komparasi 3 model pada korpus Tesseract 74 sertifikat vs GT v9.
4. `tests/validate_gemini_4layer.py` (New): Runner 4 lapis pembuktian empiris (5-fold CV, Bootstrap CI, OOD mutation, noise injection, safety net review).
5. `tests/test_gemini_pipeline.py` (New): Unit test untuk payload formatting, schema parsing, token accounting, error recovery, dan matcher validation (zero-regression).

---

## Verification

1. **Unit Test Suite Proof**:
   ```bash
   uv run pytest tests/test_gemini_pipeline.py -v
   uv run pytest tests/ -q
   ```
   *Expected*: Seluruh test passing (144 existing + unit test baru), 0 failures.

2. **Smoke Test Kontrol API (Limit 3 Sertifikat per Model)**:
   ```bash
   uv run python -m tests.benchmark_gemini_tesseract --limit 3 --model gemini-2.5-flash
   uv run python -m tests.benchmark_gemini_tesseract --limit 3 --model gemini-2.5-flash-lite
   uv run python -m tests.benchmark_gemini_tesseract --limit 3 --model gemini-3.1-flash-lite
   ```
   *Expected*: Respon JSON valid, token count tercatat di log/JSON, biaya USD/IDR terhitung, output fields mapped ke form options.

3. **Full Benchmark 74 Sertifikat (Semua 3 Model)**:
   ```bash
   uv run python -m tests.benchmark_gemini_tesseract --all-models
   ```
   *Expected*:
   - Menghasilkan 3 direktori run di `tests/benchmark_runs/ocr_experiment/`
   - Tiap run memiliki `run_results.json`, `per_cert_results.csv`, `summary.csv`, dan `report.md`
   - Total token in/out/cache terhitung lengkap dengan angka USD dan IDR (kurs 17.758)

4. **4-Layer Empirical Proof Runner**:
   ```bash
   uv run python -m tests.validate_gemini_4layer --model gemini-2.5-flash
   ```
   *Expected*: Menghasilkan tabel 5-Fold CV, Bootstrap 95% CI, kurva degradasi noise OOD, dan recall safety net `needs_review` >= 95%.

5. **Laporan Konsolidasi & Update Ledger**:
   ```bash
   uv run python scripts/generate_runs_summary.py
   rtk git status --short
   ```
   *Expected*: `docs/report/runs_summary.md` mencatat ketiga varian model, ledger diperbarui, tidak ada perubahan pada file produksi `backend/app/`.

---

## Assumptions & Contingencies

- **Ketersediaan API Key**: Menggunakan `GOOGLE_API_KEY` yang sudah tersimpan di file `.env.google`. Jika key tidak ditemukan, runner berhenti dengan pesan instruksi yang jelas.
- **Rate Limit (HTTP 429)**: Jika akun pengguna terkena limit RPM (misalnya pada Free Tier / Tier 1), runner secara otomatis menerapkan delay antar panggilan (1.5 detik per request) dan exponential retry hingga 3 kali.
- **Status Staging Terisolasi**: Seluruh implementasi tetap berada di `tests/` dan tidak mengubah kode produksi `backend/app/` sebelum ada persetujuan eksplisit promosi produksi dari pengguna.
- **Fallback Kurs**: Kurs 1 USD = Rp17.758,00 per 2 Agustus 2026 dijadikan konstanta patokan utama. Jika pengguna ingin mengubah kurs di masa depan, konstanta `EXCHANGE_RATE_IDR_PER_USD` dapat di-override melalui env var `EXCHANGE_RATE_IDR_PER_USD`.
