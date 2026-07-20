# V6 Generalized Parser

Perubahan utama:

1. Parser dibuat lebih general untuk sertifikat berbeda, bukan hardcode per file.
2. Mendukung tanggal Indonesia dan Inggris:
   - `24 Agustus - 22 September 2024`
   - `18 - 27 Agustus 2022`
   - `23 November 2024`
   - `September 21 to December 7, 2024`
   - `fromSeptember 21 to December7,2024`
3. Field kegiatan diperbaiki:
   - `as a committee` -> Panitia
   - `OF PARTICIPATION` / `partisipasinya` -> Peserta
   - `seminar Brief 2024` -> Brief 2024
   - `at SPECTA which held ...` -> SPECTA
   - `Talkshow Kakiwima ...` -> Talkshow Kakiwima
   - `PKKMB` -> Pengenalan Kehidupan Kampus bagi Mahasiswa Baru (PKKMB)
4. Mapping tidak lagi menjadikan sertifikat seminar dari HIMA/BEM sebagai Pengurus Organisasi jika role-nya peserta.
5. Jenis penyelenggara tetap dipaksa ke PTN Indonesia untuk tingkat Fakultas/Universitas/Departemen/UKM sesuai aturan form.
6. Frontend tetap tanpa debug panel.
7. Tidak menggunakan RabbitMQ.
8. Limit PDF tetap 10 MB.

Catatan:
- Keberhasilan ekstraksi tetap bergantung pada hasil teks dari PyMuPDF/Docling/OCR.
- Jika PDF berbasis gambar dan OCR tidak terpasang/hasil OCR buruk, field bisa kosong. Itu bukan hardcode, tetapi batasan pembacaan dokumen.
