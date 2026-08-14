# Handoff v33 — AKT-003 (deteksi nama_kegiatan v3: Sebagai Peserta + atthe/inthe, GATE PASS +13.5pt)

> Supersedes `docs/handoff_v32.md` (plan AKT-003/004). Sesi ini = eksekusi
> AKT-003 (grup A+B+C). Hasil: nama_kegiatan exact **36.5% → 51.4%**
> (27→38/74, +13.5pt dari AKT-002; kumulatif vs produksi +44.6pt), MACRO
> **68.8% → 71.6%** — GATE PASS, 0 regress, 0 LLM, produksi tak disentuh.

---

## Hasil sesi

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. B2 pre-check: 27 cert exact vs pola Peserta/at-the/in-the | 14 cert berisiko → desain prefix `Sebagai` WAJIB (2030372/2065179/gammafest/ML aman); 2954631/IRIS-PF/1930354 punya stop Dalam → skip aman | DONE |
| 2. `tests/benchmark_akt3.py` — repair + anchor grup A/B/C + QA sloppiness + OOD | 1 file tests/ baru, 0 produksi disentuh | DONE |
| 3. Trial iterasi (5x): bug `at(?=[Tt]he)`→"at the" zero-width (hasil "at thethe"); `At` kapital tak kena case-sensitive; `(.+?)` tak bisa stop di posisi 0 (bare Dalam/Pada); newline-stop bikin KIM kurang_lengkap; `(?!Talkshow\|campaign)` negative lookahead | Semua ter-fix via per-cert debug | DONE |
| 4. Run final GT v9 + matcher v2 | nama_kegiatan exact **27→38/74 (51.4%)**, fuzzy 17.6→74.3%, MACRO **68.8→71.6%**, 11 fix baru / 0 regress | **GATE PASS** |
| 5. QA sloppiness (changed non-exact) | 7→5 setelah 2 putaran perbaikan; sisa 5 wajar (ACIC fuzzy, 2954571 partial, ACW/hakim GT-OCR, FIT all-caps) | CLEAN |
| 6. OOD noise (QA): 10/25% | drop ekstra 10% +4.1pt / 25% +9.5pt (naik dari AKT-002 — anchor "Sebagai Peserta" teks-bergantung); gain absolut positif semua level | CATATAN |
| 7. QA | pytest **58 passed**; report_data `akt_003_detection` + generate_report + runs_summary | DONE |

---

## Temuan penting sesi ini

1. **Prefix `Sebagai` WAJIB = kunci anti false-positive OOS.** "Peserta"
   sebagai header/role kata (2030372 "Peserta /A.5/SOCIAL ACTION",
   2065179 "kepada PESERTA Dekan FTMM", gammafest "Peserta No.257...")
   tidak ter-capture — semua 7 target grup A + 2 grup B memang punya
   "Sebagai". Rule OOS-safe: salah arah = MISS (None → fallback), bukan
   FALSE positive.
2. **Jebakan regex zero-width**: `at(?=[Tt]he)` diganti "at the" → hasil
   "at thethe" (lookahead tak konsumsi "the"). Harus diganti "at ".
   Sama: `organized(?=[Bb]y)` → "organized ", bukan "organized by".
3. **Case-sensitive repair vs kapital**: "AttheHology" (A kapital) tak kena
   `at(...)` → gunakan `[Aa]t`; "AT THE" all-caps butuh repair terpisah
   `(?<=\s)[Aa][Tt]\s+THE(?=[A-Z])` (jangan `(?<=[A-Z])THE` — "THEORY"
   terpecah; "THEFIT" didahului spasi).
4. **`(.+?)` vs stop di posisi 0**: `\s+` setelah "Peserta" memakan newline
   → lookahead `\s+Dalam` tak pernah kena di capture-start. Fix: bare
   `Dalam|Pada` di lookahead + `(.*?)` + negative lookahead
   `(?!Talkshow|campaign\b)` untuk kata deskriptor (2398703 "campaign",
   Venedict "Talkshow" → None, bukan junk).
5. **Newline ≠ batas**: KIM "…(KIM)\nUniversitas Airlangga 2024" — stop
   `\n` bikin kurang_lengkap. Ganti jadi newline-BOUNDARY (lanjut bila
   baris berikut bukan kata batas: oleh/tahun/library/surabaya/pada/
   diberikan/direktur/dekan/ketua/nip/tanggal/mengetahui/yang).
   `\s+Universitas(?=[A-Z])` menangkap junk merged "UNIVERSITASAIRLANGGA-
   TAHUNAKADEMIK" (Sertif_ppkmb) tanpa merusak KIM (spasi normal).
6. **Digit-merge repair**: `(?<=\d)oleh/yang/with(?=\s|[A-Za-z])` →
   "Track2oleh"→"Track 2 oleh" (1952296), "2026yangdiselenggarakan"
   (ACW/hakim bersih), "7.0with theme" (Hology). `yang(?=[Dd]iselenggarakan)`
   untuk "yangdiselenggarakan" → stop `\s+yang\s+diselenggarakan` aktif.
7. **OOD noise naik vs AKT-002** (10% +4.1 vs +2.7): anchor "Sebagai
   Peserta" = frasa bahasa alami, lebih rapuh di-noise daripada pola
   struktural. Bila di-port produksi: grup A = GUARD needs_review F6.

---

## Frontier berikutnya (urutan saran)

1. **AKT-004 — grup D+E+F+G** (outline lengkap di handoff v32):
   - D all-caps/spacing: synreaach (DALAMACARA), Gelar Rasa, 2954685
     (DalamrangkaUX), BINARY_Venedict, SDC Unisba (huruf berjarak) —
     risiko tertinggi (ubah _preprocess global), wajib no-regress ketat
   - E: `dalam Event/lomba` — Girifest, SDC Uniska (2 fix)
   - F: `seminar on "X"` — 2954283 (1 fix)
   - G: lanjutan junk — sudah ter-repair parsial di AKT-003 (ACW/hakim bersih)
2. **Port produksi AKT** — keputusan user (pola PROD-002: flag
   `ENABLE_ACTIVITY_V2` default OFF + re-eval + smoke PDF; anchor =
   GUARD needs_review F6 karena noise-rapuh).
3. **GT v10** — fix inkonsistensi: ACW "2026" vs GT "2025", PsyAcc
   "Psy-Accretation", KARSA "(KARs A)" vs "KARSA", FMIPA "dan".
4. **R1/R4 + GUARD F6** — organizer 63.5→66.2%.

### Peta dokumen

- **AKT** → ledger (AKT-001 report-only, AKT-002 PASS, AKT-003 PASS) +
  `docs/report/akt1_activity_taxonomy.md` + `akt2_activity_detection.md` +
  `akt3_activity_detection.md` + report_data (`akt_002_detection`,
  `akt_003_detection`).
- **ORG/PROD** → ledger + report_data → `scripts/generate_report.py`.

## Frontier tertunda (sama v24-v32)

- F4 fingerprint dedup, F5 distillation, F7 infra OCR queue, Eksperimen A
  (LLM per-field), R1/R4 + GUARD F6, HYB-001 OCR hybrid, AKT-004.

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
| `tests/benchmark_akt3.py` | AKT-003 — extractor v3 (grup A+B+C) + QA sloppiness + OOD |
| `docs/report/akt3_activity_detection.md` | Report AKT-003 (fix per cert + changed + OOD) |
| `tests/benchmark_akt2.py` | AKT-002 (v2, tetap — base import AKT-003) |
| `docs/experiments_ledger.md` | AKT-003 PASS + AKT-002 PASS + AKT-001 |
| `docs/handoff_v32.md` | Plan AKT-003/AKT-004 (outline grup D-G masih berlaku) |
