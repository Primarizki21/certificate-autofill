# C1-001 — Verifikasi AKT-005 di korpus OCR branch (scan-49)

> Generasi: 2026-08-27 09:27:21 | GT v9 + matcher v2 | teks = baseline_rapid_tess (OCR branch) | 0 LLM call

## Latar

Frontier handoff v38 #5 mencatat nama_kegiatan 6.1% exact 'semua varian' di cabang OCR.
Hipotesis: artefak harness — eval cabang OCR memakai extractor produksi, sedangkan perbaikan AKT-002..005 (62.2% all-74) tidak pernah dipasang di sana.
Catatan: korpus AKT (run_20260728_131835, teks pipeline produksi) TERBUKTI BEDA dari baseline_rapid_tess (raw OCR) utk stem yang sama — verifikasi ini sah.

## Hasil — scan-49 (baseline_rapid_tess)

| Metrik | offline_prod | +AKT-005 |
|---|---|---|
| nama_kegiatan_sertifikasi exact | 6.1% (3/49) | 59.2% (29/49) |
| nama_kegiatan_sertifikasi fuzzy | 12.2% | 83.7% |
| MACRO exact | 59.60% | 70.00% |

Fixes: **27** | Regresses: **1** | regress field lain: tidak ada

## Fix (wrong -> exact, scan-49)

- `2954685_219642_skp`: 'UX DESIGN competition' (GT: 'UX DESIGN COMPETITION')
- `Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 17 Nov 2023`: 'Artificial intelligence: Reality Versus Myths' (GT: 'Artificial intelligence: Reality Versus Myths')
- `Primarizki_panitia_synreaach_2024`: 'DEKAN CUP FTMM 2024 BY SYNREACH FTMM 2024' (GT: 'Dekan Cup FTMM 2024 by SYNREACH FTMM 2024')
- `2160238_221065_skp`: 'Airlangga Career & Internship Club [ACIC] SPEAK UP &STAND OUT:MENGASAH KETERAMPILAN KOMUNIKASI DI ERA KARIR DIGITAL' (GT: 'Airlangga Career & Internship Club [ACIC] SPEAK UP & STAND OUT: MENGASAH KETERAMPILAN KOMUNIKASI DI ERA KARIR DIGITAL')
- `Gelar Rasa_Muhammad Fazil Irvan Putra`: 'GELAR RASA 2024' (GT: 'GELAR RASA 2024')
- `2030325_219642_skp`: 'Magang UKM Universitas Airlangga' (GT: 'Magang UKM Universitas Airlangga')
- `Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 9 Nov 2023`: 'Information Security in the Digital Era' (GT: 'Information Security in the Digital Era')
- `Ananda Aqeel Fathur Rahman_Guest Lecture ERP SAP 25 April 2025`: 'Introduction ERP SAP Business One' (GT: 'Introduction ERP SAP Business One')
- `Primarizki Ahmad Hariyono_data slayer 2_lomba`: 'Data Slayer 2.0' (GT: 'Data Slayer 2.0')
- `2954631_219642_skp`: 'Academic competition of Data Science 2025' (GT: 'Academic Competition of Data Science 2025')
- `2398697_219642_skp`: 'Airlangga Job Preparation 2023' (GT: 'Airlangga Job Preparation 2023')
- `NIC_Faiz`: 'National competition of de Estadisticas 4.0' (GT: 'National Competition of de Estadisticas 4.0')
- `primarizki_panitia_binary_2024`: 'BINARY 4.0 (Building Freshman Solidarity and Character Development)' (GT: 'BINARY 4.0 (Building Freshman Solidarity and Character Development)')
- `Girifest_Faiz`: 'Event Giri Statistics Fest 2026 kategori Lomba NISC' (GT: 'Event Giri Statistics Fest 2026 Kategori Lomba NISC')
- `E-certificate Ananda Aqeel Fathur Rahman (1)`: 'Connected and Smart cities -Towards a Sustainable Future' (GT: 'Connected and Smart Cities - Towards a Sustainable Future')
- `1952296_219642_skp`: 'Public Health Career Track 2' (GT: 'Public Health Career Track 2')
- `SERTIF76`: 'Training Meeting Internal Vol. 1' (GT: 'Training Meeting Internal Vol. 1')
- `2954707_219642_skp`: 'competition of Design' (GT: 'Competition of Design')
- `Airno_Faiz`: 'Dataquest 3.0 part of Airnology 3.0' (GT: 'Dataquest 3.0 part of Airnology 3.0')
- `FIT_Faiz`: 'FIT competition 2026' (GT: 'FIT COMPETITION 2026')
- `Poisson.Faiz`: 'Poisson Statistics competition 2025' (GT: 'Poisson Statistics Competition 2025')
- `Sertif sinem_vene_magang UKM`: 'Magang UKM Universitas Airlangga' (GT: 'Magang UKM Universitas Airlangga')
- `Primarizki_kim_unair_2024`: 'Kompetisi Ilmiah Mahasiswa (KIM) Universitas Airlangga 2024' (GT: 'Kompetisi Ilmiah Mahasiswa (KIM) Universitas Airlangga 2024')
- `UNITY_Muhammad Fazil Irvan Putra`: 'UNY National Information Technology competition (UNITY) #14 Tahun 2026' (GT: 'UNY National Information Technology Competition (UNITY) #14 Tahun 2026')
- `2030335_219642_skp`: 'Public Health Career Track 3' (GT: 'Public Health Career Track 3')
- `2439919_221065_skp`: 'Hology 7.0' (GT: 'Hology 7.0')
- `2071996_221065_skp`: 'Magang UKM Universitas Airlangga' (GT: 'Magang UKM Universitas Airlangga')

## Regress (exact -> wrong, scan-49)

- `KARSA_Venedict_peserta`: 'Pengenalan Kehidupan Kampus bagi Mahasiswa Baru Fakultas' (GT: 'Pengenalan Kehidupan Kampus bagi Mahasiswa Baru Fakultas (KARSA) 2023')

## Pembanding all-74 (korpus AKT asli)

| Metrik | offline_prod | +AKT-005 |
|---|---|---|
| nama_kegiatan_sertifikasi exact | 8.1% (6/74) | 56.8% (42/74) |

