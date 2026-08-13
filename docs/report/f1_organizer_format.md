# F1 lanjutan — ORG-004: Canonicalisasi Organizer (bucket format, tanpa AI)

> Generasi: 2026-08-13 10:04:43 | GT v9 + matcher v2 | baseline = offline_v3 (F1C-001) | 0 LLM call

## Hasil

| Metrik | v3 | ORG-004 | delta | gate |
|---|---|---|---|---|
| nama_kegiatan_sertifikasi exact | 6.8% | 6.8% | +0.0% | no-regress |
| waktu_mulai_pelaksanaan exact | 81.8% | 81.8% | +0.0% | no-regress |
| waktu_selesai_pelaksanaan exact | 81.8% | 81.8% | +0.0% | no-regress |
| penyelenggara_kegiatan exact | 54.1% | 66.2% | +12.2% | >=+5pt |
| nomor_bukti_fisik_nomor_sertifikasi exact | 76.9% | 76.9% | +0.0% | no-regress |
| tingkat exact | 81.1% | 81.1% | +0.0% | no-regress |
| MACRO exact | 61.2% | 63.5% | +2.3% | no-regress |

## Verdict

**GATE PASS** — organizer exact 54.1% → 66.2% (gate >=+5pt); no-regress: tidak ada.

## Fix organizer (wrong→exact)

| stem | ORG-004 | GT |
|---|---|---|
| Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 17 Nov 2023 | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 9 Nov 2023 | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| Ananda Aqeel Fathur Rahman_Guest Lecture ERP SAP 25 April 2025 | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| Ananda Aqeel Fathur Rahman_Guest Lecture FDM 29 November 2024 | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| 1952296_219642_skp | Divisi Kaprof APHSA BEM FKM Universitas Airlangga | Divisi Kaprof APHSA BEM FKM Universitas Airlangga |
| Ananda Aqeel Fathur Rahman_Guest Lecture 25 October 2024 | Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology Information System Dept. |
| BINARY_Venedict_peserta | Program Studi S1 Teknologi Sains Data | Program Studi S1 Teknologi Sains Data |
| 2030335_219642_skp | Divisi Kajian dan Keprofesian APHSA BEM FKM Universitas Airlangga | Divisi Kajian dan Keprofesian APHSA BEM FKM Universitas Airlangga |
| 2439919_221065_skp | Faculty of Computer Science Brawijaya University | Faculty of Computer Science Brawijaya University |

## Regress

tidak ada

## OOD (drop vs baseline v3, sama OOD-003 gate)

- Mutation MACRO exact drop: v3 +10.4% | ORG-004 +10.9%
- Noise 0% drop: v3 +0.0% | ORG-004 +0.0%
- Noise 10% drop: v3 +9.1% | ORG-004 +9.1%
- Noise 25% drop: v3 +18.0% | ORG-004 +18.0%
- Noise 50% drop: v3 +27.3% | ORG-004 +27.3%