# Handoff v47 — Promosi Produksi: Direct Tesseract-to-Gemini Extraction (Option A)

> Supersedes `docs/handoff_v46.md`. Sesi ini mengimplementasikan **Option A (Direct Pipeline Replacement)**
> ke dalam backend produksi `backend/app/` berdasarkan persetujuan eksplisit pengguna.
> Pipeline dilengkapi dengan sakelar fitur (*feature toggle*) `ENABLE_TESSERACT_GEMINI` (default `true` per arahan user),
> jaring pengaman *graceful fallback* (anti error 500), serta verifikasi smoke test live end-to-end tanpa menyalakan Docker.

---

## 1. Ringkasan Eksekutif & Keputusan Pengguna

- **Keputusan Arsitektur**: Pengguna memilih **Option A (Direct Replacement)** dibandingkan Option B (Hybrid). Pertimbangan utamanya adalah menghindari risiko *overfitting* dari router lokal saat sistem berhadapan dengan variasi sertifikat riil di luar korpus 74, serta memprioritaskan kemampuan generalisasi semantik LLM murni (`gemini-3.1-flash-lite`).
- **Konfigurasi Default**: `ENABLE_TESSERACT_GEMINI=true` di `.env` dan `config.py` sehingga pengguna dapat langsung menguji alur kerja end-to-end.
- **Zero 500 Error Guarantee**: Jika kuota Google API habis (HTTP 429), server Google mengalami gangguan (HTTP 503), atau koneksi internet terputus, sistem secara otomatis melakukan *graceful fallback* ke pipeline offline existing (Combined v4.2 / regex) tanpa melempar exception atau HTTP 500.

---

## 2. Rincian Implementasi & Perubahan Kode

### A. Konfigurasi (`backend/app/config.py`)
- Penambahan pemuatan otomatis `.env.google` (jika tersedia) agar `GOOGLE_API_KEY` terbaca secara aman.
- Penambahan field setting pada frozen dataclass `Settings`:
  ```python
  enable_tesseract_gemini: bool = os.getenv("ENABLE_TESSERACT_GEMINI", "true").lower() == "true"
  google_api_key: str | None = os.getenv("GOOGLE_API_KEY")
  google_gemini_model: str = os.getenv("GOOGLE_GEMINI_MODEL", "gemini-3.1-flash-lite")
  gemini_timeout_seconds: float = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "30.0"))
  ```

### B. Modul Service Produksi (`backend/app/services/gemini_extractor.py`)
- Modul mandiri standard library (`urllib.request`, `json`, `re`, `time`, `logging`).
- Mengirimkan kunci API melalui HTTP Header privat `x-goog-api-key` (bukan query string URL).
- Mengunci `generationConfig: {"temperature": 0.0, "responseMimeType": "application/json"}` untuk hasil deterministik.
- Menyediakan normalizer tanggal defensif (`standardize_date`) yang menjamin format `DD/MM/YYYY` untuk form KHP.
- Menginjeksi `extracted["full_text"] = ExtractedValue(raw_ocr_text, 1.0, "tesseract_raw")` agar form mapper KHP dapat menurunkan `kelompok_kegiatan`, `jenis_kegiatan`, dan `jenis_penyelenggara`.
- Mengembalikan `(None, {"error": ...})` saat terjadi error agar pemanggil dapat melakukan fallback tanpa crash.

### C. Alur Ekstraksi Produksi (`backend/app/services/extraction_pipeline.py`)
- Memeriksa flag `settings.enable_tesseract_gemini`:
  ```python
  if settings.enable_tesseract_gemini:
      from app.services.gemini_extractor import extract_fields_with_gemini
      gemini_extracted, meta = extract_fields_with_gemini(raw_text)
      if gemini_extracted is not None:
          extracted = gemini_extracted
          parser_engine = f"{parser_engine}+{meta.get('model', 'gemini')}"
          raw_json = meta
          mapped = map_fields_to_form(extracted, tahun_akademik=tahun_akademik, bukti_fisik=bukti_fisik)
          return PipelineResult(...)
      else:
          logger.warning("Gemini extraction failed; falling back to offline pipeline.")
  ```

### D. File Lingkungan (`.env` & `.env.example`)
- Ditambahkan parameter konfigurasi:
  ```bash
  ENABLE_TESSERACT_GEMINI=true
  GOOGLE_API_KEY=
  GOOGLE_GEMINI_MODEL=gemini-3.1-flash-lite
  GEMINI_TIMEOUT_SECONDS=30.0
  ```

---

## 3. Verifikasi & Pembuktian Pengujian

1. **Unit Test Suite**:
   - `tests/test_gemini_extractor_prod.py`: 6 unit test baru untuk memvalidasi penanganan missing key, normalisasi tanggal/tingkat, switch toggle OFF, graceful fallback, dan live smoke test.
   - Seluruh test suite proyek (`uv run pytest tests/ -q`): **163 passed, 0 failed**.
2. **Live Smoke Test pada File PDF Nyata**:
   - Menjalankan `run_extraction_pipeline` pada file PDF asli (`1952296_219642_skp.pdf`) dengan flag `ENABLE_TESSERACT_GEMINI=True`.
   - Hasil:
     * `parser_engine`: `pymupdf_fast_path+gemini-3.1-flash-lite`
     * Seluruh field form (`nama_kegiatan_sertifikasi`, `penyelenggara_kegiatan`, `tingkat`, `prestasi_partisipasi_jabatan`, `kelompok_kegiatan`, `jenis_kegiatan`) terisi secara lengkap tanpa error.
3. **Graceful Fallback Verification**:
   - Disimulasikan pemanggilan Gemini yang gagal (`Connection refused`).
   - Hasil: Pipeline otomatis mengalihkan proses ke pipeline offline existing tanpa error 500 dan berhasil memetakan form KHP secara utuh.
4. **Instruksi Docker**: Sesuai permintaan eksplisit pengguna, kontainer Docker **TIDAK dinyalakan**.

---

## 4. Cara Mengoperasikan di Produksi

- **Untuk Menggunakan Gemini (Default Sekarang)**:
  Pastikan `GOOGLE_API_KEY` terisi di `.env` atau `.env.google`. Pipeline otomatis memanggil `gemini-3.1-flash-lite`.
- **Untuk Mematikan Gemini (Kembali 100% Offline)**:
  Ubah baris di file `.env`:
  ```bash
  ENABLE_TESSERACT_GEMINI=false
  ```
  Restart server FastAPI / uvicorn. Sistem akan langsung beralih ke mode offline tanpa perlu perubahan kode.

---

## 5. Supersession Note

Supersedes `docs/handoff_v46.md`.
Status pipeline produksi saat ini: **Option A (Tesseract-to-Gemini) terpasang di backend, aktif secara default (`ENABLE_TESSERACT_GEMINI=true`) dengan proteksi graceful fallback offline**.
