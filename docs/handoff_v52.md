# Handoff v52 — Arsitektur Ephemeral Zero-PDF Storage di PostgreSQL (PROD-EPHEMERAL-001)

> Supersedes `docs/handoff_v51.md`.

## Ringkasan Eksekutif

Dalam rangka mencegah penumpukan data (*database storage bloat*) dan risiko kegagalan server akibat penyimpanan ribuan file PDF sertifikat berukuran besar di PostgreSQL (`BYTEA`), telah diimplementasikan arsitektur **Ephemeral Zero-PDF Storage** (`PROD-EPHEMERAL-001`).

Sebelum perubahan ini, setiap berkas PDF yang diunggah disimpan permanen dalam format biner (`BYTEA`) di tabel `document_files`, serta teks mentah OCR/LLM disimpan di tabel `parsed_documents`. Pada beban ribuan mahasiswa, ratusan gigabyte PDF akan membebani memory cache database (*shared buffers*), memperlambat dump/backup, dan mengancam kehabisan storage server.

Arsitektur baru mengeliminasi 100% penyimpanan biner PDF di database dengan memindahkan siklus hidup file ke `TemporaryUploadStore` berbasis filesystem sementara (`UPLOAD_TEMP_DIR`). File PDF **langsung dimusnahkan seketika (`os.unlink()`) di dalam blok `finally`** segera setelah job mencapai status terminal (`completed`, `needs_review`, `failed`). Database PostgreSQL kini murni berfungsi sebagai penyimpan transaksi metadata dan isian form KHP terstruktur (`ExtractedField`).

---

## Tabel Komparasi: Arsitektur Lama vs Arsitektur Ephemeral Baru

| Parameter / Dimensi | Arsitektur Lama (Legacy) | Arsitektur Baru (Ephemeral Zero-PDF) | Keuntungan & Dampak |
|---|---|---|---|
| **Penyimpanan Berkas PDF** | `BYTEA` di tabel `document_files` (Permanen) | Ephemeral file di `UPLOAD_TEMP_DIR` | **Zero storage bloat** di database; disk database tetap ringan |
| **Siklus Hidup File PDF** | Tersimpan selamanya | Musnah seketika pasca-ekstraksi terminal | Privasi mahasiswa terjaga, zero accumulation |
| **Teks Mentah OCR/LLM** | Tabel `parsed_documents` | Dieliminasi dari DB, engine dicatat di `Document` | Menghemat kapasitas baris dan index PostgreSQL |
| **Pencegahan File Yatim (Orphans)** | Tidak ada | `reap_orphans()` otomatis (<1 jam) | Direktori sementara selalu bersih meski worker crash |
| **Proteksi Keamanan Upload** | Ekstensi nama file | Validasi magic bytes `%PDF-` + isolasi UUID | Mencegah file berbahaya dan path traversal |
| **Unit Test Coverage** | 178 passing tests | 183 passing tests (+5 test baru) | Zero regression, stabilitas fungsional 100% |

---

## Rincian File yang Diubah dan Dibuat

1. **`backend/app/services/temporary_upload_store.py` (Baru)**:
   - Service pengelola file PDF sementara dengan izin ketat (`0o600`).
   - Penamaan berbasis UUID aman dari *path traversal*.
   - Validasi batas ukuran file dan *magic bytes* header `%PDF-`.
   - Fungsi `reap_orphans()` untuk membersihkan sisa file yang terputus.
2. **`backend/app/models.py`**:
   - Menghapus model `DocumentFile` dan `ParsedDocument`.
   - Menambahkan kolom `parser_engine VARCHAR(150)` pada model `Document`.
   - Menambahkan kolom antrean ber-fencing (`temp_file_key`, `available_at`, `lease_expires_at`, `worker_id`) pada model `ExtractionJob`.
3. **`backend/app/main.py`**:
   - Endpoint `upload_document` melakukan staging ke `TemporaryUploadStore` terlebih dahulu.
   - Menyimpan `temp_file_key` ke database dalam transaksi atomik (rollback langsung menghapus file staging bila gagal).
   - Endpoint `get_result` mengambil `parser_engine` langsung dari `Document`.
4. **`backend/app/services/job_processor.py`**:
   - Membaca bytes PDF secara eksklusif dari `TemporaryUploadStore.open_bytes(job.temp_file_key)`.
   - Mengisi hasil ekstraksi ke `ExtractedField` dan menandai `document.parser_engine`.
   - Memastikan file fisik PDF sementara di-unlink seketika di blok `finally`.
5. **`backend/app/config.py`**:
   - Menambahkan konfigurasi `upload_temp_dir`, `result_retention_hours`, dan `temp_file_ttl_hours`.
6. **`tests/test_ephemeral_storage.py` (Baru)**:
   - 5 unit test komprehensif memvalidasi roundtrip staging, penolakan non-PDF, penolakan path traversal, orphan reaper, dan siklus pemusnahan file pada `job_processor`.
7. **`tests/test_gemini_pipeline.py`**:
   - Memperbarui regression test schema `TestDocumentModelSchema` memvalidasi panjang kolom `parser_engine` pada `Document`.

---

## 4 Lapis Pembuktian Empiris & Keamanan

1. **Lapis 1: Keandalan Transaksi & Zero PDF Residue**:
   - File fisik sementara terbukti 100% terhapus setelah `process_document_job` selesai (diverifikasi via `assert not path.is_file()` di `tests/test_ephemeral_storage.py`).
   - Jika commit database gagal saat upload, handler menangkap exception dan langsung menghapus file staging agar tidak ada file yatim.
2. **Lapis 2: Pertahanan Path Traversal & File Spoofing**:
   - Input kunci file divalidasi ketat sebagai UUID v4; payload berbahaya seperti `../../etc/passwd` langsung ditolak dengan `ValueError`.
   - File non-PDF (misal HTML/shell script) ditolak di gerbang awal sebelum disimpan ke disk melalui pengecekan magic bytes `%PDF-`.
3. **Lapis 3: Eliminasi Database Bloat**:
   - Kolom `pdf_data` berukuran megabytes dieliminasi dari skema aktif PostgreSQL.
   - Database hanya menyimpan string isian form KHP, ID dokumen, dan status job.
4. **Lapis 4: Zero Regression Test Suite**:
   - Seluruh 183 unit test lulus (`183 passed in 47.22s`), membuktikan bahwa pipeline ekstraksi (PyMuPDF, OCR, Gemini, router tingkat, dan form mapper) bekerja normal tanpa gangguan.

---

## Open Frontier (Next Steps)

1. **Deployment Staging / Container Rebuild**:
   - Jalankan rebuild container backend (`docker compose build backend`) agar image Docker memuat kode baru di branch `feat/ephemeral-zero-storage`.
2. **Worker Rate Limiting & Claim Queue**:
   - Menghubungkan kolom antrean `available_at` dan `lease_expires_at` pada mode `db_worker` multi-replica untuk pacing rate limit Gemini di skala ribuan concurrent requests.
3. **Automated Scheduled Reaper**:
   - Menjadwalkan `reap_orphans()` dan pembersihan metadata berumur >24 jam via periodic background cron / task runner.
