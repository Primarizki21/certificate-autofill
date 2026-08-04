# Certificate Autofill Prototype

Prototype internal — ekstraksi PDF sertifikat mahasiswa dan autofill form Kartu Hasil Prestasi (KHP).

Stack: FastAPI + SQLAlchemy + PostgreSQL 17 + PyMuPDF + Docling + RapidOCR/Tesseract + Prometheus/Grafana/Loki. Docker Compose menyediakan full stack. Lihat [AGENTS.md](AGENTS.md) untuk arsitektur detail, konvensi, dan panduan tim.

---

## Cara Menjalankan

### Docker (full stack)
```bash
docker compose up --build
```
| Service | URL |
|---------|-----|
| FastAPI | `http://localhost:8000` |
| PostgreSQL | `localhost:5434` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` (admin:admin) |

### Manual — Linux / macOS
```bash
# Prasyarat: PostgreSQL 17 aktif di port 5434, database certautofill sudah dibuat
export APP_ENV=development
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
export PROCESSING_MODE=background
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Manual — Windows (PowerShell)
```powershell
# Prasyarat: PostgreSQL 17 aktif di port 5434, database certautofill sudah dibuat
$env:APP_ENV="development"
$env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
$env:PROCESSING_MODE="background"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Standalone
Buka `frontend/index.html` langsung di browser, atau:
```bash
cd frontend && python -m http.server 5173
```

---

## Processing Modes

| Mode | Mekanisme | Worker |
|------|-----------|--------|
| `background` | FastAPI BackgroundTasks | Tidak perlu |
| `sync` | Langsung dalam HTTP request | Tidak perlu |
| `db_worker` | Worker polling PostgreSQL | `python -m app.worker` |

Gunakan variabel `PROCESSING_MODE` di atas. Default: `background`.

---

## Testing

```bash
# Semua test
pytest tests/ -v

# Benchmark per pipeline komponen
uv run python -m tests.benchmark_pipeline      # Regex baseline
uv run python -m tests.benchmark_ner            # NER benchmark
uv run python -m tests.benchmark_hybrid         # Hybrid + post-processing
uv run python -m tests.benchmark_llm            # Hybrid + LLM (Ollama)
```

### Hasil Benchmark Saat Ini (74 sertifikat)

| Method | MACRO exact | MACRO fuzzy | Latency/cert |
|--------|:--------:|:---------:|:----------:|
| Regex baseline | 42.2% | — | ~0.1s |
| NER v1 only | 18.4% | — | ~0.07s |
| Hybrid + post-processing | 48.1% | 66.1% | ~0.6s |
| **Hybrid + LLM (A2 v2 full-text)** | **58.3%** | **74.5%** | **~2.5s** |

---

## LLM Inference (Ollama)

Gunakan LLM lokal untuk field yang tidak bisa diekstrak NER/regex (tingkat, kelompok_kegiatan, jenis_kegiatan):

```bash
# 1. Install & jalankan Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b

# 2. Jalankan benchmark LLM
uv run python -m tests.benchmark_llm
```

Detail implementasi di [docs/handoff_v5.md](docs/handoff_v5.md).

---

## Endpoint

```http
POST /api/documents              # Upload PDF → parsing
GET  /api/documents/{id}/result  # Hasil parsing
GET  /api/options                # Form dropdown options
GET  /metrics                    # Prometheus metrics
GET  /healthz                    # Health check
```

---

## Dokumen Terkait

| Dokumen | Isi |
|---------|-----|
| [AGENTS.md](AGENTS.md) | Arsitektur pipeline, konvensi coding, panduan kontribusi |
| [docs/handoff_v5.md](docs/handoff_v5.md) | Status eksperimen terbaru (Phase v4 — LLM) |
| [docs/improvements.md](docs/improvements.md) | Roadmap perbaikan teridentifikasi |
| [docs/paper_findings.md](docs/paper_findings.md) | Literature review (363 papers, 9 groups) |
| [docs/paper_keywords.md](docs/paper_keywords.md) | Keyword pencarian paper per topik |
