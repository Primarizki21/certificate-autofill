# AKT-001 — Taksonomi Mismatch Nama Kegiatan (ceiling riil)

> Generasi: 2026-08-13 14:11:54 | GT v9 + matcher v2 | pipeline = offline_prod (produksi PROD-002, flag ON) | zero LLM

Nama kegiatan exact saat ini: **6.8%** (5/74). Sisa 69 non-exact diklasifikasikan di bawah. Ceiling per kategori = jumlah kasus — kalau SEMUA kasus kategori itu diperbaiki (asumsi optimis, ceiling atas).

## Taksonomi & ceiling

| Kategori | Kasus | Ceiling exact bila diperbaiki | Jenis perbaikan |
|---|---|---|---|
| kosong | 57 | 62/74 (83.8%) | DETEKSI (perluas pattern + repair OCR-merge) |
| salah_kegiatan | 4 | 9/74 (12.2%) | guard/scoring keyword extractor |
| kurang_lengkap | 3 | 8/74 (10.8%) | enrich prefix/suffix dari teks |
| kelebihan | 3 | 8/74 (10.8%) | strip junk suffix (murah) |
| format_ocr | 2 | 7/74 (9.5%) | canonical alias / case norm (matcher v2.1) |

## Sinyal deteksi (kosong) — feasibility AKT-002

- **52/57** kasus kosong: nama kegiatan GT MUNCUL di teks raw (compact/overlap) → deteksi regex feasible dari teks, tinggal pattern coverage.
- 5 kasus kosong: nama kegiatan TIDAK terwakili di teks (OCR gagal / hanya lewat konteks) → butuh LLM per-field atau OCR baru.

> Ceiling total (semua kategori, 100% perbaikan): **74/74 (100.0%)** — target realistis dipilih dari kategori terbesar, bukan semua sekaligus.

## Rincian per sertifikat (non-exact)

| stem | status | extracted | GT | kategori | alasan | in_text |
|---|---|---|---|---|---|---|
| KARSA_Venedict_peserta | fuzzy | Pengenalan Kehidupan Kampus bagi Mahasiswa Baru (PKKMB) | Pengenalan Kehidupan Kampus bagi Mahasiswa Baru Fakultas (KARSA) 2023 | format_ocr | near-match (case/OCR/alias): 'Pengenalan Kehidupan Kampus bagi Mahasiswa Baru (PKKMB)' vs 'Pengenalan Kehidupan Kampus bagi Mahasiswa Baru Fakultas (KARSA) 2023' (6 kata sama) | tidak |
| VENEDICT_sertif_bem | fuzzy | Badan Eksekutif Mahasiswa Fakultas Teknologi Maju Dan Multidisiplin Universitas Airlangga | Kepengurusan Badan Eksekutif Mahasiswa Fakultas Teknologi Maju dan Multidisiplin Masa Bakti Tahun 2024 | format_ocr | near-match (case/OCR/alias): 'Badan Eksekutif Mahasiswa Fakultas Teknologi Maju Dan Multidisiplin Universitas Airlangga' vs 'Kepengurusan Badan Eksekutif Mahasiswa Fakultas Teknologi Maju dan Multidisiplin Masa Bakti Tahun 2024' (8 kata sama) | ya |
| Airno_Faiz | fuzzy | Dataquest 3.0 Part Of Airnology 3.0 Untuk Kategori Sma/sederajat Dan Mahasiswa | Dataquest 3.0 part of Airnology 3.0 | kelebihan | extracted 'Dataquest 3.0 Part Of Airnology 3.0 Untuk Kategori Sma/sederajat Dan Mahasiswa' > GT 'Dataquest 3.0 part of Airnology 3.0' (junk ikut ke-capture) | ya |
| BTF_Faiz | fuzzy | BLUE TECHNO FESTIVAL Pada Perlombaan Io T Tech Competition | BLUE TECHNO FESTIVAL | kelebihan | extracted 'BLUE TECHNO FESTIVAL Pada Perlombaan Io T Tech Competition' > GT 'BLUE TECHNO FESTIVAL' (junk ikut ke-capture) | ya |
| PRIMARIZKI_panitia_dataquest_2025 | fuzzy | Dataquest 4.0 Part Of Airnology 4.0 Untuk Kategori Sma/sederajat Dan Mahasiswa | Dataquest 4.0 part of Airnology 4.0 | kelebihan | extracted 'Dataquest 4.0 Part Of Airnology 4.0 Untuk Kategori Sma/sederajat Dan Mahasiswa' > GT 'Dataquest 4.0 part of Airnology 4.0' (junk ikut ke-capture) | ya |
| 1930354_219642_skp | wrong | (kosong) | Hari Anak Nasional | kosong | nilai kosong (tak terdeteksi) | ya |
| 1952296_219642_skp | wrong | (kosong) | Public Health Career Track 2 | kosong | nilai kosong (tak terdeteksi) | ya |
| 1966887_221065_skp | wrong | (kosong) | Youth Today x AIESEC Future Leaders | kosong | nilai kosong (tak terdeteksi) | ya |
| 1981676_219642_skp | wrong | (kosong) | Bincang Santai Intelektual 2 | kosong | nilai kosong (tak terdeteksi) | ya |
| 2030325_219642_skp | wrong | (kosong) | Magang UKM Universitas Airlangga | kosong | nilai kosong (tak terdeteksi) | ya |
| 2030335_219642_skp | wrong | (kosong) | Public Health Career Track 3 | kosong | nilai kosong (tak terdeteksi) | ya |
| 2030372_219642_skp | wrong | (kosong) | Economic Week 2023 | kosong | nilai kosong (tak terdeteksi) | ya |
| 2065179_219642_skp | wrong | (kosong) | REGTER (Regenerasi Terpadu) 2023 | kosong | nilai kosong (tak terdeteksi) | ya |
| 2071996_221065_skp | wrong | (kosong) | Magang UKM Universitas Airlangga | kosong | nilai kosong (tak terdeteksi) | ya |
| 2135790_221065_skp | wrong | (kosong) | SIDConnect - Future Talent Fusion : EmpowerED with SID | kosong | nilai kosong (tak terdeteksi) | ya |
| 2160238_221065_skp | wrong | (kosong) | Airlangga Career & Internship Club [ACIC] SPEAK UP & STAND OUT: MENGASAH KETERAMPILAN KOMUNIKASI DI ERA KARIR DIGITAL | kosong | nilai kosong (tak terdeteksi) | ya |
| 2398697_219642_skp | wrong | (kosong) | Airlangga Job Preparation 2023 | kosong | nilai kosong (tak terdeteksi) | ya |
| 2398703_219642_skp | wrong | (kosong) | Digital Campaign 2023: "Level Up Yourself Starting Right Now" SCHOLAH-UNAIR Mengajar | kosong | nilai kosong (tak terdeteksi) | ya |
| 2439919_221065_skp | wrong | (kosong) | Hology 7.0 | kosong | nilai kosong (tak terdeteksi) | ya |
| 2954283_219642_skp | wrong | (kosong) | The AI Revolution: Technological Frontiers and Redefining Learning in Higher Education | kosong | nilai kosong (tak terdeteksi) | ya |
| 2954571_219642_skp | wrong | (kosong) | Enchantax 2.0 | kosong | nilai kosong (tak terdeteksi) | tidak |
| 2954631_219642_skp | wrong | (kosong) | Academic Competition of Data Science 2025 | kosong | nilai kosong (tak terdeteksi) | ya |
| 2954685_219642_skp | wrong | (kosong) | UX DESIGN COMPETITION | kosong | nilai kosong (tak terdeteksi) | ya |
| 2954707_219642_skp | wrong | (kosong) | Competition of Design | kosong | nilai kosong (tak terdeteksi) | ya |
| 2954933_219642_skp | wrong | (kosong) | Kompetisi Infografis Statistika ANAVA #20 | kosong | nilai kosong (tak terdeteksi) | ya |
| 2955331_219642_skp | wrong | (kosong) | Give Yourself A Break: The Power Of Self Compassion | kosong | nilai kosong (tak terdeteksi) | ya |
| ACTION_Muhammad Fazil Irvan Putra_compressed | wrong | (kosong) | Academic Competition of Data Science 2024 | kosong | nilai kosong (tak terdeteksi) | ya |
| ACW_Faiz | wrong | (kosong) | Academic Weeks 2025 | kosong | nilai kosong (tak terdeteksi) | tidak |
| AQEEL_Seminar | wrong | (kosong) | Literasi Digital Nasional: Indonesia Makin Cakap Digital dengan Tema | kosong | nilai kosong (tak terdeteksi) | tidak |
| Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 17 Nov 2023 | wrong | (kosong) | Artificial intelligence: Reality Versus Myths | kosong | nilai kosong (tak terdeteksi) | ya |
| Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 9 Nov 2023 | wrong | (kosong) | Information Security in the Digital Era | kosong | nilai kosong (tak terdeteksi) | ya |
| Ananda Aqeel Fathur Rahman_E - Certificate Agentic AI 17 November 2025 | wrong | (kosong) | Agentic AI - Foundations and Emerging Applications in Software Engineering | kosong | nilai kosong (tak terdeteksi) | ya |
| Ananda Aqeel Fathur Rahman_Guest Lecture 25 October 2024 | wrong | (kosong) | Leveraging AI Intervention for Digital Services | kosong | nilai kosong (tak terdeteksi) | ya |
| Ananda Aqeel Fathur Rahman_Guest Lecture ERP SAP 25 April 2025 | wrong | (kosong) | Introduction ERP SAP Business One | kosong | nilai kosong (tak terdeteksi) | ya |
| Ananda Aqeel Fathur Rahman_Guest Lecture FDM 29 November 2024 | wrong | (kosong) | From Discrete Mathematics to Risk Management Systems: a Practical Approach | kosong | nilai kosong (tak terdeteksi) | ya |
| BINARY_Venedict_peserta | wrong | (kosong) | BINARY 3.0 (Building Freshman Solidarity and Character Development) | kosong | nilai kosong (tak terdeteksi) | tidak |
| E-certificate Ananda Aqeel Fathur Rahman (1) | wrong | (kosong) | Connected and Smart Cities - Towards a Sustainable Future | kosong | nilai kosong (tak terdeteksi) | ya |
| FIT_Faiz | wrong | (kosong) | FIT COMPETITION 2026 | kosong | nilai kosong (tak terdeteksi) | ya |
| Falcon_Faiz | wrong | (kosong) | Falcon Project 14 | kosong | nilai kosong (tak terdeteksi) | ya |
| File sertifikat untuk _VenedictGrinaldyPrasetyo__240103_143733_ORM | wrong | (kosong) | Online Research Management | kosong | nilai kosong (tak terdeteksi) | ya |
| Gelar Rasa_Muhammad Fazil Irvan Putra | wrong | (kosong) | GELAR RASA 2024 | kosong | nilai kosong (tak terdeteksi) | ya |
| Girifest_Faiz | wrong | (kosong) | Event Giri Statistics Fest 2026 Kategori Lomba NISC | kosong | nilai kosong (tak terdeteksi) | ya |
| MLQ - Primarizki Ahmad Hariyono | wrong | (kosong) | Intelligent Expression & Computational Thinking for Research and Application (INTELLECTRA) Tingkat Nasional Tahun 2025 | kosong | nilai kosong (tak terdeteksi) | ya |
| NIC_Faiz | wrong | (kosong) | National Competition of de Estadisticas 4.0 | kosong | nilai kosong (tak terdeteksi) | tidak |
| Piagam HIMA S1-AK 2025-compressed_69 | wrong | (kosong) | Himpunan Mahasiswa S-1 Akuntansi Organisasi Kemahasiswaan (ORMAWA) Fakultas Ekonomi dan Bisnis Universitas Airlangga masa bakti tahun 2025 | kosong | nilai kosong (tak terdeteksi) | ya |
| Poisson.Faiz | wrong | (kosong) | Poisson Statistics Competition 2025 | kosong | nilai kosong (tak terdeteksi) | ya |
| Primarizki Ahmad Hariyono_data slayer 2_lomba | wrong | (kosong) | Data Slayer 2.0 | kosong | nilai kosong (tak terdeteksi) | ya |
| Primarizki Ahmad Hariyono_gammafest_lomba | wrong | (kosong) | GAMMAFEST 2025 | kosong | nilai kosong (tak terdeteksi) | ya |
| Primarizki_kim_unair_2024 | wrong | (kosong) | Kompetisi Ilmiah Mahasiswa (KIM) Universitas Airlangga 2024 | kosong | nilai kosong (tak terdeteksi) | ya |
| Primarizki_panitia_synreaach_2024 | wrong | (kosong) | Dekan Cup FTMM 2024 by SYNREACH FTMM 2024 | kosong | nilai kosong (tak terdeteksi) | ya |
| Rasio_Faiz | wrong | (kosong) | University Infographic Competition RASIO 9.0 | kosong | nilai kosong (tak terdeteksi) | ya |
| SDC Unisba_Faiz | wrong | (kosong) | Statistics Data Challenge 2026 | kosong | nilai kosong (tak terdeteksi) | ya |
| SDC Uniska_Faiz | wrong | (kosong) | Statistics Data Champions | kosong | nilai kosong (tak terdeteksi) | ya |
| SERTIF76 | wrong | (kosong) | Training Meeting Internal Vol. 1 | kosong | nilai kosong (tak terdeteksi) | ya |
| Sertif sinem_vene_magang UKM | wrong | (kosong) | Magang UKM Universitas Airlangga | kosong | nilai kosong (tak terdeteksi) | ya |
| Sertif_sportfes_vene_panitia | wrong | (kosong) | Sport Fest FTMM 2024 | kosong | nilai kosong (tak terdeteksi) | ya |
| Sertifikat Kepengurusan IRIS 2025_Muhammad Fazil Irvan Putra | wrong | (kosong) | Innovative Research of Intelligent System (IRIS) Faculty of Advanced Technology and Multidisciplinary for the period of 2025 | kosong | nilai kosong (tak terdeteksi) | ya |
| Sertifikat_Peserta_Primarizki Ahmad Hariyono_ML | wrong | (kosong) | Sriwijaya Informatics Exhibition 2025 | kosong | nilai kosong (tak terdeteksi) | ya |
| UNITY_Muhammad Fazil Irvan Putra | wrong | (kosong) | UNY National Information Technology Competition (UNITY) #14 Tahun 2026 | kosong | nilai kosong (tak terdeteksi) | ya |
| Venedict G. P_peserta talkshow | wrong | (kosong) | Health Buddies: From Insecure to Unstoppable | kosong | nilai kosong (tak terdeteksi) | ya |
| hakim_lomba | wrong | (kosong) | GRADIANT 2.0 | kosong | nilai kosong (tak terdeteksi) | ya |
| primarizki_panitia_binary_2024 | wrong | (kosong) | BINARY 4.0 (Building Freshman Solidarity and Character Development) | kosong | nilai kosong (tak terdeteksi) | ya |
| Primarizki_hima | fuzzy | Himpunan Mahasiswa Teknologi Sains Data Fakultas Teknologi Maju Dan Multidisiplin Universitas Airlangga | Kepengurusan Himpunan Mahasiswa Teknologi Sains Data Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga masa bakti tahun 2025 | kurang_lengkap | extracted 'Himpunan Mahasiswa Teknologi Sains Data Fakultas Teknologi Maju Dan Multidisiplin Universitas Airlangga' < GT 'Kepengurusan Himpunan Mahasiswa Teknologi Sains Data Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga masa bakti tahun 2025' (prefix/suffix/tahun hilang) | ya |
| Sertif_ppkmb_univ_peserta | fuzzy | PENGENALAN KEHIDUPAN KAMPUS BAGI MAHASISWA BARU (PKKMB) | Pengenalan Kehidupan Kampus bagi Mahasiswa Baru (PKKMB) Universitas Airlangga | kurang_lengkap | extracted 'PENGENALAN KEHIDUPAN KAMPUS BAGI MAHASISWA BARU (PKKMB)' < GT 'Pengenalan Kehidupan Kampus bagi Mahasiswa Baru (PKKMB) Universitas Airlangga' (prefix/suffix/tahun hilang) | ya |
| Venedict_panitia_specta | fuzzy | SPECTA | SPECTA 2024 | kurang_lengkap | extracted 'SPECTA' < GT 'SPECTA 2024' (prefix/suffix/tahun hilang) | ya |
| 1963507_219642_skp | wrong | Mawacana | Webinar mengenai Global Warming | salah_kegiatan | extracted 'Mawacana' != GT 'Webinar mengenai Global Warming' (false positive/org lain) | ya |
| PRIMARIZKI_panitia_binary_2025 | wrong | Specta | BINARY 5.0 (Building Freshman Solidarity and Character Development) | salah_kegiatan | extracted 'Specta' != GT 'BINARY 5.0 (Building Freshman Solidarity and Character Development)' (false positive/org lain) | ya |
| PsyAcc_Faiz | wrong | Lomba Nasional Psy-accretion 2.o | Psy-Accretation 2.0 | salah_kegiatan | extracted 'Lomba Nasional Psy-accretion 2.o' != GT 'Psy-Accretation 2.0' (false positive/org lain) | tidak |
| VENEDICT_panitia_karsa | wrong | Pengenalan Kehidupan Kampus bagi Mahasiswa Baru (PKKMB) | KARSA FTMM 2024 | salah_kegiatan | extracted 'Pengenalan Kehidupan Kampus bagi Mahasiswa Baru (PKKMB)' != GT 'KARSA FTMM 2024' (false positive/org lain) | ya |

## Implikasi AKT-002

- Dominan `kosong` = masalah DETEKSI, bukan normalisasi (berbeda dari organizer). Perbaikan = perluas pola regex (Indonesia + Inggris) + repair OCR word-merge (pola `_preprocess` organizer_v2: `dalamkegiatan`, `dalamrangkaianacara`).
- `salah_kegiatan` (PKKMB/Specta/Mawacana false positive): keyword hardcode `AIRNOLOGY/KAKIWIMA/SPECTA/BRIEF` terlalu agresif — perlu guard konteks (mis. hanya fire bila tak ada pattern lain yang match).
- `kurang_lengkap`/`kelebihan`: normalisasi ringan (strip junk + enrich prefix).
- `format_ocr`: alias/case normalization — ranah matcher v2.1 (keputusan user).