# V7 HIMA/IM Tingkat Rule

Changes:
- Added stricter Tingkat mapping for certificates with HIMA/Himpunan Mahasiswa/IM/Ikatan Mahasiswa/student association context in signature-like text.
- If student association signature context exists and Universitas Airlangga/Unair/FTMM affiliation context exists, Tingkat becomes `Departemen/Program Studi`.
- If student association signature context exists without Universitas Airlangga/Unair/FTMM affiliation context, Tingkat becomes `Nasional`.
- Program Studi/Departemen detection now has priority over generic Fakultas/Dekan detection.
- No certificate-specific date/activity hardcode was added. The rule uses generic association and affiliation patterns.
