# Certificate Autofill Prototype

Prototype internal — ekstraksi PDF sertifikat mahasiswa + autofill form Kartu Hasil Prestasi.

> **Adaptif.** Struktur dan konvensi di sini mencerminkan keadaan sekarang. Dapat berubah sesuai arahan tim.

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
PDF → PyMuPDF (fast text) → Docling (fallback) → OCR (RapidOCR+Tesseract)
    → Field Extractor (regex) → Form Mapper (rules) → PostgreSQL
```

### 3 Processing Modes
| Mode | Mekanisme | Worker |
|------|-----------|--------|
| `background` | FastAPI BackgroundTasks | Tidak perlu |
| `sync` | Langsung dalam HTTP request | Tidak perlu |
| `db_worker` | Worker polling PostgreSQL | `python -m app.worker` |

### Stack
- **Backend:** FastAPI + SQLAlchemy + PyMuPDF + Docling + RapidOCR + Tesseract
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
      docling_parser.py       # Docling converter wrapper
      ocr_fallback.py         # RapidOCR + Tesseract merger
      field_extractor.py      # Regex extraction: dates, role, activity, organizer, cert number
      form_mapper.py          # Rule-based mapping ke form options + needs_review logic
      job_processor.py        # DB read → pipeline → DB write
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
  evaluation_framework.py     # Exact/fuzzy/WER/CER evaluation
  ner_extractor.py            # NER model loading + inference
  ner_to_fields.py            # NER entities → form field mapping
  post_processors.py          # Entity scoring, signer detection, person filter
  matchers.py                 # Abbreviation matching, string utilities
  generate_bio_labels.py      # BIO label generation
  fine_tune_ner.py            # NER fine-tuning (reference)
  verify_ground_truth.py      # Ground truth verification
  date_normalizer.py          # Date normalization helpers
  llm_extractor.py            # LLM inference via Ollama
  llm_extractor_v2.py         # LLM inference v2 (full-text approach)
  test_field_extractor.py     # Unit test: field extractor
  test_generalized_parser.py  # Unit test: generalized parser
  test_evaluation_framework.py # Unit test: evaluation framework
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

---

## Testing & Benchmark

```bash
# Semua unit test
pytest tests/ -v

# Benchmark per pipeline komponen
uv run python -m tests.benchmark_pipeline      # Regex baseline
uv run python -m tests.benchmark_ner            # NER benchmark
uv run python -m tests.benchmark_hybrid         # Hybrid + post-processing
uv run python -m tests.benchmark_llm            # Hybrid + LLM (Ollama)
```

### Hasil Benchmark (74 sertifikat)

| Method | MACRO exact | MACRO fuzzy | LLM calls | Catatan |
|--------|:--------:|:---------:|:----------:|--------|
| Regex baseline | 42.2% | — | 0 | v2 |
| Hybrid + post-processing | 48.1% | 66.1% | 0 | v3 |
| Hybrid + LLM (A2 v2 full-text) | 58.3% | 74.5% | 74 | v4 |
| v7 P4 e_hybrid + router | 54.2% | — | 39 | tingkat 77.0% |
| **v8 f_bias + router (current)** | **55.2%** | — | **35** | **tingkat 82.4%**, 214 eff tok/cert |

> **Angka otoritatif:** [docs/handoff_v9.md](docs/handoff_v9.md) + `docs/report/report_data.json`. Tabel di atas ringkasan; detail per-variant di `docs/report/`.

### Ollama Setup
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

Yang mungkin berubah ke depannya:
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
- Docling bergantung pada model yang di-download saat runtime — slow first call
- Form mapper punya 2 fungsi validasi: `validate_with_needs_review` (required fields) dan `field_needs_review` (per-field threshold confidence < 0.80)
- `has_student_association_signature_context()` mendeteksi dari pola *signer dekat dengan nama organisasi*, bukan dari lokasi fisik tanda tangan
- Ollama perlu CUDA library path untuk RTX 5050 — lihat `scripts/start_ollama.sh`
- `pyproject.toml` punya dependencies untuk NER/fine-tuning (torch, transformers, seqeval, peft, datasets) yang tidak dipakai di pipeline utama

---

## Dokumen Referensi
- **Status eksperimen terbaru:** [docs/handoff_v9.md](docs/handoff_v9.md) — v8 executed (router fix, f_bias winner, layout rejected, production integration)
- **Laporan eksperimen:** [docs/report/README.md](docs/report/README.md) — benchmark_methods, evaluation_methodology, phase_v4_methodology, phase_v4_results_summary (`.docx` + mirror `.md`)
- **Improvement tracking:** [docs/improvements.md](docs/improvements.md) — checklist perbaikan teridentifikasi
- **Paper keywords:** [docs/paper_keywords.md](docs/paper_keywords.md) — keyword pencarian paper per topik
- **Literature review:** [docs/paper_findings.md](docs/paper_findings.md) — 363 papers, 57 queries, 9 groups
