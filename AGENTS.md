# Certificate Autofill Prototype

Prototype internal — ekstraksi PDF sertifikat mahasiswa + autofill form Kartu Hasil Prestasi.

> **Adaptif.** Struktur dan konvensi di sini mencerminkan keadaan sekarang. Dapat berubah sesuai arahan tim.

## Gaya Komunikasi dengan User

- **Bahasa mudah + contoh konkret** — hindari jargon abstrak; kalau harus istilah
  teknis, beri contoh kasus nyata (mis. "organizer seperti `Himasada` vs GT
  `Himasada, Fakultas Ilmu Komputer`").
- **Ringkas** — jawaban pendek dulu, detail hanya kalau diminta.
- Jawaban dalam Bahasa Indonesia (istilah teknis boleh Inggris).

---

## Quick Start

### Docker (full stack)
```bash
docker compose up --build
```
- FastAPI: `http://localhost:8000`
- PostgreSQL: `localhost:5434`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (`admin:admin`)

### Manual — Linux / macOS
```bash
export APP_ENV=development
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
export PROCESSING_MODE=background
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
PostgreSQL 17 harus aktif di port 5434, database `certautofill` sudah dibuat.

### Manual — Windows (PowerShell)
```powershell
$env:APP_ENV="development"
$env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
$env:PROCESSING_MODE="background"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
PostgreSQL 17 harus aktif di port 5434, database `certautofill` sudah dibuat.

### Frontend standalone
Buka `frontend/index.html` langsung di browser, atau:
```bash
cd frontend && python -m http.server 5173
```

---

## Architecture

### Pipeline
```
PDF → PyMuPDF (fast text) → OCR (RapidOCR+Tesseract)
    → Field Extractor (regex) → Form Mapper (rules) → PostgreSQL
```

### 3 Processing Modes
| Mode | Mekanisme | Worker |
|------|-----------|--------|
| `background` | FastAPI BackgroundTasks | Tidak perlu |
| `sync` | Langsung dalam HTTP request | Tidak perlu |
| `db_worker` | Worker polling PostgreSQL | `python -m app.worker` |

### Stack
- **Backend:** FastAPI + SQLAlchemy + PyMuPDF + RapidOCR + Tesseract
- **Frontend:** Vanilla HTML/CSS/JS (no framework, no build step)
- **DB:** PostgreSQL 17 (PDF disimpan sebagai `BYTEA`)
- **Monitoring:** Prometheus + Grafana + Loki
- **No message broker.** RabbitMQ sudah dihapus dari varian ini.

---

## Project Structure

```
backend/
  app/
    main.py                   # FastAPI entry, endpoints
    config.py                 # Frozen dataclass Settings dari env
    database.py               # SQLAlchemy engine + session + init_db
    models.py                 # Document, DocumentFile, ExtractionJob, ParsedDocument, ExtractedField
    schemas.py                # Pydantic: UploadResponse, ExtractionResult, FieldResult, OptionsResponse
    master_data.py            # FORM_OPTIONS + keyword lists (PTN, PTS, BUMN, dll)
    queue.py                  # Stub — RabbitMQ dihapus, error message saja
    worker.py                 # Optional DB-polling worker
    services/
      extraction_pipeline.py  # Orchestrator pipeline (yang manage urutan parser)
      pdf_fast_path.py        # PyMuPDF text + PNG render
      ocr_fallback.py         # RapidOCR + Tesseract merger
      field_extractor.py      # Regex extraction: dates, role, activity, organizer, cert number
      form_mapper.py          # Rule-based mapping ke form options + needs_review logic
      job_processor.py        # DB read → pipeline → DB write
      combined_extractor.py   # Combined v4.x staging bundle (apply_combined_v4_2)
      high_dpi_crop.py        # High-DPI region crop module (6.0× zoom)
      activity_extractor.py   # Activity extraction (AKT-005)
      organizer_normalize.py  # Organizer normalization v3 (ORG-003/004/006)
      tingkat_router.py       # Tingkat router rules (ROUTER-005/006, 63/74 routed @100%)
      llm_tingkat.py          # LLM fallback untuk tingkat (26 cert unrouted)
    static/                   # Frontend copy (juga served sebagai static files)
frontend/
  index.html                  # Form input KHP
  styles.css                  # Styling
  app.js                      # Client-side logic (polling, autofill)
tests/
  benchmark_pipeline.py       # Regex baseline benchmark
  benchmark_ner.py            # NER benchmark
  benchmark_hybrid.py         # Hybrid + post-processing benchmark
  benchmark_llm.py            # Hybrid + LLM benchmark
  benchmark_combined_v4_2.py  # Combined v4.2 benchmark (v4.0 vs v4.1 vs v4.2 comparison)
  evaluation_framework.py     # Exact/fuzzy/WER/CER evaluation
  ner_extractor.py            # NER model loading + inference
  ner_to_fields.py            # NER entities → form field mapping
  post_processors.py          # Entity scoring, signer detection, person filter
  matchers.py                 # Matcher v2: frozen evaluator (abbreviation, fuzzy, WER/CER)
  generate_bio_labels.py      # BIO label generation
  fine_tune_ner.py            # NER fine-tuning (reference)
  verify_ground_truth.py      # Ground truth verification
  date_normalizer.py          # Date normalization helpers
  llm_extractor.py            # LLM inference via Ollama
  llm_extractor_v2.py         # LLM inference v2 (full-text approach)
  test_field_extractor.py     # Unit test: field extractor
  test_generalized_parser.py  # Unit test: generalized parser
  test_evaluation_framework.py # Unit test: evaluation framework
  test_combined_v4_2.py       # Unit test: Combined v4.2 (94 tests)
  conftest.py                 # Pytest fixtures
  bio_labels/                 # Test fixtures (75 JSON)
monitoring/
  prometheus.yml
  loki-config.yml
```

---

## Key Patterns

### ExtractedValue
Dataclass core yang dipakai semua service layer:
```python
@dataclass
class ExtractedValue:
    value: str | None
    confidence: float
    source: str
```
Segala output parsing dan mapping selalu dalam bentuk `ExtractedValue`.

### Rule Priority di Form Mapper
Rules di `form_mapper.py` punya urutan prioritas ketat. Jangan diacak. Contoh:
- `PKKMB` di-cek sebelum `panitia`
- `Panitia` di-cek sebelum `pengurus organisasi`
- Seminar/workshop dengan status peserta tidak boleh jadi "Pengurus Organisasi"
- `DIREKTUR KEMAHASISWAAN` di-cek sebelum aturan HIMA
- HIMA signature mapping butuh konteks Airlangga eksplisit

### OCR Date Fallback
OCR tidak hanya dipanggil saat teks kosong. Pipeline mengekstrak field *sementara* dulu, lalu memaksa OCR tambahan jika field tanggal belum ditemukan. Ini bukan hardcode — OCR tetap baca isi PDF.

### Month OCR Aliases
`field_extractor.py` punya daftar alias untuk kesalahan OCR umum: `AGUSTU5` → `AGUSTUS`, `SEPTEM8ER` → `SEPTEMBER`, dll.

### Combined v4.x Pipeline
Pipeline staging yang menggabungkan seluruh improvement offline (0 LLM):
- Flag gating: `settings.enable_combined_v4_2` (default: `False`, zero blast radius)
- `combined_extractor.py`: orchestrator v4.x → `apply_combined_v4_2()`
- 3 OOD pillars: semantic grammar anchors, universal Roman numeral repairs, calibrated confidence
- `high_dpi_crop.py`: re-render region nomor dari PDF pada zoom 6.0× (300+ DPI)
- Tingkat: 63/74 routed via rules (router), 11 residual → LLM fallback
- MACRO exact 76.82% (all-cells) / 87.42% (framework), 0 LLM calls, 100% offline

### Matcher v2 (Frozen Evaluation)
`tests/matchers.py` = **frozen baseline evaluator** (jangan diubah tanpa persetujuan eksplisit).
- Field-specific matching: dates (normalize_date), nomor (strip punctuation), organizer (abbreviation detection)
- `is_initialism_of`: deteksi akronim (`UNAIR` ↔ `Universitas Airlangga`) dengan known expansions
- `is_portmanteau_of`: deteksi portmanteau terdaftar (BEM, HIMA, FTMM, dll)
- Threshold organizer: fuzzy ≥0.75 (dinaikkan dari 0.5 karena false positive BEM FEB vs BEM FKM)
- WER/CER untuk metrik edit distance

---

## Session Context & Experiment Workflow

### Context loading (WAJIB di awal sesi, urut)
1. `git status` + `git log --oneline -5` — posisi & file untracked.
2. Baca handoff TERBARU (`docs/handoff_v*.md`, versi angka tertinggi — parse
   `int` setelah "v", jangan sort lexicographic) — plan + open frontier.
3. Baca `docs/report/runs_summary.md` — angka terukur semua run.
4. Baca `docs/experiments_ledger.md` — closed/failed approaches (JANGAN dilewatkan).
5. Kunci baseline dari runs_summary:
   - **Baseline evaluasi** (frozen): `Ground_Truth_Sertifikat_v9.csv` + matcher v2 (`tests/matchers.py`)
   - **Current best pipeline**: Combined v4.2 (`combined_extractor.py`, flag `ENABLE_COMBINED_V4_2`)
   - `Ground_Truth_Sertifikat_v8.csv` tetap frozen sebagai acuan historis; raw
     `Ground_Truth_Sertifikat.csv` = history, JANGAN diubah. Run benchmark baru
     WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`.
6. Kode: `codegraph_explore` on-demand (bukan baca semua file).
7. **Handoff maintenance** — setiap akhir eksperimen atau milestone:
   - Cek apakah perlu buat handoff baru (opsi B: per 5-10 ledger entries).
   - Handoff baru WAJIB: ringkasan eksekutif, tabel komparasi, file yang diubah,
     4 lapis pembuktian, open frontier, supersession note.

### Loop eksperimen (per eksperimen)
- **B0 DEDUP:** cek `experiments_ledger.md` — hipotesis pernah dicoba? Skip jika
  closed kecuali re-try condition terpenuhi.
- **B1 Pilih metode + tulis GATE** (target angka vs baseline) & sebutkan goal
  yang dilayani (efisien/robust/cepat/hemat-token/scalable).
- **B2 `codegraph_explore`** target → pahami blast radius SEBELUM edit.
- **B3 Edit kode eksperimen** di `tests/` — produksi tidak disentuh tanpa persetujuan.
- **B4 `codegraph_explore` ulang** → verifikasi index menangkap edit (auto-sync ~1s).
- **B5 Jalankan trial** (berat/OCR = probe terkontrol / user-run — WSL 8GB).
- **B6 GATE CHECK** vs baseline (akurasi no-regress + target token/call).
- **B7 `pytest tests/`** setelah perubahan kode.
- **B8 Audit diff** (blast radius, tidak ada perubahan produksi).
- **B9 LEDGER:** tambah entri PASS/FAIL (hipotesis, hasil, verdict, re-try condition).
- **B10 PASS →** `report_data.json` + `generate_report.py` + `generate_runs_summary.py` + update handoff. FAIL → regenerate runs_summary (biar terlihat).
- **B11 COMMIT MANDATORI (OTOMATIS TANPA DIMINTA):**
  - Agent **WAJIB langsung melakukan git commit** atas kode + docs terkait segera setelah verifikasi selesai (tests pass & gate check lolos).
  - **DILARANG MENUNGGU USER MENYURUH COMMIT.** Commit adalah penutup wajib di setiap akhir eksperimen atau perubahan.
  - Gunakan pesan commit terstruktur & deskriptif (Conventional Commits: `feat:`, `test:`, `docs:`, dll).
  - Hanya `git push` yang diserahkan kepada user (karena kebutuhan SSH passphrase).
- Rollback: trial FAIL = kode eksperimen boleh tetap, tercatat di ledger, jangan dipakai produksi.

> Gagal trial = pengetahuan (bukan dead end). Ledger mempersempit ruang pencarian
> sehingga sesi berikutnya tidak mengulang pendekatan yang sudah ditutup.

---

## Handoff Maintenance

Handoff (`docs/handoff_v*.md`) = narasi kohesif eksperimen. Ledger = catatan atomik; handoff = konteks lengkap.

### Kapan buat handoff baru
- Setelah 5-10 ledger entries tercatat (opsi B: per batch eksperimen).
- Setelah milestone besar (misal: Combined v4.0 → v4.1 → v4.2).
- Ketika open frontier berubah signifikan.
- **Agent WAJIB buat handoff baru bahkan tanpa user minta** bila gap konteks sudah terlalu jauh.

### Isi handoff WAJIB
1. Ringkasan eksekutif hasil eksperimen
2. Tabel komparasi vs versi sebelumnya
3. File yang diubah/dibuat
4. 4 lapis pembuktian empiris (jika ada perubahan pipeline)
5. Open frontier (next steps)
6. Supersession note: "Supersedes `docs/handoff_vXX.md`"

---

## Production Promotion

Pipeline staging (flag `ENABLE_COMBINED_V4_2` dll) boleh di-promote ke production **HANYA setelah user SETUJU**.

### Flow
1. **QA/QC pipeline** — jalankan semua test (pytest, benchmark, OOD stress), audit diff, verifikasi blast radius.
2. **User review hasil QA** — presentasikan hasil ke user.
3. **User SETUJU** — eksplisit, bukan asumsi.
4. **Production promotion** — toggle flag `=True` atau replace default di production code.
5. **Smoke test** — verifikasi pipeline berjalan di production.
6. **Commit** — Conventional Commits format.

**DILARANG promote tanpa persetujuan eksplisit user.**

---

## Emergency Rollback

Kalau pipeline production regress atau bug masuk ke live:
- **Solusi utama:** `git revert` ke commit sebelumnya (aman karena semua sudah di-commit).
- **Rollback trial:** kode eksperimen boleh tetap, tercatat di ledger, jangan dipakai produksi.
- **Rollback full:** restore dari pre-commit state via git history.

> Semua perubahan WAJIB di-commit agar versioning tersimpan dan rollback bisa dilakukan kapan saja.

---

## Testing & Benchmark

### Protokol Evaluasi & 4 Lapis Pembuktian Empiris WAJIB (Generalisasi & Robustness)

Setiap perubahan pipeline, penambahan rule router, ekstraktor regex, atau normalizer **WAJIB mematuhi 4 lapis pembuktian empiris** berikut untuk menjamin generalisasi di luar 74 sertifikat dataset:

1. **Lapis 1: Validasi Statistik ($k$-Fold Cross-Validation & Bootstrap CI)**:
   - Uji stratified 5-fold CV (`tests/stat_validation.py`, `tests/router_mining_v5.py`).
   - Rule router baru WAJIB mencapai **Min-Fold Precision 100.0%** (0 false positive di holdout fold uji yang tidak melihat data latih).
   - Rule dengan frekuensi firing $< 5$ (LOW-N) harus dilaporkan secara eksplisit dan tidak boleh diklaim robust tanpa guard ordering yang ketat.
   - Metrik makro wajib diverifikasi dengan Bootstrap Confidence Interval 1000x resampling.

2. **Lapis 2: Uji Ketahanan Out-of-Distribution (OOD Stress Testing)**:
   - **Template & Entity Mutation**: Uji mutasi entitas institusi/kegiatan (`tests/ood_probe.py`: UNAIR $\to$ UNS, FTMM $\to$ FST, nama event diganti generik). Penurunan akurasi pada field bebas-institusi (tanggal, kegiatan, peranan) dibatasi $\le 2.0\text{pt}$.
   - **OCR Noise Injection**: Uji perturbasi kebingungan karakter nyata (`5↔S`, `8↔B`, `0↔O`, `1↔I`, spasi runtuh) pada tingkat $10\%$, $25\%$, $50\%$ untuk menguji daya tahan normalizer.

3. **Lapis 3: Ekstraksi Berbasis Structural Semantic Anchors (Anti-Hardcoding)**:
   - Regex WAJIB memanfaatkan relasi sintaksis dan pola tata bahasa sertifikat formal (misal: `sebagai [Role] pada [Kegiatan] yang diselenggarakan oleh [Penyelenggara]`, `in the event entitled "..."`, `held on [Date]`), BUKAN mencocokkan judul event spesifik secara hardcoded.
   - Format tanggal dan nomor harus mengikuti format baku penanggalan (ID/EN) dan penomoran surat resmi (`[Kode]/[Unit]/[Bulan Romawi]/[Tahun]`).

4. **Lapis 4: Arsitektur Safety Net Produksi & Calibrated Confidence (`needs_review`)**:
   - Zero silent error: Semua nilai wajib dibungkus `ExtractedValue(value, confidence, source)`.
   - Sertifikat dengan confidence $< 0.85$, unrouted/ambiguous, atau missing field otomatis memicu `needs_review = True` (target recall review $\ge 95\%$) agar diverifikasi oleh pengguna di antarmuka form.

5. **STANDAR WAJIB PELAPORAN DOKUMEN (.docx / .md / .xlsx)**:
   - **Setiap laporan `.docx` yang diminta user** (seperti `docs/pipeline_best.docx` atau laporan di `docs/report/`) **WAJIB menyertakan bab khusus "Empirical Robustness & Generalization Proof"** yang mencantumkan:
     - Tabel 5-Fold Cross Validation (per-fold precision & routed certs).
     - Tabel OOD Stress Test (mutasi institusi & kurva noise OCR).
     - Rincian Anchor Semantik Struktural (anti-hardcoding).
     - Matriks Kalibrasi Review & Safety Net (Recall review, Precision review, Confusion Matrix).
   - **Dilarang keras** hanya menyajikan tabel progression linier tanpa bukti ketahanan empiris yang dapat diverifikasi.
   - **STANDAR LAPORAN TEKNIKAL EVALUASI PIPELINE / OCR (DOCX + XLSX)**:
     Saat pengguna meminta laporan teknikal (*technical report*) untuk evaluasi pipeline atau eksperimen OCR, agen **WAJIB** mengikuti alur dan standar deliverable berikut:
     1. **Gaya Bahasa**: *Simplified Indonesian* (ringkas, bahasa mudah dipahami, contoh konkret, tanpa jargon berbelit, istilah teknis tetap presisi).
     2. **Deliverable Dokumen DOCX (`docs/report/*.docx`)**:
        - **Bab 1: Ringkasan Eksekutif & Garis Evolusi Pipeline**: Mencakup garis evolusi dari baseline awal (misal v4.x yang masih memakai RapidOCR + Tesseract), transisi ke arsitektur primer/hybrid, hingga versi pure/final.
        - **Bab 2: Arsitektur Pipeline, Konfigurasi & Alur Lengkap**: Parameter rendering (zoom 3.0× / 300 DPI), konfigurasi OCR (multi-PSM Tesseract `""`, `--psm 6`, `--psm 11`, kamus bahasa `ind+eng`), dan urutan modul post-processing v4.x deterministik.
        - **Bab 3: Tabel Komparasi Metrik Lengkap**: Tabel 4-arah yang membandingkan (1) Baseline legacy awal (v9), (2) Pipeline v4.x terbaik eksisting sebelum Tesseract (berbasis teks produksi RapidOCR+Tesseract / Composite B8), (3) Tesseract-Primary Hybrid (49 scan via Tesseract + 25 digital via layer asli), dan (4) Pure 100% Tesseract (74/74 seluruhnya dibaca murni via OCR gambar raster).
        - **Bab 4: Contoh Konkret Raw OCR vs Hasil Field Pipeline**: Wajib menyertakan minimal 5 contoh nyata yang menampilkan **LENGKAP SELURUH 6 FIELD** (Nama Kegiatan, Nomor Sertifikat, Penyelenggara, Tanggal Mulai, Tanggal Selesai, Tingkat — dilarang hanya menampilkan sebagian field), mencakup teks mentah OCR lengkap (full raw OCR text), nilai bersih pipeline, Ground Truth, dan status kecocokan.
        - **Bab 5: Empirical Robustness & Generalization Proof**: Wajib menyertakan 4 lapis pembuktian empiris lengkap (5-Fold CV min-fold 100%, OOD stress test mutasi & noise, semantic anchors anti-hardcoding, calibrated confidence safety net).
        - **Bab 6: Kesimpulan & Rekomendasi Deployment**.
     3. **Deliverable Dokumen XLSX (`docs/report/*.xlsx`)**:
        - Berisi data lengkap seluruh 74 sertifikat dataset.
        - Kolom wajib: No, Stem File, Tipe Dokumen (Scan/Digital), Teks Raw OCR Lengkap, Prediksi per Field, Ground Truth per Field, Status Match per Field (EXACT/FUZZY/MISMATCH dengan styling warna hijau/kuning/merah), dan Total Exact per baris.

6. **Aturan Regression & Baseline Evaluasi**:
   - Setiap perubahan ekstraktor/router $\to$ `pytest tests/` (seluruh test passing) + zero-regression vs baseline GT v9 + matcher v2 (`GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`).
   - Matcher v2 + GT v9 = baseline evaluasi frozen, jangan diubah tanpa persetujuan eksplisit.
```bash
# Semua unit test
pytest tests/ -v

# Benchmark per pipeline komponen
uv run python -m tests.benchmark_pipeline          # Regex baseline
uv run python -m tests.benchmark_ner               # NER benchmark
uv run python -m tests.benchmark_hybrid            # Hybrid + post-processing
uv run python -m tests.benchmark_llm               # Hybrid + LLM (Ollama)
uv run python -m tests.benchmark_combined_v4_2     # Combined v4.2 (v4.0 vs v4.1 vs v4.2)
```

### Hasil Benchmark (74 sertifikat)

| Method | MACRO exact | MACRO fuzzy | LLM calls | Catatan |
|--------|:--------:|:---------:|:----------:|--------|
| Regex baseline | 42.2% | — | 0 | v2 |
| Hybrid + post-processing | 48.1% | 66.1% | 0 | v3 |
| v9 organizer_v2 + router | 60.2% | 74.2% | 29 | tingkat 83.8%, 176 eff tok/cert |
| Combined v2 | 74.2% | 80.7% | 0 | 0 LLM, offline |
| Combined v3 | 85.7% | 88.3% | 0 | 0 LLM, offline |
| **Combined v4.2 (current)** | **76.82%** (all-cells) / **87.42%** (framework) | **78.64%** / **90.00%** | **0** | 3 OOD pillars, High-DPI crop |

> **Angka otoritatif:** handoff terbaru (`docs/handoff_v44.md`) + `docs/report/runs_summary.md` + `docs/experiments_ledger.md`. Tabel di atas ringkasan; detail per-variant di `docs/report/`.
>
> **OCR:** eksperimen OCR sebelumnya CLOSED (nomor gagal, ledger OCR-001..012). Semua engine non-LFM gagal pada field nomor. LFM2.5-VL-3B = satu-satunya yang tidak regress nomor (28.6% = baseline), tapi latency 77s/cert tidak viable untuk produksi.

### Ollama Setup
LLM sekarang hanya sebagai **fallback untuk tingkat** (26 cert unrouted, ~1.5s/cert):
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
```

---

## Conventions

### Code Style
- Python: snake_case, type hints di setiap fungsi, dataclasses untuk value objects
- Komentar dan UI labels: **Bahasa Indonesia**
- Import: stdlib → third-party → local, tanpa blank line antar grup
- Frontend: no framework, no build step, pure vanilla (HTML/CSS/JS)

### Config
- Semua env var dibaca di `config.py` → `Settings` frozen dataclass → global `settings`
- Default values untuk development di `.env.example` dan file `.env`

### Database
- PDF disimpan langsung sebagai `BYTEA` di `document_files.pdf_data`
- Tidak ada migration tool — `Base.metadata.create_all()` di `init_db()`
- Schema: `Document` - `DocumentFile` (1:1), `Document` - `ExtractionJob` (1:N), `Document` - `ExtractedField` (1:N)


### Keamanan & Proteksi Rahasia (Zero Secret Leakage — WAJIB)
Aspek keamanan kredensial dan API key adalah **prioritas absolut dan dilarang keras dilanggar dalam kondisi apa pun**:
- **DILARANG KERAS MEMASUKKAN KUNCI API ASLI KE GIT / REPO**:
  * File `.env` dan `.env.google` yang memuat nilai rahasia asli WAJIB terdaftar di `.gitignore` dan **DILARANG SEKALI PUN DI-STAGE ATAU DI-COMMIT**.
  * Sebelum melakukan commit (`git commit`), agent WAJIB memastikan file yang di-stage (`git diff --staged`) **TIDAK memuat token/kunci API privat**.
  * Pada file template (`.env.example`, `.env.docker.example`) atau dokumentasi (`README.md`), hanya gunakan placeholder kosong (`GOOGLE_API_KEY=`) atau dummy generik (`GOOGLE_API_KEY="AIzaSy..."`).
- **DILARANG MEMBOCORKAN KUNCI KE CHAT ATAU LOG**:
  * Agent dilarang keras menampilkan isi kunci API asli (`GOOGLE_API_KEY`) ke respons chat pengguna, artefak publik, atau commit message.
  * Semua modul pemanggil external API (`gemini_extractor.py`, `gemini_client.py`) WAJIB menyamarkan/meredaksi kunci (`[REDACTED_API_KEY]`) sehingga pesan error atau exception logger tidak mencatat key ke log file maupun terminal.
- **OTENTIKASI VIA PRIVATE HTTP HEADERS**:
  * Pengiriman kunci API ke Google Cloud API WAJIB melalui private HTTP header `x-goog-api-key`, BUKAN query parameter URL (`?key=...`), agar kunci tidak tercatat di URL log proxy/server.
- **VERIFIKASI KEAMANAN MANDATORI**:
  * Jika pengguna meminta audit keamanan atau sebelum `git push`, pastikan verifikasi dengan:
    `git log -E -G"AIza[0-9A-Za-z_-]{35}" --all` menghasilkan **0 temuan**.
---

## Perubahan yang Ada & yang Mungkin Datang

Yang sudah berubah:
- V4: DATE FIX — pipeline memeriksa field tanggal sebelum menentukan perlu OCR
- V5: DATE FORCE OCR — OCR dipaksa saat field tanggal masih kosong
- V6: GENERALIZED PARSER — parser reusable, tidak hardcode satu format
- V7: HIMA TINGKAT — aturan HIMA/Student Association menentukan Tingkat
- V8: HIMA AIRLANGGA ONLY — HIMA mapping butuh konteks Airlangga eksplisit
- Phase v3 (Hybrid+PP): NER + regex + post-processing — 48.1% exact
- Phase v4 (LLM): Hybrid + Ollama llama3.2 — 58.3% exact, ~2.5s/cert
- Combined v2: offline bundle (0 LLM) — 74.2% exact
- Combined v3: 5 branches (ROUTER-006 + DATE-001 + ORG-006 + ACT-006 + NUM-003) — 85.7% exact
- Combined v4.2: 3 OOD pillars + High-DPI crop — 76.82% all-cells / 87.42% framework

- Option A: Direct Tesseract-to-Gemini extraction (EXP-LLM-002 / PROD-GEMINI-001/002) aktif di produksi (`ENABLE_TESSERACT_GEMINI=true`) dengan graceful fallback
Yang mungkin berubah ke depannya:
- Promosi Combined v4.2 ke production (perlu user approval)
- Resume eksperimen OCR (DocTR sebagai kandidat)
- Resume KB (knowledge base) untuk hemat LLM calls di skala besar
- Skema database (migration tool mungkin ditambahkan)
- Cakupan testing
- Processing mode tambahan
- Aturan mapping baru sesuai kebutuhan form
- Penambahan linter/formatter

---

## Gotchas

- `pika` masih ada di `requirements.txt` tapi sudah tidak dipakai (RabbitMQ dihapus)
- `pytesseract` perlu Tesseract terinstall di sistem — tidak otomatis dari pip
- `rapidocr-onnxruntime` perlu download model on first run
- Form mapper punya 2 fungsi validasi: `validate_with_needs_review` (required fields) dan `field_needs_review` (per-field threshold confidence < 0.80)
- `has_student_association_signature_context()` mendeteksi dari pola *signer dekat dengan nama organisasi*, bukan dari lokasi fisik tanda tangan
- Ollama perlu CUDA library path untuk RTX 5050 — lihat `scripts/start_ollama.sh`
- `pyproject.toml` punya dependencies untuk NER/fine-tuning (torch, transformers, seqeval, peft, datasets) yang tidak dipakai di pipeline utama
- Combined v4.2 flag default `False` — harus diaktifkan manual via `ENABLE_COMBINED_V4_2=true` di `.env`

---

## Dokumen Referensi
- **Status eksperimen terbaru:** handoff TERBARU (`docs/handoff_v48.md` — Encoder NER vs LLM vs Rules) + `docs/experiments_ledger.md` (closed approaches)
- **Laporan eksperimen:** [docs/report/README.md](docs/report/README.md) — benchmark_methods, evaluation_methodology, phase_v4_methodology, phase_v4_results_summary (`.docx` + mirror `.md`)
- **Laporan resmi (docx/xlsx):** `docs/report/report_data.json` = source of truth (`experiments[]` + `per_field_src` per eksperimen + blocks dokumen) → `scripts/generate_report.py` → docx/md + `results_comparison.xlsx` (7 sheet, termasuk "Per-Field by Experiment" — per-field per eksperimen, OCR "n/a"). xlsx TIDAK di-commit (`*.xlsx` di-ignore) — regenerate lokal.
- **Improvement tracking:** [docs/improvements.md](docs/improvements.md) — checklist perbaikan teridentifikasi
- **Paper keywords:** [docs/paper_keywords.md](docs/paper_keywords.md) — keyword pencarian paper per topik
- **Literature review:** [docs/paper_findings.md](docs/paper_findings.md) — 363 papers, 57 queries, 9 groups
