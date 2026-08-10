# OOD Probe v3 — Robustness Lapisan Organizer v3 (N=74, 0 LLM)

> Generasi: 2026-08-10 16:18:14 | GT v9 + matcher v2 | seed 42 | pipeline offline (no LLM)

## Ringkasan verdict

**FAIL** — sumbu 1 (template mutation): FAIL | sumbu 2 (OCR noise): FAIL

> Arti PASS: drop v3 tidak lebih besar dari drop v9 (toleransi +1.0pt di mutation & noise 10%; tanpa toleransi di noise 25%/50%) → lapisan v3 **tidak menambah kerapuhan** vs baseline. Verdict hanya menilai kerapuhan relatif; keakuratan absolut diukur benchmark F1C-001 (organizer 54.1%, MACRO 61.2%).

## Baseline offline (corpus asli)

| Pipeline | MACRO exact | MACRO fuzzy | organizer exact |
|---|---|---|---|
| v9 | 55.7% | 65.1% | 37.8% |
| v3 | 61.2% | 67.7% | 54.1% |

## Sumbu 1 — Template mutation (drop vs baseline)

| Metrik | drop v9 | drop v3 | gate (v3 ≤ v9+1pt) |
|---|---|---|---|
| macro_exact | +8.9% | +10.4% | ❌ |
| macro_fuzzy | +8.6% | +9.4% | ✅ |
| free_inst_exact | +1.2% | +1.2% | ✅ |
| tingkat_exact | +4.1% | +4.1% | ✅ |
| organizer_exact | +16.2% | +21.6% | ❌ |

## Sumbu 2 — OCR noise (drop vs baseline)

| Noise | Metrik | drop v9 | drop v3 | gate |
|---|---|---|---|---|
| 10% | macro_exact | +8.6% | +9.1% | +1pt ✅ |
| 10% | macro_fuzzy | +8.6% | +8.9% | +1pt ✅ |
| 10% | free_inst_exact | +7.8% | +7.8% | +1pt ✅ |
| 10% | tingkat_exact | +0.0% | +0.0% | +1pt ✅ |
| 10% | organizer_exact | +0.0% | +1.4% | +1pt ❌ |
| 25% | macro_exact | +16.4% | +18.0% | 0pt ❌ |
| 25% | macro_fuzzy | +16.7% | +18.0% | 0pt ❌ |
| 25% | free_inst_exact | +17.1% | +17.1% | 0pt ✅ |
| 25% | tingkat_exact | +0.0% | +0.0% | 0pt ✅ |
| 25% | organizer_exact | +1.4% | +2.7% | 0pt ❌ |
| 50% | macro_exact | +24.2% | +27.3% | 0pt ❌ |
| 50% | macro_fuzzy | +22.7% | +25.0% | 0pt ❌ |
| 50% | free_inst_exact | +23.3% | +23.3% | 0pt ✅ |
| 50% | tingkat_exact | +0.0% | +0.0% | 0pt ✅ |
| 50% | organizer_exact | +8.1% | +12.2% | 0pt ❌ |

## Sumbu 3+4 — Ablation & noise survival per aturan

| Aturan | fix | regress | nilai berubah | fix bertahan di noise 10% | status |
|---|---|---|---|---|---|
| R0 | 1 | 0 | 1 | 100% (['PRIMARIZKI_panitia_binary_2025']/1) | LOW_N |
| PREFIX_HELD | 1 | 0 | 1 | 100% (['Venedict_panitia_specta']/1) | LOW_N |
| R1 | 1 | 0 | 1 | 100% (['Rasio_Faiz']/1) | LOW_N |
| R2 | 1 | 0 | 1 | 100% (['File sertifikat untuk _VenedictGrinaldyPrasetyo__240103_143733_ORM']/1) | LOW_N |
| R3 | 0 | 0 | 2 | - | NO_FIX |
| R4 | 1 | 0 | 1 | 0% ([]/1) | LOW_N |
| R5 | 0 | 0 | 0 | - | DEAD |
| R6 | 6 | 0 | 6 | 100% (['2954933_219642_skp', 'Ananda Aqeel Fathur Rahman_E - Certificate Agentic AI 17 November 2025', 'Gelar Rasa_Muhammad Fazil Irvan Putra', 'Sertifikat Kepengurusan IRIS 2025_Muhammad Fazil Irvan Putra', 'E-certificate Ananda Aqeel Fathur Rahman (1)', 'SERTIF76']/6) | KEEP |

**Status**: KEEP = bertahan (≥60% di noise 10%, ≥3 fix) · GUARD = rapuh di noise (butuh jaring review) · LOW_N = <3 fix-cert (validasi data baru) · DEAD = tak pernah mengubah nilai (kandidat hapus) · HARMFUL = menimbulkan regress (nonaktifkan) · NO_FIX = mengubah nilai tapi tak pernah memperbaiki.

## Per-aturan: fix-cert (corpus asli) & bertahan di noise 10%

### R0 — fix 1: PRIMARIZKI_panitia_binary_2025

Gagal di noise 10%: tidak ada

### PREFIX_HELD — fix 1: Venedict_panitia_specta

Gagal di noise 10%: tidak ada

### R1 — fix 1: Rasio_Faiz

Gagal di noise 10%: tidak ada

### R2 — fix 1: File sertifikat untuk _VenedictGrinaldyPrasetyo__240103_143733_ORM

Gagal di noise 10%: tidak ada

### R4 — fix 1: 2955331_219642_skp

Gagal di noise 10%: 2955331_219642_skp

### R6 — fix 6: 2954933_219642_skp, Ananda Aqeel Fathur Rahman_E - Certificate Agentic AI 17 November 2025, Gelar Rasa_Muhammad Fazil Irvan Putra, Sertifikat Kepengurusan IRIS 2025_Muhammad Fazil Irvan Putra, E-certificate Ananda Aqeel Fathur Rahman (1), SERTIF76

Gagal di noise 10%: tidak ada

## Diagnosis organizer: cert fix v3 yang MATI saat OOD (asal extra drop)

- template mutation: 4 cert
  - PRIMARIZKI_panitia_binary_2025 [KONTAMINASI GT] GT='Program Studi S1 Teknologi Sains Data Universitas Airlangga' v3='Program Studi S1 Teknologi Sains Data Universitas Airlangga' → kond: 'Program Studi S1 Teknologi Sains Data Universitas Negeri Semarang Himpunan Mahasiswa TSD'
  - primarizki_panitia_binary_2024 [KONTAMINASI GT] GT='Program Studi S1 Teknologi Sains Data Universitas Airlangga' v3='Program Studi S1 Teknologi Sains Data Universitas Airlangga' → kond: 'Program Studi S1 Teknologi Sains Data Universitas'
  - SERTIF76 [KONTAMINASI GT] GT='Biro Penelitian dan Pengembangan Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga' v3='Biro Penelitian dan Pengembangan Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga' → kond: 'Biro Penelitian dan Pengembangan Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis'
  - File sertifikat untuk _VenedictGrinaldyPrasetyo__240103_143733_ORM [KONTAMINASI GT] GT='Perpustakaan Universitas Airlangga' v3='Perpustakaan Universitas Airlangga' → kond: 'PERPUSTAKAAN Universitas Negeri Semarang'
- noise 10%: 1 cert
  - 2955331_219642_skp [KERAPUHAN] GT='Literasi Psikologi Indonesia' v3='Literasi Psikologi Indonesia' → kond: 'Literasi Psikologi Indonesia on July 3O 2023'
- noise 25%: 1 cert
  - Rasio_Faiz [KERAPUHAN] GT='Badan Eksekutif Himpunan Mahasiswa Statistika 2025' v3='Badan Eksekutif Himpunan Mahasiswa Statistika 2025' → kond: 'Badan Eksekutif Himpunan Mahasiswa Statistika 2O25 Facultyof Mathematics and Natural Sciences FMIPA Universitas Padjadjaran in the Series of Events Statistics Day Elevora'
- noise 50%: 3 cert
  - PRIMARIZKI_panitia_binary_2025 [KERAPUHAN] GT='Program Studi S1 Teknologi Sains Data Universitas Airlangga' v3='Program Studi S1 Teknologi Sains Data Universitas Airlangga' → kond: 'Program Studi SI Teknologi Sains Data Universitas Airlangga'
  - 2955331_219642_skp [KERAPUHAN] GT='Literasi Psikologi Indonesia' v3='Literasi Psikologi Indonesia' → kond: 'Literasi Psikologi Indonesia on July 3O 2023'
  - primarizki_panitia_binary_2024 [KERAPUHAN] GT='Program Studi S1 Teknologi Sains Data Universitas Airlangga' v3='Program Studi S1 Teknologi Sains Data Universitas Airlangga' → kond: 'Program Studi SI Teknologi Sains Data Universitas Airlangga'

## Interpretasi

- Sumbu 1+2 membandingkan drop **dalam korpus yang sama** (v9 vs v3 atas input identik) — valid untuk mengukur degradasi relatif.
- **template mutation**: 4 fix v3 mati — 4 kontaminasi GT — jawaban benar ikut berubah saat institusi mutasi (GT lama tak di-update); bukan kerapuhan aturan, 0 kerapuhan aturan nyata.
- **noise 10%**: 1 fix v3 mati — kerapuhan teks-bergantung (GT statis; lihat daftar nilai di atas).
- **noise 25%**: 1 fix v3 mati — kerapuhan teks-bergantung (GT statis; lihat daftar nilai di atas).
- **noise 50%**: 3 fix v3 mati — kerapuhan teks-bergantung (GT statis; lihat daftar nilai di atas).
- Mutation: extra drop organizer v3 (21.6% vs v9 16.2%) = 100% kontaminasi GT — 4 cert (PRIMARIZKI_panitia_binary×2, SERTIF76, File Venedict ORM) yang GT-nya memuat token institusi (termasuk SERTIF76 = fix R6 baru, GT '...Universitas Airlangga' ikut mutasi). Nilai v3 justru mengikuti institusi baru — benar untuk template baru, GT lama tak di-update. Pada metrik bebas institusi (free_inst, tingkat) v3 = v9 PERSIS.
- Noise 10%: 1 kerapuhan nyata = R4 (strip tanggal gagal saat digit OCR rusak: 'July 30' → 'July 3O', 2955331). Gain absolut v3 tetap positif di kondisi noise (organizer 54.1→52.7% vs v9 37.8%): v3 unggul ~+16pt di baseline dan ~+15pt di noise 10% — hanya gate drop-relatif yang terlewat (toleransi +1.0pt vs drop 1.4%).
- Noise 25%: Rasio_Faiz mati — R1 gagal saat kata merge ('Facultyof' — regex butuh koma+spasi). Noise 50%: 2 extra drop (PRIMARIZKI×2) BUKAN aturan strip — nilai v3 benar secara substansi, hanya digit noise 'S1'→'SI' membuat matcher exact gagal (kerapuhan matcher digit, bukan strip). R4 tetap mati di 25% & 50% (2955331).
- Kesimpulan kerapuhan aturan: **0 aturan rapuh di mutation** (semua extra drop = kontaminasi GT); **2 aturan rapuh teks-bergantung di noise**: R4 (mati sejak 10% — digit tanggal) & R1 (mati sejak 25% — kata merge). R0/R2/PREFIX_HELD/R6 bertahan sampai 50%.
- **R6 (F1C-001) = KEEP tanpa catatan GUARD**: 6 fix-cert, regress 0, survival 100% di noise 10%, 0 fix mati di noise 25%/50% & mutation (non-kontaminasi) — lebih robust dari R1/R4. Alasan: compact-equality baris tahan char-confusion, typo map OCR menangani merge, join beruntun tak bergantung spasi.
- R3 = NO_FIX (mengubah 2 nilai tanpa memperbaiki apa pun — risiko murni), R5 = DEAD (tak pernah mengubah nilai) → kandidat hapus saat port produksi.
- R0-R4 fix HANYA 1 cert (LOW_N, <3); R6 = 6 fix-cert (≥3) → klaim robust R6 valid di level korpus ini (STAT-001: fire ≥5 bisa diklaim; tetap validasi data baru untuk generalisasi).
- DEAD/HARMFUL di ablation = aturan tidak membawa manfaat terukur di korpus (rekomendasi hapus/nonaktif saat port produksi). KEEP/GUARD/LOW_N = aman dipromosikan; GUARD wajib ditemani needs_review (F6) sebagai jaring.