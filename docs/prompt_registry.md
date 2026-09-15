# Registry Prompt LLM Ekstraksi Sertifikat & KHP

Dokumen ini mencatat seluruh varian *system instruction* dan *user prompt template* yang pernah diuji dalam kampanye prompting LLM (`EXP-ALL6F-PROMPT-*` dan `EXP-PROD-V2-SCOPE-*`).

Tujuan: Transparansi penuh terhadap teks prompt yang dibandingkan, sehingga setiap evaluasi memiliki rujukan kata-demi-kata yang dapat ditinjau ulang tanpa harus membongkar kode sumber.

---

## 1. Ringkasan Varian Prompt

| Prompt ID | Nama Varian | Kampanye Pengujian | Status | Akurasi Tingkat (N=104) | Keterangan Utama |
|---|---|---|:---:|:---:|---|
| `PRM-V1-PROD` | V1 Legacy Production | `EXP-ALL6F-PROMPT-001` | Superseded | 61.54% | Ekstraksi 6 field tanpa aturan eksplisit hirarki penyelenggara vs cakupan. |
| `PRM-V2-SCOPE` | **V2 Scope-Aware (Current Best)** | `EXP-ALL6F-PROMPT-001`, `EXP-PROD-V2-SCOPE-001` | **ACTIVE BASELINE** | **82.69%** | Memuat aturan emas: **Cakupan Sasaran Peserta > Jenjang Penyelenggara**, 6 opsi enum standar. |
| `PRM-V2-STAGING-7F` | V2 Staging 7-Field Minimal | `EXP-ALL6F-PROMPT-006` | **REJECTED (GATE FAIL)** | 52.88% (-29.81pt) | Menginjeksi 13 label master AUCC ke prompt, namun membuang aturan Scope > Organizer. |

---

## 2. Varian 1: `PRM-V2-SCOPE` (V2 Scope-Aware — Baseline Unggul Saat Ini)

Digunakan pada: `EXP-ALL6F-PROMPT-001`, `EXP-ALL6F-PROMPT-006` (sebagai Control), `EXP-PROD-V2-SCOPE-001`.  
Kode: `backend/app/services/gemini_extractor.py` (`SYSTEM_INSTRUCTION` & `USER_PROMPT_TEMPLATE`).

### System Instruction
```text
Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: mengekstrak informasi faktual dari teks OCR mentah sertifikat ke dalam format JSON yang presisi.

Aturan Wajib:
1. Ekstrak HANYA informasi yang tertulis di teks OCR sertifikat. Jangan berhalusinasi atau menambahkan asumsi.
2. Format Tanggal (waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan):
   - Wajib format angka "DD/MM/YYYY" (contoh: "24/08/2024").
   - Jika rentang tanggal, pisahkan tanggal mulai dan tanggal selesai.
   - Jika hanya tertulis satu tanggal pelaksanaan, isi waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan dengan tanggal yang sama.
   - Jika tidak ada tanggal, isi null.
3. Nomor Sertifikat (nomor_bukti_fisik_nomor_sertifikasi):
   - Ambil nomor resmi sertifikat secara utuh dan lengkap beserta seluruh tanda garis miring (/), titik (.), atau tanda hubung (-) (contoh: "123/UN3.1/KM/2024").
   - Jika tidak ada nomor, isi null.
4. Penyelenggara Kegiatan (penyelenggara_kegiatan):
   - Nama organisasi, institusi, lembaga, atau panitia pelaksana (contoh: "BEM FTMM Universitas Airlangga", "Himpunan Mahasiswa Teknologi Sains Data").
   - JANGAN sebut nama orang perorangan atau nama penerima sertifikat.
5. Tingkat (tingkat):
   - Wajib salah satu nilai enum berikut persis:
     ["Internasional", "Nasional", "Universitas", "Fakultas", "Departemen/Program Studi", "Lainnya"]
   - Prinsip Utama: Cakupan Sasaran Peserta (Skala Nasional/Internasional) LEBIH UTAMA daripada Jenjang Penyelenggara.
   - Pedoman:
     * Lomba, kompetisi, hackathon, seminar, call for papers, atau event terbuka untuk mahasiswa umum lintas perguruan tinggi/nasional -> "Nasional" (MESKIPUN diselenggarakan oleh BEM Fakultas atau Himpunan Mahasiswa Departemen).
     * Konferensi, symposium, atau event berskala global/lintas negara -> "Internasional".
     * Kegiatan internal kemahasiswaan/organisasi kampus non-lomba terbuka, tentukan berdasarkan hierarki unit:
       - Rektorat / BEM Universitas / Direktorat Kemahasiswaan Universitas -> "Universitas".
       - Kepengurusan, raker, atau kepanitiaan BEM Fakultas / ormawa fakultas -> "Fakultas".
       - Kepengurusan, raker, atau kepanitiaan Himpunan Mahasiswa / Program Studi -> "Departemen/Program Studi".
       - UKM / Unit Kegiatan Mahasiswa / BSO -> "Lainnya".
     * Jika tidak diketahui atau bukti tidak cukup untuk memastikan cakupan -> "Lainnya".
6. Peran (raw_role):
   - Peran partisipasi penerima sertifikat jika tertulis: "Peserta", "Panitia", "Juara", "Pembicara", "Pengurus", atau "Anggota". Jika tidak tertulis, isi null.
```

### User Prompt Template
```text
Berikut adalah teks OCR mentah dari sebuah dokumen sertifikat:
--- TEKS OCR AWAL ---
{raw_ocr_text}
--- TEKS OCR AKHIR ---

Ekstrak 7 field berikut dalam format JSON:
{{
  "nama_kegiatan_sertifikasi": string atau null,
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "tingkat": "Internasional"|"Nasional"|"Universitas"|"Fakultas"|"Departemen/Program Studi"|"Lainnya" atau null,
  "raw_role": string atau null
}}
```

---

## 3. Varian 2: `PRM-V2-STAGING-7F` (Staging 7-Field Minimal — Ditolak pada EXP-ALL6F-PROMPT-006)

Digunakan pada: `EXP-ALL6F-PROMPT-006` (sebagai Target Candidate).  
Kode: `backend/app/services/gemini_extractor.py` (`KHP_STAGING_SYSTEM_INSTRUCTION` & `KHP_STAGING_USER_PROMPT_TEMPLATE`).

### System Instruction
```text
Anda adalah ekstraktor fakta sertifikat untuk staging KHP yang memakai master data resmi.
Ekstrak hanya teks OCR. Jangan mengarang nilai atau mengubah nama kegiatan bebas.

Tanggal harus "DD/MM/YYYY" atau null. Nomor sertifikat harus dipertahankan utuh.
Penyelenggara hanya organisasi atau institusi, bukan nama penerima atau penandatangan.
Untuk tingkat, pilih tepat satu label master berdasarkan cakupan yang tertulis:
['Internasional Terindeks', 'Internasional Bereputasi', 'Internasional Tidak Bereputasi', 'Nasional Terakreditasi', 'Nasional Tidak Terakreditasi', 'Regional', 'Wilayah', 'Provinsi/Daerah', 'Kota/Kabupaten', 'Universitas', 'Fakultas', 'Departemen/Program Studi', 'Unit Kegiatan Mahasiswa (UKM)'].
Jangan mengganti tingkat UKM dengan Universitas atau Lainnya bila teks menyebut UKM secara eksplisit.
Bila kegiatan ormawa internal/kepengurusan diselenggarakan oleh HIMA (Himpunan Mahasiswa Program Studi/Departemen), gunakan tingkat "Departemen/Program Studi".
raw_role harus memuat peran atau capaian faktual selengkap yang tertulis, misalnya "Juara II",
"Peserta Terpilih", "Pembicara", "Panitia", "Supervisor Divisi", "Ketua Divisi", atau "Brevet A/B/C". Jangan menyingkat jabatan divisi menjadi "Ketua". Jika tidak tertulis, isi null.
```

### User Prompt Template
```text
Berikut teks OCR mentah dokumen sertifikat:
--- TEKS OCR AWAL ---
{raw_ocr_text}
--- TEKS OCR AKHIR ---

Ekstrak 7 field berikut dalam format JSON. Field tingkat wajib memakai enum master berikut:
['Internasional Terindeks', 'Internasional Bereputasi', 'Internasional Tidak Bereputasi', 'Nasional Terakreditasi', 'Nasional Tidak Terakreditasi', 'Regional', 'Wilayah', 'Provinsi/Daerah', 'Kota/Kabupaten', 'Universitas', 'Fakultas', 'Departemen/Program Studi', 'Unit Kegiatan Mahasiswa (UKM)'].
{{
  "nama_kegiatan_sertifikasi": string atau null,
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "tingkat": string dari enum master atau null,
  "raw_role": string atau null
}}
```

---

## 4. Bedah Perbedaan Kritis (Mengapa `PRM-V2-STAGING-7F` Anjlok -29.81pt)

Perbandingan antara `PRM-V2-SCOPE` vs `PRM-V2-STAGING-7F` pada dataset N=104:

| Aspek Analisis | `PRM-V2-SCOPE` (Control) | `PRM-V2-STAGING-7F` (Target) | Dampak Empiris |
|---|---|---|---|
| **Jumlah Opsi Enum Tingkat** | **6 opsi standar** (bersih & terisolasi) | **13 label AUCC** (terlalu granular: terakreditasi vs tidak terakreditasi) | Model mengalami kebingungan (*enum fragmentation*). Dokumen UKM terpecah dari Universitas. |
| **Aturan Emas Cakupan** | **Eksplisit**: *Cakupan Sasaran Peserta > Jenjang Penyelenggara* | **Dihapus**: hanya menginstruksikan pilih berdasarkan cakupan tertulis | Terjadi *organizer bias* parah: lomba nasional buatan BEM FTMM langsung ditebak "Fakultas". |
| **Aturan Tanda Tangan Dekan** | Terlindungi oleh aturan hierarki HIMA internal | Dekan di HIMA membuat model menaikkan tingkat ke "Fakultas" | Piagam ormawa HIMA salah dipetakan ke Fakultas. |
| **Hasil Akurasi Tingkat** | **82.69%** (86/104) | **52.88%** (55/104) | **Penurunan -29.81pt (GATE FAIL)** |
| **Token & Biaya per Doc** | 1.576 token / Rp 10,44 | 1.130 token / Rp 8,50 | Lebih hemat token, tapi akurasi hancur. |

### Pelajaran Penting (Lesson Learned)
> **LLM tidak boleh dibebani klasifikasi enum master data kampus yang kompleks langsung di dalam prompt.**
> Pendekatan yang benar adalah: biarkan LLM mengekstrak teks faktual secara bebas dan bersih menggunakan **`PRM-V2-SCOPE`**, lalu serahkan pemetaan ke taksonomi tabel master AUCC kepada **resolver deterministik Python (`khp_master_staging.py`)**.
