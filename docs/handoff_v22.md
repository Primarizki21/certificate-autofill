# Handoff v22 — OOD probe lapisan v3 (OOD-002) + laporan resmi v10 (report_data.json, sheet Per-Field by Experiment)

> Supersedes `docs/handoff_v21.md`. Sesi ini = jawaban pertanyaan user "apakah
> approach v3 robust/generalize?" (OOD-002) + membawa eksperimen v10 masuk
> laporan resmi docx/xlsx. Keputusan user tetap: produksi = zero-touch, commit
> saja (user yang push), tanpa AI/LLM didahulukan.

---

## Hasil sesi (committed: `59cb038`, `128ac15`, `37a300c`, `a3b2567`, `ce1b590`, `ee570f1`)

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. OOD probe lapisan v3 (`tests/ood_probe_v3.py`, OOD-002) | Mutation: **0 kerapuhan aturan nyata** (extra drop = 100% kontaminasi GT). Noise: R4 rapuh sejak 10% (`July 30`→`July 3O`), R1 sejak 25% (kata merge `Facultyof`); R0/R2/PREFIX_HELD bertahan s.d. 50%. Ablation: R3 = NO_FIX, R5 = DEAD. Semua aturan 1 fix-cert (LOW_N) | FAIL gate drop-relatif; gain absolut v3 tetap positif di semua kondisi |
| 2. Laporan resmi v10 — entri ORG-003 | `report_data.json` experiments[] + entri `org_003_v3` (tingkat 81.1%, MACRO 59.6%, 0 LLM, notes metrologi offline) → `benchmark_methods.docx/.md` + `results_comparison.xlsx` regenerasi | DONE |
| 3. Rerun benchmark v3 + fuzzy | `benchmark_organizer_v3.py` sekarang mencatat fuzzy per-field (per_field_v3: total/exact/fuzzy). Run baru `organizer_v3_20260810_135842` (45.9% GATE PASS konsisten). **6 run dir lama dihapus** → registry runs_summary bersih 1 entri | DONE |
| 4. Sheet Per-Field (level metode) | Kolom baru `v10 organizer v3` (exact+fuzzy) — dibaca **live dari summary_organizer_v3.json**, bukan hardcoded | DONE |
| 5. **Sheet "Per-Field by Experiment"** (level eksperimen) | Baris = 6 field + MACRO, kolom = **16 eksperimen** (urutan sama Results Comparison), 2 tabel exact/fuzzy, label GT di header. **9 non-OCR terisi** (sumber `per_field_src` di report_data.json — v6/v7 dirunut dari run dir lama, v9_reval dari `summary_gt_v9_reval.json`); **OCR × 6 = "n/a" + catatan** (korpus scan 49 cert, tidak sebanding) | DONE |
| 6. Styling sheet Per-Field by Experiment | Header fill `1F3864` center/wrap, ALT_FILL selang-seling, **highlight best per grup GT** (raw / v8 / v9 — opsi B, disetujui user) | DONE |

- Ledger: entri baru **OOD-002**. Report: `ood_probe_v3.md`, `runs_summary.md`
  (ood_probe_v3 + organizer_v3 baru terdaftar). pytest 31 passed.

---

## Temuan penting sesi ini

1. **OOD-002 — jawaban pertanyaan user**: approach v3 **tidak menambah
   kerapuhan saat template baru** (mutation = 0 kerapuhan aturan; nilai v3
   justru mengikuti institusi baru, GT lama tak di-update = artefak). Tapi
   **2 aturan rapuh di OCR noise**: R4 (sejak 10% — digit tanggal rusak) &
   R1 (sejak 25% — kata merge). R3/R5 tanpa manfaat terukur → hapus saat port.
2. **v9_reval_v12 = metrologi, bukan eksperimen baru** — `is_winner` tetap di
   v9_final (makna: diadopsi ke produksi, PROD-001). Angka otoritatif pipeline
   v9 = **60.2%** (GT v9 + matcher v2) — dipakai sebagai baseline evaluasi v10.
3. **`report_data.json` punya `per_field_src`** (path summary json per
   eksperimen, 9 entri) — sumber sheet Per-Field by Experiment. Format 3
   macam: top-level field dict / `fields` dict / `per_field_v3` nested.
4. **`results_comparison.xlsx` TIDAK di-commit** (`*.xlsx` di-ignore) —
   regenerate lokal via `generate_report.py`; user cek visual langsung.

---

## Perbaikan yang direkomendasikan untuk produksi (menunggu keputusan user)

Per-aturan dari OOD-002 (lapisan organizer v3, `benchmark_organizer_v3.py`):
- **KEEP**: R0, R2, PREFIX_HELD — bertahan s.d. noise 50%
- **GUARD** (wajib ditemani needs_review F6 sebagai jaring): R1, R4 — rapuh
  teks-bergantung di noise ≥10–25%
- **HAPUS**: R3, R5 — tanpa manfaat terukur (0 fix, 0 regress)
- Catatan: semua aturan cuma 1 fix-cert (LOW_N) → validasi data baru (cert
  non-UNAIR/FTMM) sebelum klaim robust per-aturan
- Sisa dari v21: bug normalisasi F1 (`_TRAILING_ORG` → `r"\1"`, `_PREFIX_JUNK`
  whitespace), nomor pattern ke-4 + fallback raw (ORG-002, +17.3pt)

Semua = tests-only; port ke produksi butuh keputusan eksplisit user.

---

## Frontier berikutnya (urutan saran) — menunggu keputusan user

1. **Matcher v2.1 / normalisasi alias** — bucket `format` (12 kasus: alias
   UB↔Brawijaya, case/spasi, OCR). Opsi: (a) normalisasi pipeline-side lanjut,
   (b) matcher v2.1 dengan re-baseline evaluasi. **Butuh keputusan user.**
2. **F1 selanjutnya: `kurang_lengkap` enrich** (9 kasus: enrich fakultas/prodi
   dari konteks teks, mis. `Himasada` → `Himasada, Fakultas Ilmu Komputer`) —
   0 LLM, target organizer +~12pt. **Siap eksekusi tanpa keputusan baru.**
3. **Port produksi v3** — per-aturan KEEP/GUARD/hapus (di atas). **Butuh
   keputusan user** (produksi zero-touch).
4. **F3 lanjutan** — sampling data riil unique organizer lintas fakultas
   (validasi asumsi 1.000–10.000 unik). **Butuh data baru dari user.**
5. **Eksperimen A (LLM per-field)**: TIDAK dijalankan — F1 v3 PASS gate
   (handoff v20: hanya jika F1 gagal).

## Frontier tertunda (sama dengan v21)

- F4 fingerprint dedup (butuh KB stabil), F5 distillation (butuh volume F3),
  F7 infra OCR queue (menyentuh produksi, keputusan user), promosi produksi TIDAK.

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Jangan sentuh `backend/` tanpa keputusan user (eksperimen tetap di `tests/`)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..006, LLM-001..003, ROUTER-001, NC-001/002
- Pytest: `uv run python -m pytest tests/ -q` (31 passed) — `pytest` langsung
  gagal spawn/module di env ini, pakai `python -m pytest`
- `results_comparison.xlsx` tidak di-commit — kalau perlu versi terbaru,
  jalankan `uv run python scripts/generate_report.py` lokal

## Key Files

| File | Peran |
|---|---|
| `tests/ood_probe_v3.py` | OOD probe lapisan v3 (mutation/noise + ablation + noise survival) |
| `tests/benchmark_organizer_v3.py` | F1 v3 (R0–R5, `enabled` param utk ablation) + fuzzy per-field |
| `tests/ood_probe.py` | OOD probe v9 (dipakai v3: `eval_corpus(fn=)` param baru) |
| `docs/report/report_data.json` | Sumber laporan resmi: experiments[] + `per_field_src` (9 eksperimen) + blocks dokumen |
| `scripts/generate_report.py` | Regenerate docx/md/xlsx — xlsx 7 sheet, termasuk **Per-Field by Experiment** (styling + highlight best per grup GT) |
| `docs/report/ood_probe_v3.md` | Report OOD-002 (verdict FAIL gate, rekomendasi per-aturan) |
| `docs/report/runs_summary.md` | Registry (ood_probe_v3 + organizer_v3_20260810_135842 terdaftar) |
| `docs/experiments_ledger.md` | OOD-002 tercatat (di samping F1B-001, ORG-003, F3-001) |
