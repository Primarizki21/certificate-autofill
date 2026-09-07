# Handoff v52 — Ephemeral Zero-PDF Storage

> Supersedes `docs/handoff_v51.md`.

## Ringkasan Eksekutif

PDF sertifikat sekarang hanya berada sementara di filesystem `UPLOAD_TEMP_DIR`.
PostgreSQL menyimpan metadata dokumen, status job, dan field hasil ekstraksi.
Tidak ada bytes PDF, raw OCR, preview, deduplikasi upload, atau pemulihan `localStorage` pada implementasi ini.

## Cutover Database Lama

Model SQLAlchemy saja tidak mengubah database PostgreSQL yang sudah ada.
Script `scripts/migrate_ephemeral_storage.py` wajib dijalankan satu kali sebelum deploy ke database lama.

1. Buat backup yang sudah diuji pemulihannya.
2. Jalankan dry-run:
   ```bash
   uv run python scripts/migrate_ephemeral_storage.py
   ```
3. Hentikan seluruh instance FastAPI dan `db_worker`; pastikan tidak ada job lama yang masih berjalan.
4. Jalankan migrasi:
   ```bash
   uv run python scripts/migrate_ephemeral_storage.py --apply --confirm-delete-legacy-storage --confirm-maintenance-window
   ```

Migrasi menambah `documents.parser_engine` dan empat kolom antrean: `temp_file_key`, `available_at`, `lease_expires_at`, `worker_id`.
Setelah itu migrasi menghapus permanen `document_files` dan `parsed_documents`; keduanya berisi PDF atau OCR mentah lama.

## Siklus Hidup Job

1. Upload memvalidasi magic bytes PDF lalu menulis file UUID dengan mode `0o600`.
2. Transaksi database menyimpan `temp_file_key` dan job `queued`.
3. Processor mengunci dan mengubah satu job menjadi `processing`, menyimpan worker ID serta lease.
4. Hanya pemilik lease aktif yang dapat menulis hasil atau menandai kegagalan.
5. Status terminal menghapus PDF pada blok `finally`.
6. Crash atau lease kedaluwarsa direkonsiliasi: job valid dapat diantrikan ulang sampai `MAX_JOB_RETRIES`; job melewati TTL menjadi `failed` lalu file dihapus.

`reap_orphans()` berjalan saat startup FastAPI, berkala pada FastAPI, dan berkala pada `db_worker`.
Reaper menerima daftar `temp_file_key` job `queued` atau `processing`, sehingga file aktif tidak terhapus hanya karena umur file.

## File Perubahan

- `scripts/migrate_ephemeral_storage.py`: dry-run default; apply membutuhkan konfirmasi hapus data legacy.
- `backend/app/services/job_processor.py`: atomic claim, lease owner, recovery, cleanup.
- `backend/app/services/temporary_upload_store.py`: reaper dengan daftar file aktif terlindungi.
- `backend/app/main.py`: cleanup startup dan task periodik.
- `backend/app/worker.py`: cleanup periodik dan claim melalui processor.
- `backend/app/config.py`, `.env.example`, `.env.docker.example`: TTL, lease, dan interval cleanup.
- `tests/test_ephemeral_storage.py`, `tests/test_ephemeral_storage_recovery.py`: unlink terminal, cutover schema, lease lintas worker, cleanup crash, dan task startup.

## Bukti Saat Ini

- `uv run pytest tests/test_ephemeral_storage.py tests/test_ephemeral_storage_recovery.py -v`: `10 passed in 1.25s`.
- `uv run pytest tests/ -v`: `188 passed in 49.91s`; 4 warning deprecation FastAPI `on_event` sudah ada, tidak mengubah hasil test.
- Dry-run migrasi SQLite memaparkan kolom yang hilang tanpa perubahan database; test migrasi memakai schema legacy dan membuktikan kolom antrean ditambah serta tabel PDF/OCR lama dihapus.

## Konfigurasi Operasional

| Variabel | Default | Fungsi |
|---|---:|---|
| `UPLOAD_TEMP_DIR` | `/tmp/cert_uploads` | Lokasi PDF sementara |
| `TEMP_FILE_TTL_HOURS` | `1` | TTL file tanpa job aktif |
| `JOB_LEASE_SECONDS` | `900` | Masa kepemilikan job |
| `STORAGE_CLEANUP_INTERVAL_SECONDS` | `300` | Jeda cleanup |
| `MAX_JOB_RETRIES` | `3` | Batas requeue lease kedaluwarsa |

## Open Frontier

- Operator menjalankan migrasi destructive setelah backup terverifikasi.
- Deploy worker atau FastAPI baru hanya setelah migrasi sukses.
