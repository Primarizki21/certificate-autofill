# Handoff v34 — AKT-004 (grup E+F+G, GATE PASS +2 exact, gate scope-kecil)

> Supersedes `docs/handoff_v33.md`. Sesi ini = eksekusi AKT-004 (grup E+F+G,
> bagian "aman" dari sisa deteksi nama_kegiatan). Hasil: nama_kegiatan exact
> **51.4% → 54.1%** (38→40/74, +2 exact — gate scope-kecil ≥+2 exact),
> MACRO **71.6% → 72.1%** — GATE PASS, 0 regress, 0 LLM, produksi tak disentuh.

---

## Hasil sesi

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. B3: `tests/benchmark_akt4.py` — 3 anchor (dalam Event / lomba tingkat Nasional / seminar on) + repair OCR-alias NisC + gate scope-kecil `>=+2 exact` | 1 file tests/ baru, 0 produksi disentuh | DONE |
| 2. Trial iterasi (2x): bug import `_REPAIR3`; Girifest fuzzy karena camel-split pecah "NisC"→"Nis C" → repair `Nis\s+C\b`→"NISC" | Ter-fix | DONE |
| 3. Run final GT v9 + matcher v2 | nama_kegiatan exact **38→40/74 (54.1%)**, MACRO **71.6→72.1%**, +2 fix / 0 regress | **GATE PASS** |
| 4. QA sloppiness | changed non-exact 1 (SDC Uniska 'Statistic Data Champions' — plausible, GT mismatch) | CLEAN |
| 5. OOD noise (QA): 10/25% | drop ekstra 10% +4.1pt / 25% +9.5pt — TIDAK naik vs AKT-003 (anchor E/F fire sedikit) | CATATAN |
| 6. QA | pytest **58 passed**; report_data `akt_004_detection` + generate_report + runs_summary | DONE |

---

## Temuan penting sesi ini

1. **Gate scope-kecil bekerja**: 2-3 cert sasaran = +2 exact (~+2.7pt) < gate
   standar +5pt. Gate `>=+2 exact` ditetapkan eksplisit (keputusan user,
   handoff v33) dan tercatat di report md + ledger — bukan menurunkan standar
   diam-diam, tapi skala eksperimen yang sengaja kecil.
2. **camel-split punya efek samping pada akronim OCR**: "NisC" (OCR NISC,
   Girifest) terpecah "Nis C" → tidak cocok GT "NISC". Repair OCR-alias
   TARGETED pasca-camel-split (`Nis\s+C\b`→"NISC") — jangan repair generic
   (risiko memecah kata lain).
3. **SDC Uniska = beda teks vs GT**: cert tulis "Statistic Data Champions",
   GT tulis "Statistics Data Champions" — bukan bug kode, **kandidat GT v10**
   (satu char "s"). Diputuskan TERIMA sebagai WRONG, tercatat.
4. **Anchor `seminar on "X"` dan `dalam Event X`** tidak menambah OOD drop
   (fire hanya 2-3 cert) — beda dari grup A AKT-003 (anchor bahasa alami
   frekuen tinggi).

---

## Frontier berikutnya (urutan saran)

1. **AKT-005 — grup D (risiko tertinggi, terakhir untuk field ini)**:
   - synreaach `DALAMACARADEKANCUPFTMM2024BYSYNREACHFTMM2024` (keyword all-caps
     split), Gelar Rasa `DALAMACARAGELARRASA2024`, 2954685
     `DalamrangkaUXDESIGNcoMPETITIoN...` (campuran, camel-split bantu),
     BINARY_Venedict ("BINARY 3.0" literal di teks), SDC Unisba (huruf
     berjarak `D a l a m a c a r a ...` → collapse), bonus ACIC fuzzy→exact
     (split all-caps "SPEAKUP/KOMUNIKASIDIERAKARIRDIGITAL").
   - Mitigasi: repair keyword-specific (bukan aturan generic all-caps), no-
     regress ketat 40 cert exact AKT-004, pecah per-cert bila melenceng.
   - Gate: ≥+5pt, no-regress, 0 LLM.
2. **Port produksi AKT** — keputusan user (pola PROD-002: flag
   `ENABLE_ACTIVITY_V2` default OFF + re-eval + smoke PDF; anchor = GUARD
   needs_review F6 karena noise-rapuh).
3. **GT v10** — fix inkonsistensi terkumpul: ACW "2026" vs GT "2025",
   SDC Uniska "Statistic" vs "Statistics", PsyAcc "Psy-Accretation",
   KARSA "(KARs A)" vs "KARSA", FMIPA "dan".
4. **R1/R4 + GUARD F6** — organizer 63.5→66.2%.

### Peta dokumen

- **AKT** → ledger (AKT-001 report-only, AKT-002/003/004 PASS) +
  `docs/report/akt{1,2,3,4}_*.md` + report_data (`akt_002..004_detection`).
- **ORG/PROD** → ledger + report_data → `scripts/generate_report.py`.

## Frontier tertunda (sama v24-v33)

- F4 fingerprint dedup, F5 distillation, F7 infra OCR queue, Eksperimen A
  (LLM per-field), R1/R4 + GUARD F6, HYB-001 OCR hybrid, AKT-005.

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Eksperimen tetap di `tests/` (produksi: PROD-002 flag default OFF)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..007, LLM-001..003, ROUTER-001, NC-001/002, ORG-005
- Pytest: `uv run python -m pytest tests/ -q` (58 passed)
- `results_comparison.xlsx` tidak di-commit — regenerate lokal bila perlu

## Key Files

| File | Peran |
|---|---|
| `tests/benchmark_akt4.py` | AKT-004 — extractor v4 (grup E+F+G) + gate scope-kecil |
| `docs/report/akt4_activity_detection.md` | Report AKT-004 (fix per cert + changed + OOD) |
| `tests/benchmark_akt3.py` | AKT-003 (v3, tetap — base import AKT-004) |
| `docs/experiments_ledger.md` | AKT-002/003/004 PASS + AKT-001 |
| `docs/handoff_v33.md` | Hasil AKT-003 (v33) — konteks OOD naik |
