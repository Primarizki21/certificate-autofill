# PROD-002 — Re-eval Port Produksi Normalisasi Organizer & Nomor

> Generasi: 2026-08-13 13:50:20 | GT v9 + matcher v2 | baseline = offline_fields (produksi current) | 0 LLM call | flag ENABLE_ORGANIZER_NORMALIZATION (default OFF)

## Hasil

| Metrik | baseline (produksi current) | PROD path | REF replica |
|---|---|---|---|
| nama_kegiatan_sertifikasi exact | 6.8% | 6.8% | 6.8% |
| waktu_mulai_pelaksanaan exact | 81.8% | 81.8% | 81.8% |
| waktu_selesai_pelaksanaan exact | 81.8% | 81.8% | 81.8% |
| penyelenggara_kegiatan exact | 37.8% | 63.5% | 63.5% |
| nomor_bukti_fisik_nomor_sertifikasi exact | 59.6% | 76.9% | 76.9% |
| tingkat exact | 81.1% | 81.1% | 81.1% |
| MACRO exact | 55.7% | 63.0% | 63.0% |

## Verdict

**GATE PASS** — port fidelity prod==ref: OK (0 mismatch); no-regress vs baseline: tidak ada.

> Port spec (handoff v29 + KOREKSI R3): KEEP R0/PREFIX_HELD/R2/R3/R6 + F1 alias + F3 BEM FKM + nomor D/E; SKIP R1/R4 (2 fix dikorbankan, 0 risiko); DROP R5. KOREKSI: R3 (strip sampai 'oleh') BUKAN dead code — ablation OOD diukur pre-ORG-004 tanpa lapisan alias; di port final R3 membuka alias F1 APHSA (1952296/2030335 = 2 fix). R1 = Rasio_Faiz (suffix faculty), R4 = 2955331 (date suffix).

## Fix vs baseline (wrong -> exact)

| stem | field | PROD | GT |
|---|---|---|---|
| Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 17 Nov 2023 | penyelenggara_kegiatan | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| 2954933_219642_skp | penyelenggara_kegiatan | Himpunan Mahasiswa Statistika Fakultas Matematika dan ilmu Pengetahuan Alam Universitas Gadjah Mada | Himpunan Mahasiswa Statistika Fakultas Matematika dan Ilmu Pengetahuan Alam Universitas Gadjah Mada |
| Ananda Aqeel Fathur Rahman_E - Certificate Agentic AI 17 November 2025 | penyelenggara_kegiatan | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| Gelar Rasa_Muhammad Fazil Irvan Putra | penyelenggara_kegiatan | Himasada, Fakultas Ilmu Komputer | Himasada, Fakultas Ilmu Komputer |
| 1981676_219642_skp | nomor_bukti_fisik_nomor_sertifikasi | 542/A.5/BINCANGSANTAIINTELEKTUAL/BEMFEBUNAIR/XI/2023 | 542/A.5/BINCANG SANTAI INTELEKTUAL/BEM FEB UNAIR/XI/2023 |
| Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 9 Nov 2023 | penyelenggara_kegiatan | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| Ananda Aqeel Fathur Rahman_Guest Lecture ERP SAP 25 April 2025 | penyelenggara_kegiatan | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| 2954571_219642_skp | nomor_bukti_fisik_nomor_sertifikasi | SERT-2465/PKN.1/2025 | SERT-2465/PKN.1/2025 |
| PRIMARIZKI_panitia_binary_2025 | penyelenggara_kegiatan | Program Studi S1 Teknologi Sains Data Universitas Airlangga | Program Studi S1 Teknologi Sains Data Universitas Airlangga |
| Primarizki Ahmad Hariyono_data slayer 2_lomba | nomor_bukti_fisik_nomor_sertifikasi | 804/AKD01/SDT-000/2024 | 804/AKD01/SDT-000/2024 |
| ACW_Faiz | nomor_bukti_fisik_nomor_sertifikasi | SERT-2128/BEM/2026 | SERT-2128/BEM/2026 |
| SSF_Faiz | nomor_bukti_fisik_nomor_sertifikasi | 4330/UN27/KM.05.04/2025 | 4330/UN27/KM.05.04/2025 |
| Ananda Aqeel Fathur Rahman_Guest Lecture FDM 29 November 2024 | penyelenggara_kegiatan | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| Sertifikat Kepengurusan IRIS 2025_Muhammad Fazil Irvan Putra | penyelenggara_kegiatan | Innovative Research of Intelligent System (IRIS) Faculty of Advanced Technology and Multidisciplinary | Innovative Research of Intelligent System (IRIS) Faculty of Advanced Technology and Multidisciplinary |
| primarizki_panitia_binary_2024 | penyelenggara_kegiatan | Program Studi S1 Teknologi Sains Data Universitas Airlangga | Program Studi S1 Teknologi Sains Data Universitas Airlangga |
| hakim_lomba | nomor_bukti_fisik_nomor_sertifikasi | 016/A.1/GRADIANT2.0/HMA/XI/2025 | 016/A.1/GRADIANT 2.0/HMA/XI/2025 |
| E-certificate Ananda Aqeel Fathur Rahman (1) | penyelenggara_kegiatan | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| Sertifikat_Peserta_Primarizki Ahmad Hariyono_ML | nomor_bukti_fisik_nomor_sertifikasi | 1164/UN9.1.9.HMIF/SE/2025 | 1164/UN9.1.9.HMIF/SE/2025 |
| 1952296_219642_skp | penyelenggara_kegiatan | Divisi Kaprof APHSA BEM FKM Universitas Airlangga | Divisi Kaprof APHSA BEM FKM Universitas Airlangga |
| SERTIF76 | penyelenggara_kegiatan | Biro Penelitian dan Pengembangan Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga | Biro Penelitian dan Pengembangan Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga |
| Ananda Aqeel Fathur Rahman_Guest Lecture 25 October 2024 | penyelenggara_kegiatan | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| File sertifikat untuk _VenedictGrinaldyPrasetyo__240103_143733_ORM | penyelenggara_kegiatan | Perpustakaan Universitas Airlangga | Perpustakaan Universitas Airlangga |
| BINARY_Venedict_peserta | penyelenggara_kegiatan | Program Studi S1 Teknologi Sains Data | Program Studi S1 Teknologi Sains Data |
| 2030335_219642_skp | penyelenggara_kegiatan | Divisi Kajian dan Keprofesian APHSA BEM FKM Universitas Airlangga | Divisi Kajian dan Keprofesian APHSA BEM FKM Universitas Airlangga |
| 2439919_221065_skp | penyelenggara_kegiatan | Faculty of Computer Science Brawijaya University | Faculty of Computer Science Brawijaya University |
| 2954421_219642_skp | nomor_bukti_fisik_nomor_sertifikasi | 1688/UN4.1.17.6/JM.02.00/2026 | 1688/UN4.1.17.6/JM.02.00/2026 |
| KARSA_Venedict_peserta | nomor_bukti_fisik_nomor_sertifikasi | 1944/UN3.FTMM/TM.00.02/2023 | 1944/UN3.FTMM/TM.00.02/2023 |
| Venedict_panitia_specta | penyelenggara_kegiatan | Himatesda | Himatesda |

## Regress vs baseline (exact -> wrong)

tidak ada