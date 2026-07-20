# Changelog Rules V2

Perubahan berdasarkan revisi Airnology:

1. `Jenis Penyelenggara` tidak lagi otomatis menjadi `BUMN` hanya karena terdapat sponsor/logo/teks perusahaan.
2. Prioritas mapping `Jenis Penyelenggara` diperketat:
   - Jika `Tingkat` = `Fakultas`, `Departemen/Program Studi`, atau `UKM`, maka `Jenis Penyelenggara` otomatis `PTN di Indonesia`.
   - Jika `Tingkat` = `Internasional`, maka `Jenis Penyelenggara` otomatis `PT di luar negeri`.
   - Keyword PTN/PTS diprioritaskan sebelum keyword BUMN.
   - Keyword BUMN pendek seperti BRI/BNI/PLN/KAI sekarang memakai word boundary agar tidak false positive dari potongan kata OCR.
3. Parser tanggal diperkuat untuk interval dengan satu tahun:
   - `24 Agustus - 22 September 2024` -> `24/08/2024` dan `22/09/2024`.
   - `18 - 27 Agustus 2022` -> `18/08/2022` dan `27/08/2022`.
   - Jika hanya ada satu tanggal, tanggal tersebut masuk ke mulai dan selesai.
4. Tambahan normalisasi OCR untuk nama bulan, misalnya `AGUSTU5`, `SEPTEM8ER`, dan variasi sejenis.
5. Limit upload PDF dinaikkan dari 1 MB menjadi 10 MB di backend, env, README, dan hint frontend.
6. Frontend diberi strict rule tambahan: jika user mengubah `Tingkat` secara manual, `Jenis Penyelenggara` ikut menyesuaikan sesuai aturan di atas.

Validasi:

```bash
PYTHONPATH=backend python -m pytest -q
# 2 passed
```
