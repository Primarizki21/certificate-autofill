# Handoff v35 — AKT-005 (grup D all-caps/spacing, GATE PASS +6 exact) — RANGKAIAN AKT SELESAI

> Supersedes `docs/handoff_v34.md`. Sesi ini = eksekusi AKT-005 (grup D —
> terakhir untuk field nama_kegiatan). Hasil: nama_kegiatan exact
> **54.1% → 62.2%** (40→46/74, +6 exact), MACRO **72.1% → 73.7%** — GATE PASS,
> 0 regress, 0 LLM, **produksi tak disentuh (keputusan user: tetap eksperimen)**.

---

## Hasil sesi

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. B2 audit: run huruf-berjarak di seluruh korpus | Hanya 3 cert (SDC Unisba target, Hitech/ACTION = header benign) — collapse aman | DONE |
| 2. `tests/benchmark_akt5.py` — pre-camel repairs (collapse + keyword all-caps + UXDESIGN/competition/dengan) + post-camel (re-split competition, sentinel Himpunan) + anchor join2 | 1 file tests/ baru, 0 produksi disentuh | DONE |
| 3. Trial iterasi (3x): 2 regress vs AKT-004 tertangkap (competition lowercase bunuh camel-boundary 2954631/Poisson → post-repair re-split); dengan-split konflik lookahead; join2 span newline; sentinel Himpunan | Semua ter-fix | DONE |
| 4. Run final GT v9 + matcher v2 (no-regress vs baseline DAN vs AKT-004) | nama_kegiatan exact **40→46/74 (62.2%)**, MACRO **72.1→73.7%**, +6 fix / 0 regress | **GATE PASS** |
| 5. QA sloppiness | changed non-exact 1 (SDC Uniska, wajar — GT mismatch) | CLEAN |
| 6. OOD noise (QA): 10/25% | drop ekstra 10% +4.1pt / **25% +13.5pt (NAIK)** — grup D paling noise-fragile; gain absolut positif semua level | CATATAN |
| 7. QA | pytest **58 passed**; report_data `akt_005_detection` + generate_report + runs_summary | DONE |

---

## Temuan penting sesi ini

1. **Grup D = paling noise-fragile** (OOD 25% +13.5pt, naik dari +9.5):
   collapse huruf-berjarak & split all-caps = sinyal yang paling mudah rusak
   di-noise. Gain absolut tetap positif semua level (25%: 47.3% vs 5.4%).
   Bila port produksi → grup D harus GUARD needs_review paling ketat.
2. **Repair lowercase bisa membunuh camel-boundary** (regress 2954631/
   Poisson): `(?i)competition` → "competition" mengubah "AcademicCompetition"
   jadi "Academiccompetition" — camel-split tak terpecah lagi. Fix: post-
   repair `(?i)(?<=[a-z])competition(?=\s)` → " competition". Lesson:
   setiap repair yang menurunkan case harus diikuti verifikasi no-regress vs
   versi SEBELUMNYA (bukan cuma vs baseline produksi).
3. **Dua repair "dengan" konflik**: `(?i)(?<=[a-z0-9])dengan(?=[A-Za-z])`
   gagal karena repair pertama sudah menambah spasi (lookahead huruf tak
   pernah kena). Fix: left-split pakai lookahead `\s`.
4. **join2 anchor** (kutip + sisa `[...]`) di ATAS anchor kutip lama:
   ACIC butuh sisa setelah kutip, ORM (tanpa "[") tetap aman ke anchor lama.
   Rest capture harus span newline (raw text pecah baris).
5. **Sentinel `\n` sebelum "Himpunan" digit-bound**: organizer menyela antara
   nama kegiatan dan "dengan tema" (SDC Unisba) — sentinel membuat _STOP `\n`
   memberhentikan capture tepat setelah nama kegiatan. Digit-bound = aman
   (tidak ada cert lain "digit Himpunan" dalam konteks kegiatan).
6. **BINARY_Venedict SKIP (bukan kegagalan)**: OCR "Bl NARY 2o 23" vs GT
   "BINARY 3.0" — angka beda (2023 vs 3.0) = kandidat GT v10/konvensi,
   bukan fix regex aman.

---

## STATUS: Rangkaian AKT SELESAI

| Eksperimen | Scope | exact nama_kegiatan |
|---|---|---|
| AKT-001 (v30) | taksonomi (report-only) | 5/74 (6.8%) |
| AKT-002 (v31) | 16 anchor + repair merge | → 27/74 (36.5%) |
| AKT-003 (v33) | Sebagai Peserta + atthe/inthe | → 38/74 (51.4%) |
| AKT-004 (v34) | Event/lomba/seminar on (gate kecil) | → 40/74 (54.1%) |
| AKT-005 (v35) | all-caps + huruf berjarak | → **46/74 (62.2%)** |

Kumulatif: **6.8% → 62.2%** (+55.4pt), 41 fix, 0 LLM. **TIDAK di-port
produksi** (keputusan user — tetap eksperimen). Sisa 28 wrong = OCR/noise
inherent (BINARY 2o23, hakim GRADl ANT, FIT all-caps) + GT v10 candidates
(ACW 2025/2026, SDC Uniska Statistic/Statistics, PsyAcc) + in_text=tidak
(Enchantax, AQEEL, NIC).

## Frontier berikutnya (urutan saran)

1. **GT v10** — fix inkonsistensi terkumpul: ACW "2026" vs "2025", SDC
   Uniska "Statistic" vs "Statistics", PsyAcc, KARSA "(KARs A)", FMIPA "dan",
   BINARY "2o23" vs "3.0".
2. **Port produksi AKT** — KEPUTUSAN USER (saat ini: TIDAK). Pola PROD-002:
   flag `ENABLE_ACTIVITY_V2` default OFF + re-eval + smoke PDF. Anchor =
   GUARD needs_review F6; grup D = guard paling ketat (noise-fragile).
3. **R1/R4 + GUARD F6** — organizer 63.5→66.2%.
4. **OCR baru** — sisa yang regex mentok (BINARY/hakim/FIT) butuh OCR lebih
   baik, bukan regex.

### Peta dokumen

- **AKT** → ledger (001 report-only, 002/003/004/005 PASS) + `docs/report/
  akt{1,2,3,4,5}_*.md` + report_data (`akt_002..005_detection`).
- **ORG/PROD** → ledger + report_data → `scripts/generate_report.py`.

## Frontier tertunda (sama v24-v34)

- F4 fingerprint dedup, F5 distillation, F7 infra OCR queue, Eksperimen A
  (LLM per-field), R1/R4 + GUARD F6, HYB-001 OCR hybrid, GT v10.

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Eksperimen tetap di `tests/` (produksi: PROD-002 flag default OFF; AKT tidak di-port)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..007, LLM-001..003, ROUTER-001, NC-001/002, ORG-005
- Pytest: `uv run python -m pytest tests/ -q` (58 passed)
- `results_comparison.xlsx` tidak di-commit — regenerate lokal bila perlu

## Key Files

| File | Peran |
|---|---|
| `tests/benchmark_akt5.py` | AKT-005 — extractor v5 (grup D) + QA + OOD |
| `docs/report/akt5_activity_detection.md` | Report AKT-005 (fix per cert + changed + OOD) |
| `tests/benchmark_akt4.py` | AKT-004 (v4) — base import AKT-005 |
| `docs/experiments_ledger.md` | AKT-002..005 PASS + AKT-001 |
| `docs/handoff_v34.md` | Hasil AKT-004 (v34) |
