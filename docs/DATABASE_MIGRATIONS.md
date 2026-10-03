# Panduan Database Migrations (Alembic)

Dokumentasi ini menjelaskan manajemen evolusi skema database PostgreSQL menggunakan **Alembic** pada project Certificate Autofill.

---

## 1. Konsep & Filosofi

Sebelumnya, inisialisasi skema menggunakan `Base.metadata.create_all()` di `backend/app/database.py`. Cara tersebut hanya bekerja ketika database masih kosong dan **tidak mampu mendeteksi penambahan atau perubahan kolom pada tabel yang sudah ada**.

Alembic bertindak sebagai *version control* untuk skema database (analog dengan migrasi `php artisan migrate` di Laravel atau `python manage.py migrate` di Django):
- Setiap perubahan skema dicatat ke dalam file Python berurutan di `backend/alembic/versions/`.
- PostgreSQL menyimpan riwayat versi pada tabel khusus `alembic_version`.
- Setiap migrasi memiliki fungsi `upgrade()` untuk menerapkan perubahan dan `downgrade()` untuk melakukan rollback.

---

## 2. Struktur Direktori

```
├── alembic.ini                   # Konfigurasi utama Alembic (root)
└── backend/
    └── alembic/
        ├── env.py                # Runner migrasi (terhubung ke Base.metadata & settings)
        ├── script.py.mako        # Template generator file migrasi
        └── versions/             # Direktori script migrasi tersimpan
            └── b1ffa32f19bf_initial_schema.py   # Baseline skema awal
```

---

## 3. Perintah Operasional

### A. Menerapkan Migrasi ke Database (Upgrade)
Untuk memperbarui skema database ke versi paling mutakhir:
```bash
# Melalui host lokal
uv run alembic upgrade head

# Melalui container Docker yang sedang berjalan
docker compose exec backend alembic upgrade head
```

### B. Membuat Script Migrasi Baru (Autogenerate)
Ketika Anda menambahkan kolom, tabel, atau indeks baru di `backend/app/models.py`:
1. Ubah class model di `backend/app/models.py`.
2. Jalankan autogenerate:
```bash
uv run alembic revision --autogenerate -m "tambah_kolom_feedback_di_extracted_fields"
```
3. Periksa file baru yang tercipta di `backend/alembic/versions/` untuk memastikan perubahan sesuai ekspektasi.

### C. Melakukan Rollback (Downgrade)
Jika perubahan skema perlu dibatalkan:
```bash
# Membatalkan 1 langkah ke belakang
uv run alembic downgrade -1

# Mengembalikan ke baseline awal
uv run alembic downgrade b1ffa32f19bf
```

### D. Memeriksa Riwayat & Status Migrasi
```bash
# Melihat versi migrasi yang sedang aktif di database
uv run alembic current

# Melihat seluruh riwayat migrasi yang tersedia
uv run alembic history --verbose
```

---

## 4. Opsi Override URL Database

Konfigurasi `backend/alembic/env.py` secara dinamis memprioritaskan database URL dengan urutan:
1. Argumen eksplisit `-x url=...` (sangat berguna untuk pengujian lokal/CI).
2. Environment variable `DATABASE_URL`.
3. Default `settings.database_url`.

**Contoh pengujian migrasi tanpa menyalakan PostgreSQL:**
```bash
uv run alembic -x url="sqlite:///test.db" upgrade head
```

---

## 5. Integrasi Deployment Produksi

Saat merilis versi baru ke server produksi:
1. Jalankan `docker compose pull` atau `docker compose build`.
2. Terapkan migrasi sebelum traffic masuk:
   ```bash
   docker compose run --rm backend alembic upgrade head
   ```
3. Restart backend & worker:
   ```bash
   docker compose up -d
   ```
