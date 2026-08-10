# F1 lanjutan — Perbaikan Pemilihan Penyelenggara (v3, tanpa AI)

> Generasi: 2026-08-10 16:02:32 | GT v9 + matcher v2 | baseline = offline_variant F1 (ORG-002) | 0 LLM call

## Hasil

| Metrik | baseline | v3 | delta | gate |
|---|---|---|---|---|
| nama_kegiatan_sertifikasi exact | 6.8% | 6.8% | +0.0% | no-regress |
| waktu_mulai_pelaksanaan exact | 81.8% | 81.8% | +0.0% | no-regress |
| waktu_selesai_pelaksanaan exact | 81.8% | 81.8% | +0.0% | no-regress |
| penyelenggara_kegiatan exact | 39.2% | 54.1% | +14.9% | >=+5pt |
| nomor_bukti_fisik_nomor_sertifikasi exact | 76.9% | 76.9% | +0.0% | no-regress |
| tingkat exact | 81.1% | 81.1% | +0.0% | no-regress |
| MACRO exact | 58.3% | 61.2% | +286.5% | no-regress |

## Verdict

**GATE PASS** — organizer exact 39.2% → 54.1% (gate >=44.2%); no-regress field lain: tidak ada.

## Per-cert organizer: wrong→exact (perbaikan)

| stem | baseline | v3 | GT |
|---|---|---|---|
| 2954933_219642_skp | Himpunan Mahasiswa Statistika | Himpunan Mahasiswa Statistika Fakultas Matematika dan ilmu Pengetahuan Alam Universitas Gadjah Mada | Himpunan Mahasiswa Statistika Fakultas Matematika dan Ilmu Pengetahuan Alam Universitas Gadjah Mada |
| Ananda Aqeel Fathur Rahman_E - Certificate Agentic AI 17 November 2025 | Faculty of Science and Technology | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| Gelar Rasa_Muhammad Fazil Irvan Putra | Himasada | Himasada, Fakultas Ilmu Komputer | Himasada, Fakultas Ilmu Komputer |
| PRIMARIZKI_panitia_binary_2025 | Program Studi S1 Teknologi Sains Data Universitas Airlangga Himpunan Mahasiswa TSD | Program Studi S1 Teknologi Sains Data Universitas Airlangga | Program Studi S1 Teknologi Sains Data Universitas Airlangga |
| Rasio_Faiz | Badan Eksekutif Himpunan Mahasiswa Statistika 2025, Faculty of Mathematics and Natural Sciences FMIPA Universitas Padjadjaran in the Series of Events Statistics Day Elevora | Badan Eksekutif Himpunan Mahasiswa Statistika 2025 | Badan Eksekutif Himpunan Mahasiswa Statistika 2025 |
| 2955331_219642_skp | Literasi Psikologi Indonesia on July 30, 2023 - August 1, 2023. Literasi Psikologi Indonesia Really Appreciate the Hard Work and Sincerity in Being Fully Committed to Realizing the Psychological Well-being of the Indonesian People. W LITERASI PSIKOL INDON Renata Abigail Novlia Alam Rahmad Wedi Apria | Literasi Psikologi Indonesia | Literasi Psikologi Indonesia |
| Sertifikat Kepengurusan IRIS 2025_Muhammad Fazil Irvan Putra | Faculty of Advanced Technology and Multidisciplinary | Innovative Research of Intelligent System (IRIS) Faculty of Advanced Technology and Multidisciplinary | Innovative Research of Intelligent System (IRIS) Faculty of Advanced Technology and Multidisciplinary |
| E-certificate Ananda Aqeel Fathur Rahman (1) | Faculty of Science and Technology | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| SERTIF76 | Penelitian dan Pengembangan Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga | Biro Penelitian dan Pengembangan Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga | Biro Penelitian dan Pengembangan Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga |
| File sertifikat untuk _VenedictGrinaldyPrasetyo__240103_143733_ORM | Library Class Perpustakaan Universitas Airlangga | Perpustakaan Universitas Airlangga | Perpustakaan Universitas Airlangga |
| Venedict_panitia_specta | Which Held From September21 to December7,2024 by Himatesda | Himatesda | Himatesda |

## Per-cert organizer: exact→wrong (regresi)
