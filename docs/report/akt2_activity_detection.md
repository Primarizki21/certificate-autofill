# AKT-002 — Deteksi Nama Kegiatan v2 (0 LLM)

> Generasi: 2026-08-13 14:24:52 | GT v9 + matcher v2 | baseline = offline_prod (produksi PROD-002, flag ON) | 0 LLM call

## Hasil

| Metrik | baseline | AKT-002 | delta | gate |
|---|---|---|---|---|
| nama_kegiatan_sertifikasi exact | 6.8% | 36.5% | +29.7% | >=+5pt |
| waktu_mulai_pelaksanaan exact | 81.8% | 81.8% | +0.0% | no-regress |
| waktu_selesai_pelaksanaan exact | 81.8% | 81.8% | +0.0% | no-regress |
| penyelenggara_kegiatan exact | 63.5% | 63.5% | +0.0% | no-regress |
| nomor_bukti_fisik_nomor_sertifikasi exact | 76.9% | 76.9% | +0.0% | no-regress |
| tingkat exact | 81.1% | 81.1% | +0.0% | no-regress |
| MACRO exact | 63.0% | 68.8% | +5.7% | no-regress |

## Verdict

**GATE PASS** — nama_kegiatan exact 6.8% → 36.5% (gate >=+5pt); no-regress: tidak ada.

## Fix (wrong -> exact)

| stem | AKT-002 | GT |
|---|---|---|
| Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 17 Nov 2023 | Artificial intelligence: Reality Versus Myths | Artificial intelligence: Reality Versus Myths |
| 2030372_219642_skp | Economic Week 2023 | Economic Week 2023 |
| 1981676_219642_skp | Bincang Santai Intelektual 2 | Bincang Santai Intelektual 2 |
| Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 9 Nov 2023 | Information Security in the Digital Era | Information Security in the Digital Era |
| 2065179_219642_skp | REGTER (REGENERASI TERPADU) 2023 | REGTER (Regenerasi Terpadu) 2023 |
| Ananda Aqeel Fathur Rahman_Guest Lecture ERP SAP 25 April 2025 | Introduction ERP SAP Business One | Introduction ERP SAP Business One |
| PRIMARIZKI_panitia_dataquest_2025 | Dataquest 4.0 part of Airnology 4.0 | Dataquest 4.0 part of Airnology 4.0 |
| Primarizki Ahmad Hariyono_data slayer 2_lomba | Data Slayer 2.0 | Data Slayer 2.0 |
| 2954631_219642_skp | Academic Competition of Data Science 2025 | Academic Competition of Data Science 2025 |
| Rasio_Faiz | University Infographic Competition RASIO 9.0 | University Infographic Competition RASIO 9.0 |
| Primarizki Ahmad Hariyono_gammafest_lomba | GAMMAFEST 2025 | GAMMAFEST 2025 |
| primarizki_panitia_binary_2024 | BINARY 4.0 (Building Freshman Solidarity and Character Development) | BINARY 4.0 (Building Freshman Solidarity and Character Development) |
| ACTION_Muhammad Fazil Irvan Putra_compressed | Academic Competition of Data Science 2024 | Academic Competition of Data Science 2024 |
| E-certificate Ananda Aqeel Fathur Rahman (1) | Connected and Smart cities -Towards a Sustainable Future | Connected and Smart Cities - Towards a Sustainable Future |
| Sertifikat_Peserta_Primarizki Ahmad Hariyono_ML | Sriwijaya Informatics Exhibition 2025 | Sriwijaya Informatics Exhibition 2025 |
| SERTIF76 | Training Meeting Internal Vol. 1 | Training Meeting Internal Vol. 1 |
| 2954707_219642_skp | Competition of Design | Competition of Design |
| BTF_Faiz | BLUE TECHNO FESTIVAL | BLUE TECHNO FESTIVAL |
| Airno_Faiz | Dataquest 3.0 part of Airnology 3.0 | Dataquest 3.0 part of Airnology 3.0 |
| UNITY_Muhammad Fazil Irvan Putra | UNY National Information Technology Competition (UNITY) #14 Tahun 2026 | UNY National Information Technology Competition (UNITY) #14 Tahun 2026 |
| 1963507_219642_skp | Webinar mengenai Global Warming | Webinar mengenai Global Warming |
| 1930354_219642_skp | Hari Anak Nasional | Hari Anak Nasional |

## Regress (exact -> wrong)

tidak ada

## OOD noise (QA, bukan gate)

- Noise 10%: baseline 5.4% (drop +1.4pt) | AKT-002 32.4% (drop +4.1pt, ekstra +2.7pt)
- Noise 25%: baseline 5.4% (drop +1.4pt) | AKT-002 27.0% (drop +9.5pt, ekstra +8.1pt)

> Anchor phrase teks-bergantung: drop ekstra di noise (10% +2.7pt, 25% +8.1pt) — pola sama R1/R4 organizer (OOD-002/003). Gain absolut tetap positif di semua level (10%: 32.4% vs 5.4%; 25%: 27.0% vs 5.4%). Bila di-port produksi: ikuti pola KEEP/GUARD (anchor = GUARD needs_review F6).