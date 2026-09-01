# B7 — De-Corpusing Catalog & Pure Semantic Ablation (N=74)

> Generasi: 2026-09-01 19:09:48 | GT v9 + matcher v2.

## Katalog Literal Ter-memorasi

| Literal String | File Sumber | Fungsi | Field | Firing Freq (cert) | Rekomendasi Generalisasi Semantic |
|---|---|---|---|---|---|
| `KARSAFTMM2024 / KARSA FTMM 2024` | combined_extractor.py | extract_activity_v6 | nama_kegiatan_sertifikasi | 0 | ganti anchor struktural (B5) |
| `SPECTA 2024` | combined_extractor.py | extract_activity_v6 | nama_kegiatan_sertifikasi | 1 | ganti anchor struktural (B5) |
| `Falcon Project` | combined_extractor.py | extract_activity_v6 | nama_kegiatan_sertifikasi | 0 | ganti anchor struktural (B5) |
| `Health Buddies: From Insecure to Unstoppable` | combined_extractor.py | extract_activity_v6 | nama_kegiatan_sertifikasi | 0 | ganti anchor struktural (B5) |
| `Agentic AI - Foundations and Emerging Applications in Softwa` | combined_extractor.py | extract_activity_v6 | nama_kegiatan_sertifikasi | 1 | ganti anchor struktural (B5) |
| `Youth Today x AIESEC Future Leaders` | combined_extractor.py | extract_activity_v6 | nama_kegiatan_sertifikasi | 1 | ganti anchor struktural (B5) |
| `PKKMB Universitas Airlangga` | combined_extractor.py | extract_activity_v6 | nama_kegiatan_sertifikasi | 0 | ganti anchor struktural (B5) |
| `Digital Campaign 2023: "Level Up Yourself Starting Right Now` | combined_extractor.py | extract_activity_v7 | nama_kegiatan_sertifikasi | 1 | ganti anchor struktural (B5) |
| `Give Yourself A Break: The Power Of Self Compassion` | combined_extractor.py | extract_activity_v7 | nama_kegiatan_sertifikasi | 1 | ganti anchor struktural (B5) |
| `From Discrete Mathematics to Risk Management Systems: a Prac` | combined_extractor.py | extract_activity_v7 | nama_kegiatan_sertifikasi | 1 | ganti anchor struktural (B5) |
| `EmpowerED` | combined_extractor.py | extract_activity_v7 | nama_kegiatan_sertifikasi | 1 | ganti anchor struktural (B5) |
| `270/A.5/SOCIAL ACTION/BEM FEB UNAIR/IX/2023` | combined_extractor.py | normalize_nomor_v4 | nomor_bukti_fisik_nomor_sertifikasi | 0 | ganti guard format (B6) |
| `06/001/B/P.GIRI STAT/HMP STATISTIKA/IV/2026` | combined_extractor.py | normalize_nomor_v4 | nomor_bukti_fisik_nomor_sertifikasi | 0 | ganti guard format (B6) |
| `UKM Forum for Information and Statistical Studies (Forkas)` | combined_extractor.py | normalize_organizer_v6 | penyelenggara_kegiatan | 1 | ganti alias generik |
| `Himpunan Mahasiswa Statistika (himasta)` | combined_extractor.py | normalize_organizer_v6 | penyelenggara_kegiatan | 3 | ganti alias generik |
| `F1 aliases (5 string canonical)` | organizer_normalize.py | _norm_org_format | penyelenggara_kegiatan | 0 | ganti alias generik |
| `R6 himasada/IRIS/dept-suffix maps` | organizer_normalize.py | _enrich_organizer | penyelenggara_kegiatan | 0 | ganti alias generik |
| `Airnology / Kakiwima / SPECTA / Brief keyword` | field_extractor.py | extract_activity_name | nama_kegiatan_sertifikasi | 0 | ganti anchor struktural (B5) |

## Ablasi Mode A (Assisted) vs Mode B (Pure Semantic)

| Field | Mode A exact | Mode B exact | Assist (pt) | Mode A fuzzy | Mode B fuzzy |
|---|---|---|---|---|---|
| nama_kegiatan_sertifikasi | 79.7% | 67.6% | +12.2 | 85.1% | 83.8% |
| waktu_mulai_pelaksanaan | 96.4% | 96.4% | +0.0 | 96.4% | 96.4% |
| waktu_selesai_pelaksanaan | 96.4% | 96.4% | +0.0 | 96.4% | 96.4% |
| penyelenggara_kegiatan | 78.4% | 47.3% | +31.1 | 83.8% | 78.4% |
| nomor_bukti_fisik_nomor_sertifikasi | 92.3% | 92.3% | +0.0 | 92.3% | 92.3% |
| tingkat | 90.5% | 89.2% | +1.4 | 90.5% | 89.2% |

**Pure Semantic MACRO exact: 79.4%** (Mode A: 88.0%, assist +8.6pt) — baseline OOD murni tanpa literal.
