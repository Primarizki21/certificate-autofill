# Improvement Tracking — Certificate Autofill

> Checklist perbaikan teridentifikasi dari review pipeline.
> Update status: `🔲 TODO` → `🔜 IN PROGRESS` → `✅ DONE`.
> Ref paper keywords: [paper_keywords.md](paper_keywords.md).

---

## A. LLM-Based Field Classification

### Latar Belakang

Pipeline saat ini sepenuhnya rule-based: `field_extractor.py` (regex) + `form_mapper.py` (keyword rules).
Arah pengembangan: hybrid rule-based + LLM untuk klasifikasi field, transisi ke ML tradisional untuk production scale.

### Arsitektur Hybrid yang Diusulkan

```
PDF → Text Extraction (PyMuPDF/OCR)
       ↓
    Raw Text (cleaned + filtered)
       ↓
    ┌──────────────────────────────────────────┐
    │  LLM Field Classifier (Tier 1)            │
    │                                            │
    │  System Prompt (Bahasa Indonesia):          │
    │  "Kamu adalah ekstraktor sertifikat.       │
    │   Ekstrak field dalam format JSON:         │
    │   - nama_kegiatan                          │
    │   - peran: panitia|peserta|ketua|...       │
    │   - tanggal_mulai (DD/MM/YYYY)             │
    │   - tanggal_selesai (DD/MM/YYYY)           │
    │   - penyelenggara                          │
    │   - nomor_sertifikat                       │
    │   Beri confidence 0.0-1.0 per field."      │
    │                                            │
    │  + 2-3 Few-shot examples                   │
    │  + Temperature = 0                         │
    │  + JSON mode / function calling             │
    └──────────────────────────────────────────┘
       ↓ gagal / confidence < threshold
    ┌──────────────────────────────────────────┐
    │  Regex Rule-Based (Tier 2, existing)       │
    │  field_extractor.py + form_mapper.py       │
    └──────────────────────────────────────────┘
       ↓
    ┌──────────────────────────────────────────┐
    │  Validasi + Rule Mapper (Tier 3)          │
    │  Cross-field validation + mapping ke       │
    │  form KHP (kelompok, jenis, tingkat, dll)  │
    └──────────────────────────────────────────┘
       ↓
    ExtractedField (confidence dihitung ulang)
```

### Strategi Model per Fase

| Fase | Model | Latensi (est.) | Biaya/dok | Kapan |
|------|-------|---------------|-----------|-------|
| 1. Prototype | GPT-4o-mini / Gemini Flash (API) | 1-2s | ~$0.0001 | Iterasi cepat, validasi approach |
| 2. Optimasi | Local LLM via Ollama/vLLM (Llama-3, Qwen-2.5) | 0.5-2s | $0 | Self-hosted, hilangkan biaya API |
| 3. Transisi ML | Fine-tuned DistilBERT / BERT-small per field | ~50ms | $0 | Classifier ringan, latency rendah |
| 4. Production | Ensemble classifier per field + rule fallback | ~20ms | $0 | Final, production scale |

### Resilience Pattern

```
LLM Call → Timeout (3x) → Circuit Breaker Open
                              ↓
                    Fallback ke Rule-Based
                              ↓
                    Flag document untuk retry
```

### Checklist — LLM Approach

- [ ] **A1 — LLM Classifier Prototype**
  *Implementasi Tier 1 LLM classifier untuk 6 field utama.*
  - Prioritas: **Tinggi**
  - Paper: Group A
  - Detail: Buat `llm_extractor.py` dengan prompt engineering + few-shot examples.
    Integrasikan ke `extraction_pipeline.py` sebagai optional tier.

- [ ] **A2 — LLM vs Rule Ensemble Decision**
  *Logika ensemble: kapan pakai hasil LLM vs rule.*
  - Prioritas: **Tinggi**
  - Paper: Group B
  - Detail: Aturan: kalau LLM confidence > rule confidence, pakai LLM.
    Kalau LLM gagal/tidak available, fallback ke rule.

- [ ] **A3 — Dataset Labeled dari Output LLM**
  *Kumpulkan hasil LLM yang sudah dikoreksi sebagai training data.*
  - Prioritas: **Menengah**
  - Paper: Group F
  - Detail: Simpan setiap hasil extraction + koreksi user (jika ada UI edit).
    Target: minimal 500 sample per field untuk fine-tuning.

- [ ] **A4 — Fine-tuned Classifier per Field**
  *Transisi dari LLM ke model kecil yang fine-tuned.*
  - Prioritas: **Menengah** (setelah A3 selesai)
  - Paper: Group G
  - Detail: Fine-tune DistilBERT/IndoBERT per field (role, activity, organizer).
    Evaluasi: precision/recall/F1 vs LLM baseline.

---

## B. Confidence & Evaluation

- [ ] **B1 — Confidence Calibration**
  *Ganti confidence hardcoded (0.86, 0.92) dengan confidence statistik.*
  - Prioritas: **Tinggi**
  - Paper: Group C
  - Detail: Confidence berbasis rule (berapa strategi setuju? seberapa spesifik match?).
    Kalau sudah ada labeled data: Platt scaling / isotonic regression.

- [ ] **B2 — Evaluation Dataset**
  *Buat labeled dataset untuk evaluasi objektif.*
  - Prioritas: **Tinggi**
  - Paper: Group E
  - Detail: Kumpulkan 100+ PDF + ground truth per field. Format: JSON dengan field → value.
    Simpan di `tests/fixtures/` atau database terpisah.

- [ ] **B3 — Metrics Dashboard**
  *Tampilkan metrik evaluasi per field.*
  - Prioritas: **Menengah**
  - Paper: Group E
  - Detail: Precision/Recall/F1 per field, confusion matrix untuk field kategorikal.
    Integrasi dengan Grafana.

- [ ] **B4 — Threshold Optimization**
  *Cari threshold optimal untuk needs_review (sekarang 0.80) dan min_text_length (80).*
  - Prioritas: **Menengah**
  - Paper: Group C
  - Detail: Eksperimen dengan labeled data, cari threshold yang minimalkan false negative (missed review).

---

## C. Extraction Robustness

- [ ] **C1 — Document Preprocessing**
  *Tambahkan preprocessing untuk meningkatkan kualitas OCR.*
  - Prioritas: **Tinggi**
  - Paper: Group D
  - Detail: Deskew, denoise, contrast enhancement, binarization.
    Integrasikan ke `ocr_fallback.py`.

- [ ] **C2 — Cross-Field Validation**
  *Validasi logis antar field.*
  - Prioritas: **Menengah**
  - Paper: —
  - Detail: `tanggal_mulai <= tanggal_selesai`, `role harus sesuai jenis_kegiatan`,
    `PKKMB tidak bisa jadi Pengurus Organisasi`. Flag `needs_review` kalau tidak konsisten.

- [ ] **C3 — Document Type Classification**
  *Klasifikasi tipe sertifikat sebelum extraction.*
  - Prioritas: **Rendah**
  - Paper: Group H
  - Detail: Klasifikasi: PKKMB, seminar/workshop, organisasi, lomba, lainnya.
    Extraction rules spesifik per tipe (contoh: PKKMB tidak perlu extract nomor sertifikat).

- [ ] **C4 — Deduplication Detection**
  *Deteksi sertifikat duplikat (mahasiswa upload sertifikat yang sama).*
  - Prioritas: **Rendah**
  - Paper: —
  - Detail: Gunakan `checksum_sha256` yang sudah ada, cek sebelum extraction.
    Return hasil extraction yang sudah ada kalau duplikat.

---

## D. Performance & Scale

- [ ] **D1 — Throughput Benchmark**
  *Benchmark throughput pipeline untuk estimasi capacity.*
  - Prioritas: **Tinggi**
  - Paper: Group I
  - Detail: Ukur latensi per tier (PyMuPDF, Docling, OCR, regex, mapper).
    Hitung throughput maksimal per worker. Dokumentasikan.

- [ ] **D2 — Result Caching**
  *Cache hasil extraction berdasarkan content hash.*
  - Prioritas: **Menengah**
  - Paper: Group I
  - Detail: Gunakan `checksum_sha256` yang sudah dihitung saat upload.
    Cache ke Redis/memory dict: `{sha256: ExtractionResult}`.

- [ ] **D3 — Batch Processing**
  *Optimasi untuk bulk upload (mahasiswa upload 10+ sertifikat).*
  - Prioritas: **Menengah**
  - Paper: Group I
  - Detail: Endpoint `POST /api/documents/batch` untuk upload banyak PDF.
    Background processing per batch.

- [ ] **D4 — Worker Pool Optimization**
  *Multiple worker untuk throughput tinggi.*
  - Prioritas: **Rendah**
  - Paper: Group I
  - Detail: Kalau pakai `db_worker` mode, jalankan N worker parallel.
    Gunakan `FOR UPDATE SKIP LOCKED` untuk job distribution.

---

## E. Observability

- [ ] **E1 — Structured Logging**
  *Tambah structured logging (JSON format).*
  - Prioritas: **Tinggi**
  - Paper: —
  - Detail: Log dengan field: `document_id`, `job_id`, `parser_engine`, `duration_ms`,
    `field_extracted_count`, `needs_review_count`. Format JSON → Loki parsing lebih baik.

- [ ] **E2 — Extraction Analytics**
  *Dashboard analytics untuk extraction pipeline.*
  - Prioritas: **Menengah**
  - Paper: —
  - Detail: Metrics: documents per hour, avg extraction time, needs_review rate per field,
    parser_engine distribution, OCR call rate, error rate.

- [ ] **E3 — Alerting**
  *Alert untuk anomali pipeline.*
  - Prioritas: **Rendah**
  - Paper: —
  - Detail: Grafana alert: error rate > 10%, needs_review rate spike, latency > 30s,
    OCR fallback rate increase.

---

## F. Keyword Data Management

- [ ] **F1 — Database-Backed Keyword Lists**
  *Pindahkan PTN/PTS/BUMN keyword ke database table.*
  - Prioritas: **Menengah**
  - Paper: —
  - Detail: Table `master_keywords` dengan kolom: `category`, `keyword`, `is_active`.
    API: `GET/POST/PUT/DELETE /api/keywords`. Tidak perlu deploy ulang untuk update keyword.

- [ ] **F2 — Fuzzy Matching**
  *Tambahkan fuzzy matching untuk keyword (toleransi OCR error).*
  - Prioritas: **Rendah**
  - Paper: —
  - Detail: `rapidfuzz` / `thefuzz` untuk match keyword dengan toleransi typo.
    Misal: "UNIVERSITAS AIRLANGGA" juga match "UNIVERSITAS AIRLANGCA" (OCR typo).

---

## G. Developer Experience

- [ ] **G1 — Debug Mode**
  *Aktifkan debug panel di frontend untuk development.*
  - Prioritas: **Menengah**
  - Paper: —
  - Detail: Toggle debug mode: tampilkan raw text, parser engine, confidence breakdown,
    intermediate extraction results. Development-only, tidak di production.

- [ ] **G2 — A/B Testing Framework**
  *Simpan extraction version untuk A/B testing.*
  - Prioritas: **Rendah**
  - Paper: Group E
  - Detail: Kolom `parser_version` di `parsed_documents`. Ekstraksi dengan 2 versi rules,
    bandingkan hasil. Metrics: field match rate, needs_review rate.

- [ ] **G3 — Test Coverage**
  *Tingkatkan test coverage dari 2 file test.*
  - Prioritas: **Menengah**
  - Paper: —
  - Detail: Unit test per extractor function. Integration test end-to-end dengan fixture PDF.
    Target: semua `extract_*` function punya minimal 1 test.
