# Handoff v32 — Rencana AKT-003 + AKT-004 (deteksi nama_kegiatan lanjutan, pra-produksi)

> Supersedes `docs/handoff_v31.md`. Sesi ini = **handoff PLAN**: AKT-002 sudah
> PASS (v31); dokumen ini menjabarkan rencana detail eksperimen AKT-003
> (eksekusi berikutnya) + outline AKT-004, sebelum rangkaian AKT disahkan ke
> produksi. Keputusan user: **pecah** — AKT-003 = grup A+B+C (core, tanpa
> all-caps), AKT-004 = grup D+E+F+G (termasuk normalisasi all-caps).

---

## Status (pasca AKT-002, GT v9 + matcher v2, baseline offline_prod)

`nama_kegiatan_sertifikasi` exact **27/74 (36.5%)** — sisa **47 non-exact**:

| Kelas | Jumlah | Keterangan |
|---|---|---|
| wrong (ev=None) | 28 | deteksi gagal total → target utama AKT-003/AKT-004 |
| wrong (ev≠None) | 4 | junk `yangdiselenggarakan` (2) + keyword false-positive (2) |
| fuzzy | 15 | kurang_lengkap 7 · format_ocr 3 · kelebihan 1 · repair OCR 4 |

Dari 28 wrong-None: **~22 cert GT MUNCUL di teks** dengan anchor yang bisa
ditangkap regex; 5 cert in_text=TIDAK (Enchantax 2954571, AQEEL_Seminar,
NIC_Faiz, BINARY_Venedict?, PsyAcc GT typo, VENEDICT_karsa GT KARSA) → di luar
scope regex.

---

## Rencana AKT-003 — grup A + B + C (~12 cert, target +8–12pt)

Eksperimen ber-gate, 0 LLM, tests-only (`tests/benchmark_akt2.py` diperluas,
produksi TAK disentuh). Baseline = `offline_prod` (PROD-002).

### Grup A — anchor `(?:[Ss]ebagai\s*:?\s*)?Peserta\s+(.+?)` (7 cert)

| cert | GT | fragment teks | stop lookahead | expected |
|---|---|---|---|---|
| `1952296_219642_skp` | Public Health Career Track 2 | `Sebagai PESERTA PublicHealthCareerTrack2olehDivisi` | `oleh` | **exact** (camel-split + digit-split repair sudah ada) |
| `2030335_219642_skp` | Public Health Career Track 3 | `Sebagai Peserta Public Health Career Track 3 oleh Divisi` | `oleh` | **exact** |
| `2398697_219642_skp` | Airlangga Job Preparation 2023 | `SebagaiPeserta AirlanggaJobPreparation2023 olehBadan` | `oleh` | **exact** (butuh repair `Peserta(?=[A-Z])`) |
| `2030325_219642_skp` | Magang UKM Universitas Airlangga | `sebagai : Peserta Magang UKM Universitas Airlangga Tahun Akademik` | `Tahun Akademik` | **exact** (wajib `\s*:?\s*` — ada colon) |
| `Sertif sinem_vene_magang UKM` | Magang UKM Universitas Airlangga | sama pola | `Tahun Akademik` | **exact** |
| `2071996_221065_skp` | Magang UKM Universitas Airlangga | sama pola | `Tahun Akademik` | **exact** |
| `Primarizki_kim_unair_2024` | Kompetisi Ilmiah Mahasiswa (KIM) Universitas Airlangga 2024 | `Peserta Kompetisi Ilmiah Mahasiswa (KIM) Universitas Airlangga 2024` | `\n`/`Surabaya` | **exact** |

**Risiko grup A (wajib stop tambahan)**: `Peserta Dalam...` (2954685, BINARY)
→ capture junk "DalamrangkaUXDESIGN...". Tambah `Dalam` ke lookahead stop agar
skip → jatuh ke anchor berikutnya. Prioritas: anchor kutip (B) SEBELUM A.

### Grup B — anchor `(?:[Ss]ebagai\s*:?\s*)?Peserta\s*["“]([^"”]+)["”]` (2 cert)

| cert | GT | fragment | expected |
|---|---|---|---|
| `File sertifikat untuk _VenedictGrinaldyPrasetyo__240103_143733_ORM` | Online Research Management | `PESERTA "Online Research Management" Library Class` | **exact** |
| `2160238_221065_skp` | Airlangga Career & Internship Club [ACIC] SPEAK UP & STAND OUT: MENGASAH... | `Sebagai Peserta "Airlangga Career & Internship Club" [ACIC] SPEAKUP &STANDOUT...` | **fuzzy** (kutip hanya ambil awalan; seluruh GT = kutip + sisa `[ACIC] SPEAK UP & STAND OUT: ...` yang butuh repair all-caps → jangan janji exact) |

### Grup C — repair `at(?=[Tt]he)` → "at the", `in(?=[Tt]he)` → "in the" (3 cert)

| cert | GT | fragment | expected |
|---|---|---|---|
| `2439919_221065_skp` | Hology 7.0 | `AttheHology7.0with theme` | **exact** (anchor 15 `at the` + digit-split) |
| `Poisson.Faiz` | Poisson Statistics Competition 2025 | `inthePoissonStatisticsCompetition2025 organizedby` | **exact** (camel-split) |
| `FIT_Faiz` | FIT COMPETITION 2026 | `AT THEFITCOMPETITION2026 "Digital lmpact...` | **fuzzy** ("FITCOMPETITION" all-caps tidak ter-split — butuh aturan acronym `(?<=[A-Z])(?=[A-Z][a-z])` yang rawan, jangan masuk AKT-003) |

### Perubahan kode (rinci)

1. **Anchor baru** (masuk `_ANCHORS`, perhatikan urutan prioritas):
   - `(?:[Ss]ebagai\s*:?\s*)?Peserta\s*["“]([^"”]+)["”]` — SEBELUM anchor Peserta polos
   - `(?:[Ss]ebagai\s*:?\s*)?Peserta\s+(.+?)(?=oleh|Tahun\s+Akademik|Library|Surabaya|Dalam|Pada|\n|$)`
2. **Repair baru** (`_REPAIR`): `at(?=[Tt]he)`→"at the", `in(?=[Tt]he)`→"in the",
   `(?<=[a-z])Peserta(?=[A-Z])`→"Peserta " (split "SebagaiPeserta").
   **Jangan IGNORECASE global** (jebakan v31: rusak camel-split `(?<=[a-z])(?=[A-Z])`).
3. **STOP**: lookahead grup A sudah menyertakan `oleh` (tidak di-`_STOP` global
   — perubahan di anchor, bukan global, supaya blast radius kecil).

### Gate & QA (mirror AKT-002)

- Gate: nama_kegiatan exact **≥ +5pt**, **no-regress** (jaga 5 cert exact
  baseline: sertif_colab_vene_panitia, SSF_Faiz, Hitech_Faiz, IRIS PF 2026,
  2954421 + 22 fix AKT-002), **0 LLM**, GT v9 + matcher v2.
- QA: `pytest tests/` (58 expected), OOD noise 10/25% (QA, bukan gate —
  laporkan drop ekstra jujur), audit diff (1 file tests/ saja).
- Alur B0–B11; PASS → ledger AKT-003 + report_data `akt_003_detection` +
  `generate_report.py` + runs_summary + update handoff → commit (user push).

---

## Rencana AKT-004 — grup D + E + F + G (outline, ~10 cert)

Eksekusi setelah AKT-003 PASS (atau FAIL — ledger dulu). Target ~5–7 exact.

| Grup | cert | pola | risiko |
|---|---|---|---|
| D. all-caps/spacing | `Primarizki_panitia_synreaach_2024` (Dekan Cup...), `Gelar Rasa` (GELAR RASA 2024), `2954685` (UX DESIGN, `DalamrangkaUX`), `BINARY_Venedict_peserta` (`DalamrangkaianacaraBlNARY2o23`), `SDC Unisba_Faiz` (huruf berjarak `D a l a m a c a r a`) | normalisasi token ALL-CAPS + collapse spasi antar huruf di `_preprocess` | **tertinggi** — ubah perilaku cert lain, wajib no-regress ketat; BINARY pakai "BINARY 3.0" literal di teks |
| E. `dalam Event/lomba` | `Girifest_Faiz` (`dalam Event Giri Statistics Fest 2026 kategori`), `SDC Uniska_Faiz` (`Dalam lomba tingkat Nasional "Statistic Data Champions"`) | anchor `dalam\s+(?:Event|lomba\s+tingkat\s+Nasional)?\s*["“]?` | rendah |
| F. `seminar on "X"` | `2954283_219642_skp` (`seminar on "The AI Revolution..."`) | anchor `seminar\s+on\s*["“]` | rendah |
| G. junk `yangdiselenggarakan` | `ACW_Faiz` (`Academic Weeks 2026yangdiselenggarakan` — CEK teks: 2025 vs 2026, kalau teks 2026 → GT v10), `hakim_lomba` (`GRADl ANT 2.0yangdiselenggarakanoleh`) | repair `yang(?=[Dd]iselenggarakan)`→"yang " (spesifik, bukan `yang(?=[a-z])` generik) | rendah |

---

## Defer permanen (bukan AKT)

- **format_ocr/case** (VENEDICT_sertif_bem "Dan"↔"dan", Ananda "Al"↔"AI") →
  **matcher v2.1** (keputusan user, ranah evaluator).
- **kurang_lengkap subtitle/tahun** (MLQ, AgenticAI, 2955331, FDM, SPECTA,
  ACIC) → enrich berisiko rendah-nilai, tunda sampai matcher v2.1.
- **in_text=TIDAK (5)** → LLM per-field / OCR baru / GT v10 (Enchantax,
  AQEEL, NIC, PsyAcc, KARSA; BINARY verifikasi ulang — "BINARY 3.0" ADA di
  teks, taksonomi AKT-001 salah klasifikasi).
- **GT typo** (PsyAcc "Psy-Accretation") → GT v10.

---

## Frontier sesudah rangkaian AKT

1. **Port produksi AKT** — keputusan user (pola PROD-002: flag
   `ENABLE_ACTIVITY_V2` default OFF + re-eval + smoke PDF; anchor = GUARD
   needs_review F6 karena noise-rapuh).
2. **GT v10** — fix inkonsistensi GT v9 (FMIPA "dan", HIMA pendek/panjang,
   ACW 2025/2026).
3. **R1/R4 + GUARD F6** — organizer 63.5→66.2%.
4. **Scoring organizer_v2** — data >74 (ORG-005 FAIL). **KB** TUTUP (v27).

### Peta dokumen

- **AKT** → ledger (AKT-001 report-only, AKT-002 PASS) + `docs/report/
  akt1_activity_taxonomy.md` + `docs/report/akt2_activity_detection.md` +
  report_data (`akt_002_detection`). AKT-003/004 → follow-up entri sama.
- **ORG/PROD** → ledger + report_data → `scripts/generate_report.py`.

## Frontier tertunda (sama v24-v31)

- F4 fingerprint dedup, F5 distillation, F7 infra OCR queue, Eksperimen A
  (LLM per-field), R1/R4 + GUARD F6, HYB-001 OCR hybrid.

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Eksperimen tetap di `tests/` (produksi: PROD-002 flag default OFF)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..006, LLM-001..003, ROUTER-001, NC-001/002, ORG-005
- Pytest: `uv run python -m pytest tests/ -q` (58 passed)
- `results_comparison.xlsx` tidak di-commit — regenerate lokal bila perlu

## Key Files

| File | Peran |
|---|---|
| `tests/benchmark_akt2.py` | AKT-002 PASS + target edit AKT-003 (grup A+B+C) |
| `docs/report/akt2_activity_detection.md` | Report AKT-002 (fix per cert + OOD noise) |
| `docs/experiments_ledger.md` | AKT-002 PASS; AKT-003/004 mengikuti |
| `tests/akt1_activity_taxonomy.py` | AKT-001 (v30) — taksonomi nama_kegiatan |
| `backend/app/services/organizer_normalize.py` | PROD-002 (v29) — produksi, flag OFF |
