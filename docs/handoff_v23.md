# Handoff v23 — F1C-001: enrich `kurang_lengkap` organizer (R6) — organizer 54.1%, MACRO 61.2%

> Supersedes `docs/handoff_v22.md`. Sesi ini = eksekusi frontier #2 v22 (F1
> selanjutnya: `kurang_lengkap` enrich, 0 LLM) atas keputusan user "ok boleh,
> tolong eksekusi". Produksi tetap zero-touch; commit saja (user yang push).

---

## Hasil sesi (belum commit)

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. Verifikasi 9 kasus `kurang_lengkap` ke teks sumber | 5-6 fixable dari teks (2954933, IRIS, SERTIF76, Gelar Rasa, Ananda Agentic AI + E-certificate (1)); **4 skip**: 2160238 (masalah scoring — extracted cuma institusi), E-certificate (1) awalnya di-skip tapi ternyata punya baris dept di teks → fix, NIC_Faiz (OCR merge parah), SDC Unisba (OCR spasi hancur) | DONE |
| 2. R6 di `tests/benchmark_organizer_v3.py` | 5 mekanisme: join baris beruntun (camel-split + typo `llmu`→`ilmu`), Biro-prefix, Himasada fakultas, IRIS prepend, dept OCR-merge. Guard keras: v tanpa penanda fakultas/kampus, baris lanjutan beruntun max 2, dedup ≠ v. Gate kode 44.2 → 51.0 | DONE |
| 3. Benchmark (`organizer_v3_20260810_160232`) | Organizer **45.9% → 54.1% (+6.2pt)** dari ORG-003; 39.2% → 54.1% dari baseline F1. MACRO **59.6% → 61.2%** (+1.6, no-regress). 0 regress, 0 LLM | **GATE PASS** (≥51.0%) |
| 4. Risiko regress empiris | Piagam HIMA S1-AK, 2065179, UKM×2, 2439919, Venedict_specta aman — guard baris beruntun/berkata-kunci bekerja | DONE |
| 5. Pytest + registry + ledger | pytest 31 passed. `runs_summary.md` entri organizer_v3 diganti ke run baru (61.2%). Ledger: **F1C-001** (PASS) | DONE |

---

## Temuan penting sesi ini

1. **F1C-001 — 6 fix baru dari konteks teks**: 2954933 (join 3 baris +
   camel-split `FakultasMatematika` + typo OCR `llmu`→`ilmu`), IRIS (baris org
   tepat di atas baris fakultas), SERTIF76 (`Biro` di akhir baris sebelumnya),
   Gelar Rasa (`DEKAN FAKUETASILMU KOMPUTER`), Ananda Agentic AI + E-certificate
   (1) (baris dept ter-merge `INFORMATIONSYSTEMSSTUDYPROGRAM`).
2. **4 kasus tak fixable dari teks**: 2160238 = masalah SCORING (extracted cuma
   "Universitas Airlangga", org spesifik ada di teks tapi kalah skor) —
   ranah organizer_v2, bukan normalisasi; NIC_Faiz & SDC Unisba = OCR rusak.
3. **R6 murni teks-bergantung** — OOD probe v3 belum di-re-run untuk R6.
   Ekspektasi: rapuh di noise (mirip R1/R4). Re-run sebelum port produksi.
4. `report_data.json`/xlsx **TIDAK di-update** (belum ada keputusan user —
   F1C adalah lanjutan ORG-003 yang sudah di laporan resmi; kalau mau masuk,
   regenerate `scripts/generate_report.py` lokal).

---

## Frontier berikutnya (urutan saran) — menunggu keputusan user

1. **Port produksi v3+R6** — per-aturan OOD-002 + F1C-001: KEEP R0/R2/PREFIX_HELD/
   R6, GUARD R1/R4 (needs_review F6), hapus R3/R5. **Butuh keputusan user**
   (produksi zero-touch).
2. **Re-run OOD probe v3** untuk R6 (robust noise) — prasyarat klaim robust
   sebelum port. **Siap eksekusi tanpa keputusan baru.**
3. **Matcher v2.1 / normalisasi alias** — bucket `format` (12 kasus). **Butuh
   keputusan user** (a) pipeline-side vs (b) matcher v2.1 + re-baseline.
4. **Scoring organizer_v2** — 2160238 + `salah_org`/`kosong` (8+4 kasus). Ranah
   scoring, produksi tersentuh. **Butuh keputusan user.**
5. **F3 lanjutan** — sampling data riil unique organizer. **Butuh data baru.**

## Frontier tertunda (sama dengan v22)

- F4 fingerprint dedup (butuh KB stabil), F5 distillation (butuh volume F3),
  F7 infra OCR queue (produksi), Eksperimen A (LLM per-field — TIDAK, hanya
  jika F1 gagal; F1 v3+R6 PASS).

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Jangan sentuh `backend/` tanpa keputusan user (eksperimen tetap di `tests/`)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..006, LLM-001..003, ROUTER-001, NC-001/002
- Pytest: `uv run python -m pytest tests/ -q` (31 passed)
- `results_comparison.xlsx` tidak di-commit — regenerate lokal bila perlu
- `report_data.json` belum berisi F1C — keputusan user apakah masuk laporan resmi

## Key Files

| File | Peran |
|---|---|
| `tests/benchmark_organizer_v3.py` | Lapisan organizer v3 + **R6 enrich** (R0-R6, `enabled` param utk ablation) |
| `docs/report/f1_organizer_v3.md` | Report run organizer_v3_20260810_160232 (54.1%, 6 fix R6) |
| `docs/report/runs_summary.md` | Registry (entri organizer_v3 terbaru = 160232, 61.2%) |
| `docs/experiments_ledger.md` | **F1C-001** (PASS) di samping OOD-002, ORG-003 |
| `tests/f1b_organizer_taxonomy.py` | Taksonomi mismatch (sumber daftar 9 kasus kurang_lengkap) |
