# V8 - HIMA/IM Rule Uses Explicit Airlangga Context Only

Perubahan:

- Aturan HIMA/Himpunan Mahasiswa/IM/Ikatan Mahasiswa pada konteks tanda tangan sekarang hanya memakai bukti eksplisit `Universitas Airlangga`, `UNAIR`, atau `Airlangga`.
- `FTMM`, `Fakultas Teknologi Maju dan Multidisiplin`, `Dekan FTMM`, dan `Dean of FTMM` tidak lagi dianggap cukup untuk rule khusus HIMA -> Departemen/Program Studi.
- Jika ada konteks tanda tangan HIMA/IM tetapi tidak ada bukti eksplisit Universitas Airlangga/UNAIR/Airlangga, maka `Tingkat = Nasional`.
- Jika ada konteks tanda tangan HIMA/IM dan ada bukti eksplisit Universitas Airlangga/UNAIR/Airlangga, maka `Tingkat = Departemen/Program Studi`.

Catatan: rule ini tidak meng-hardcode sertifikat tertentu. Yang digunakan hanya pola generik organisasi mahasiswa dan konteks institusi.
