# AKT-003 — Deteksi Nama Kegiatan v3: grup A+B+C (0 LLM)

> Generasi: 2026-08-14 13:50:25 | GT v9 + matcher v2 | baseline = offline_prod (produksi PROD-002, flag ON) | 0 LLM call

## Hasil

| Metrik | baseline | AKT-003 | delta | gate |
|---|---|---|---|---|
| nama_kegiatan_sertifikasi exact | 6.8% | 51.4% | +44.6% | >=+5pt |
| waktu_mulai_pelaksanaan exact | 81.8% | 81.8% | +0.0% | no-regress |
| waktu_selesai_pelaksanaan exact | 81.8% | 81.8% | +0.0% | no-regress |
| penyelenggara_kegiatan exact | 63.5% | 63.5% | +0.0% | no-regress |
| nomor_bukti_fisik_nomor_sertifikasi exact | 76.9% | 76.9% | +0.0% | no-regress |
| tingkat exact | 81.1% | 81.1% | +0.0% | no-regress |
| MACRO exact | 63.0% | 71.6% | +8.6% | no-regress |

## Verdict

**GATE PASS** — nama_kegiatan exact 6.8% → 51.4% (gate >=+5pt); no-regress: tidak ada.

## Fix (wrong -> exact)

| stem | AKT-003 | GT |
|---|---|---|
| Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 17 Nov 2023 | Artificial intelligence: Reality Versus Myths | Artificial intelligence: Reality Versus Myths |
| 2030372_219642_skp | Economic Week 2023 | Economic Week 2023 |
| 1981676_219642_skp | Bincang Santai Intelektual 2 | Bincang Santai Intelektual 2 |
| 2030325_219642_skp | Magang UKM Universitas Airlangga | Magang UKM Universitas Airlangga |
| Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 9 Nov 2023 | Information Security in the Digital Era | Information Security in the Digital Era |
| 2065179_219642_skp | REGTER (REGENERASI TERPADU) 2023 | REGTER (Regenerasi Terpadu) 2023 |
| Ananda Aqeel Fathur Rahman_Guest Lecture ERP SAP 25 April 2025 | Introduction ERP SAP Business One | Introduction ERP SAP Business One |
| PRIMARIZKI_panitia_dataquest_2025 | Dataquest 4.0 part of Airnology 4.0 | Dataquest 4.0 part of Airnology 4.0 |
| Primarizki Ahmad Hariyono_data slayer 2_lomba | Data Slayer 2.0 | Data Slayer 2.0 |
| 2954631_219642_skp | Academic Competition of Data Science 2025 | Academic Competition of Data Science 2025 |
| Rasio_Faiz | University Infographic Competition RASIO 9.0 | University Infographic Competition RASIO 9.0 |
| 2398697_219642_skp | Airlangga Job Preparation 2023 | Airlangga Job Preparation 2023 |
| Primarizki Ahmad Hariyono_gammafest_lomba | GAMMAFEST 2025 | GAMMAFEST 2025 |
| primarizki_panitia_binary_2024 | BINARY 4.0 (Building Freshman Solidarity and Character Development) | BINARY 4.0 (Building Freshman Solidarity and Character Development) |
| ACTION_Muhammad Fazil Irvan Putra_compressed | Academic Competition of Data Science 2024 | Academic Competition of Data Science 2024 |
| E-certificate Ananda Aqeel Fathur Rahman (1) | Connected and Smart cities -Towards a Sustainable Future | Connected and Smart Cities - Towards a Sustainable Future |
| Sertifikat_Peserta_Primarizki Ahmad Hariyono_ML | Sriwijaya Informatics Exhibition 2025 | Sriwijaya Informatics Exhibition 2025 |
| 1952296_219642_skp | Public Health Career Track 2 | Public Health Career Track 2 |
| SERTIF76 | Training Meeting Internal Vol. 1 | Training Meeting Internal Vol. 1 |
| 2954707_219642_skp | Competition of Design | Competition of Design |
| BTF_Faiz | BLUE TECHNO FESTIVAL | BLUE TECHNO FESTIVAL |
| File sertifikat untuk _VenedictGrinaldyPrasetyo__240103_143733_ORM | Online Research Management | Online Research Management |
| Airno_Faiz | Dataquest 3.0 part of Airnology 3.0 | Dataquest 3.0 part of Airnology 3.0 |
| Poisson.Faiz | Poisson Statistics Competition 2025 | Poisson Statistics Competition 2025 |
| Sertif sinem_vene_magang UKM | Magang UKM Universitas Airlangga | Magang UKM Universitas Airlangga |
| Primarizki_kim_unair_2024 | Kompetisi Ilmiah Mahasiswa (KIM) Universitas Airlangga 2024 | Kompetisi Ilmiah Mahasiswa (KIM) Universitas Airlangga 2024 |
| UNITY_Muhammad Fazil Irvan Putra | UNY National Information Technology Competition (UNITY) #14 Tahun 2026 | UNY National Information Technology Competition (UNITY) #14 Tahun 2026 |
| 2030335_219642_skp | Public Health Career Track 3 | Public Health Career Track 3 |
| 1963507_219642_skp | Webinar mengenai Global Warming | Webinar mengenai Global Warming |
| 2439919_221065_skp | Hology 7.0 | Hology 7.0 |
| 2071996_221065_skp | Magang UKM Universitas Airlangga | Magang UKM Universitas Airlangga |
| 1930354_219642_skp | Hari Anak Nasional | Hari Anak Nasional |
| KARSA_Venedict_peserta | (KARs A) 2023 | Pengenalan Kehidupan Kampus bagi Mahasiswa Baru Fakultas (KARSA) 2023 |

## Regress (exact -> wrong)

tidak ada

## Changed non-exact (QA sloppiness — anchor fire index)

| stem | old (v2) | new (v3) | anchor# |
|---|---|---|---|
| 2160238_221065_skp | None | 'Airlangga Career & Internship Club' | 16 |
| 2954571_219642_skp | None | 'Lomba Infografis' | 17 |
| ACW_Faiz | 'Academic Weeks 2026yangdiselenggarakan' | 'Academic Weeks 2026' | 6 |
| hakim_lomba | 'GRADl ANT 2.0yangdiselenggarakanoleh Himpunan Mahasiswa' | 'GRADl ANT 2.0' | 1 |
| FIT_Faiz | None | 'FITCOMPETITION 2026' | 15 |

## OOD noise (QA, bukan gate)

- Noise 10%: baseline 5.4% (drop +1.4pt) | AKT-003 45.9% (drop +5.4pt, ekstra +4.1pt)
- Noise 25%: baseline 5.4% (drop +1.4pt) | AKT-003 40.5% (drop +10.8pt, ekstra +9.5pt)

> Drop ekstra vs baseline = harga rule teks-bergantung (sama pola AKT-002/R1/R4). Gain absolut tetap positif di semua level noise. Bila di-port produksi: pola KEEP/GUARD.