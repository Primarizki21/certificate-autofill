# Handoff v18 — Mentor artifacts + Frontier: eksperimen adaptif A/B/C (fallback LLM per-field, rule mining, OOD probe)

> Supersedes `docs/handoff_v17.md`. Sesi ini:
> - **Artefak presentasi mentor** dibangun & di-commit: `results_comparison.xlsx`
>   (styled, direction-aware delta), `raw_vs_pipeline.xlsx` (74 cert: teks mentah
>   vs field pipeline vs GT), `raw_vs_pipeline_examples.docx` (5 contoh terkurasi),
>   `mentor_presentation_notes.md` (jawaban kuantitatif "LLM vs router" +
>   robustness). Commit `4b7e029`.
> - **pipeline_best** dilengkapi section "Metode Penentuan Field (sentence →
>   field)" + status NER eksplisit (NER TIDAK dipakai: v1 = 12.8% FAIL closed,
>   hybrid superseded; semua field = regex + rule-based, LLM hanya fallback
>   tingkat). Commit `9599c9d`.
> - **Temuan kunci untuk frontier**: v9 hampir seluruhnya regex/rule-based yang
>   DITURUNKAN dari 74 sertifikat korpus (bukti: `OCR_ORG_MAP` berisi typo
>   korpus `UNIVERSITASAIRLANCCA`, `_UNAIR_BEMS` 8 kampus UNAIR saja, keyword
>   event AIRNOLOGY/KAKIWIMA/SPECTA/BRIEF di-hardcode, daftar "luar" router =
>   universitas yang muncul di korpus). LLM full-text (A2 v2) justru MENANG di
>   field yang rule-nya rapuh (nama_kegiatan 43.2 vs 25.7, tanggal 94.5 vs 81.8,
>   nomor 73.1 vs 59.6) — jalur adaptif sudah terukur, tinggal dipakai selektif.
> - **Frontier eksperimen adaptif** (3 opsi, urutan C → A → B) — detail lengkap
>   di bawah, siap dieksekusi sesi berikutnya. Semua di `tests/`, produksi TIDAK
>   disentuh tanpa keputusan user.

---

## Mentor artifacts (selesai & di-commit)

| Artifact | Isi | Source data |
|---|---|---|
| `docs/report/results_comparison.xlsx` | 6 sheets: Results Comparison (15 eksperimen + delta arah warna), Progression, Per-Field, OCR Line, v8 Variants, Per-File tingkat | `report_data.json` (auto) |
| `docs/report/raw_vs_pipeline.xlsx` | 74 sertifikat: teks mentah + field pipeline vs GT, EXACT=hijau/FUZZY=kuning/WRONG=merah | `extracted_texts/` + run v9 + GT v9 (matcher v2) |
| `docs/report/raw_vs_pipeline_examples.docx` | 5 contoh terkurasi + annotasi tahap pipeline (router, LLM fallback, organizer, OCR gagal, field gagal) | sama |
| `docs/report/mentor_presentation_notes.md` | Jawaban kuantitatif "LLM vs router" + robustness + artefak | angka otoritatif |

Regenerate (idempotent):
```bash
uv run python scripts/generate_report.py           # results_comparison.xlsx
uv run python scripts/generate_raw_vs_pipeline.py  # raw_vs_pipeline.xlsx + examples.docx
```

Jawaban kunci "LLM atau router?" (dipakai mentor): **didominasi rule-based**.
Router putuskan 45/74 @100% precision (72.6% dari semua keputusan tingkat benar,
tanpa token); LLM hanya fallback 29/74 (58.6% akurasi pada kasus ambigu).
Bukti: akurasi naik sementara LLM dipakai LEBIH SEDIKIT (calls 39→29, tok
214→176, MACRO 54.2→60.2).

---

## Frontier — Eksperimen adaptif (urutan: C → A → B)

Motivasi: v9 rule-based hardcode korpus → break di luar 74 sertifikat UNAIR.
Tiga jalur untuk robust/adaptif. Semua = eksperimen `tests/` (B-workflow:
codegraph → edit → trial → GATE CHECK → pytest → ledger → report).

### C — OOD probe (kerjakan PALING DULU, report-only, ~1 jam)

**Hipotesis:** penurunan akurasi terukur saat input keluar domain (template
baru / OCR noise) — ini bukti empiris "seberapa break" untuk mentor + validasi
urgensi A/B.

**File baru:** `tests/ood_probe.py` (measurement-only, NO gate akurasi)

2 sumbu degradasi pada korpus asli (GT v9 + matcher v2, re-eval offline):
1. **Template mutation**: ganti `Universitas Airlangga`→`Universitas Negeri
   Semarang`, event hardcode (Airnology→nama lain), fakultas lain → ukur MACRO
   drop vs baseline v9 (60.2%).
2. **OCR noise injeksi**: confusion table dari MONTH_ALIASES nyata (5↔S, 8↔B,
   0↔O, merge kata) pada level 0/10/25/50% karakter → kurva MACRO vs noise.

**Output:** `docs/report/ood_probe.md` (angka + kurva) + ledger entry OOD-001.

**GATE:** report-only — tidak ada gate akurasi, hanya angka jujur.

### A — Fallback LLM per-field (nama_kegiatan, penyelenggara) (~2-3 jam)

**Hipotesis:** regex gagal di 2 field ini karena template-hardcode; LLM dengan
konteks terminimalkan bisa menutup gap, seperti pola tingkat-router yang sudah
terbukti (Exp5-001 FAIL sebelumnya karena token; di sini field BEDA + HANYA
saat regex gagal → cost jauh lebih kecil).

**File baru:** `tests/benchmark_field_fallback.py`

Alur: `extract_certificate_fields` → jika `nama_kegiatan` None / confidence
< 0.5 (dan `penyelenggara` None) → panggil LLM llama3.1:8b dengan teks
terminimalkan (reuse `minimize_text`/`score_line` dari
`backend/app/services/llm_tingkat.py`), prompt per-field, temperature 0.
Evaluasi matcher v2 vs GT v9, bandingkan vs baseline v9 (nama_kegiatan 25.7%,
penyelenggara 39.2%).

**GATE:** nama_kegiatan exact ≥ 30% (dari 25.7%) · penyelenggara no-regress ·
eff tok ≤ 200/cert · extra LLM calls ≤ 30/74 · tingkat no-regress.

**Perhatian:** EXP5-001 di ledger = multi-field dalam SATU call (token FAIL).
Jangan ulang — fallback per-field ini per-call terpisah & hanya cert miss.

### B — Rule mining dari data (hapus hardcode korpus) (~1-2 jam)

**Hipotesis:** `OCR_ORG_MAP`/`_UNAIR_BEMS`/daftar "luar" bisa diturunkan dari
data (token frequency + GT alignment), sehingga korpus baru tidak butuh entri
manual.

**File baru:** `tests/rule_mining.py` (offline; TIDAK mengubah
`organizer_v2.py`/`tingkat_router.py` produksi)

Alur: (1) kumpulkan token org dari raw text 74 cert, (2) align ke GT
penyelenggara → peta akronim/merge (mis. `BEMFTMM`→`BEM FTMM`), (3) daftar
"luar" = universitas non-UNAIR di GT, (4) re-run organizer_v2 + router dengan
peta hasil mining (di benchmark script, bukan produksi). Validasi silang
60/14: peta dari train, evaluasi di test.

**GATE:** organizer exact no-regress (±2pt) · router precision ≥95% ·
0 entri manual untuk korpus yang sama · coverage peta ≥ OCR_ORG_MAP lama.

---

## Pekerjaan USER berjalan (agent JANGAN kerjakan)

- **User sedang memperbaiki `docs/report/pipeline_best.docx` secara manual**
  (styling/isi). Agent: skip, tunggu arahan.
- ⚠️ **Hati-hati regenerasi**: `uv run python scripts/generate_pipeline_doc.py`
  MENIMPA pipeline_best.docx dari `pipeline_data.json`. Jangan dijalankan
  selama user masih mengedit docx — atau backup dulu (lihat Jangan Lakukan).

---

## Rencana EKSEKUSI sesi berikutnya (kalau mau lanjut)

1. **Context loading** (WAJIB, urut): `git status` + `git log --oneline -5`
   → handoff TERBARU (v18 ini) → `docs/report/runs_summary.md` →
   `docs/experiments_ledger.md` (closed approaches — JANGAN dilewatkan).
2. **Cek status pipeline_best.docx user** — kalau user masih edit manual,
   jangan regenerate `generate_pipeline_doc.py` (menimpa manual edit).
3. **Eksperimen C (OOD probe)** — `tests/ood_probe.py`, report-only, ~1 jam.
   Output `docs/report/ood_probe.md` + ledger OOD-001. Bukti kerapuhan utk A/B.
4. **Eksperimen A (fallback LLM per-field)** — `tests/benchmark_field_fallback.py`,
   reuse `minimize_text` dari `llm_tingkat.py`, GATE di atas (nama_kegiatan
   ≥30%, tok ≤200/cert, calls ≤30).
5. **Eksperimen B (rule mining)** — `tests/rule_mining.py`, validasi silang
   60/14, GATE (organizer no-regress, router precision ≥95%).
6. **Per eksperimen** ikuti B-workflow: codegraph explore → edit → trial →
   GATE CHECK → `pytest tests/` → audit diff → ledger entry → PASS = update
   report_data + runs_summary + handoff; FAIL = ledger + runs_summary saja.
7. **Commit** kode + docs bersama. **User yang push** (SSH passphrase).

---

## Keputusan yang DIBUTUHKAN USER (open)

1. **`ENABLE_OCR_NUMBER_2PASS`** — default false (rekomendasi) vs true (dari v17).
2. **Eksperimen adaptif A/B/C** — urutan C → A → B disetujui? Gate di atas
   final? (C bisa langsung jalan tanpa LLM.)
3. **Promosi/eksperimen lain dari v17** (NC-002 dst.) — tertunda, fokus frontier baru.
4. **pipeline_best.docx** — setelah edit manual user selesai, perlu sinkronisasi
   ulang dengan `pipeline_data.json` (supaya regenerasi tak menimpa manual edit).

---

## What Was Done (sesi ini)

1. `scripts/generate_report.py` — `render_xlsx()` dirombak: output
   `results_comparison.xlsx` (6 sheets), grid border, header indigo `1F3864`,
   baris selang-seling, winner row highlight, delta direction-aware
   (accuracy naik=hijau/turun=merah; cost turun=hijau), delta chain terpisah
   LLM vs OCR (like-for-like). `phase_v4_results_summary.xlsx` dihapus,
   referensi .md/README/report_data.json di-update.
2. `scripts/generate_raw_vs_pipeline.py` (baru) — `raw_vs_pipeline.xlsx`
   (74 cert) + `raw_vs_pipeline_examples.docx` (5 contoh terkurasi: router win,
   LLM fallback, organizer normalisasi, OCR gagal, field gagal).
3. `docs/report/mentor_presentation_notes.md` (baru) — Q&A presentasi.
4. `docs/report/pipeline_data.json` — +`field_methods` (7 field: metode/
   mekanisme/modul) +`ner_status`; `scripts/generate_pipeline_doc.py` — section
   "Metode Penentuan Field" di docx/md + sheet `Field Methods` di xlsx.
5. `docs/report/README.md` — +baris artefak baru.
6. Commit `4b7e029` (artefak mentor) + `9599c9d` (pipeline_best field methods).

`uv run python -m pytest tests/` → **31 passed**. GT & produksi tak disentuh.

---

## Key Files

| File | Peran |
|---|---|
| `scripts/generate_report.py` | Generator report (docx/md/xlsx) — render_xlsx baru |
| `scripts/generate_raw_vs_pipeline.py` | Generator raw-vs-pipeline (baru) |
| `scripts/generate_pipeline_doc.py` | Generator pipeline_best — +Field Methods |
| `docs/report/results_comparison.xlsx` | Perbandingan semua eksperimen (gitignored, regenerate) |
| `docs/report/raw_vs_pipeline.xlsx` + `.docx` | Matriks 74 cert + contoh terkurasi (gitignored) |
| `docs/report/mentor_presentation_notes.md` | Catatan presentasi mentor |
| `docs/report/pipeline_data.json` | Source pipeline_best (field_methods, ner_status) |
| `docs/report/ood_probe.md` | Output eksperimen C (belum ada) |

---

## Jangan Lakukan

- Ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Run benchmark tanpa `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Ubah angka eksperimen di ledger/report_data jadi angka pasca-promosi —
  snapshot berbeda, simpan keduanya dgn label jelas
- Aktifkan `ENABLE_OCR_NUMBER_2PASS=true` tanpa smoke API + ukur cost riil
- **Jalankan `generate_pipeline_doc.py` saat user masih edit pipeline_best.docx**
  (menimpa manual edit) — backup docx dulu bila perlu
- Re-run Exp 5 multi-field tanpa melonggarkan gate token (ledger EXP5-001)
- Uji CnOCR/MMOCR/DocTR full-replacement (ledger OCR-005/006)
- Sentuh `backend/` tanpa keputusan user
