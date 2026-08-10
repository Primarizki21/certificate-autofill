# Handoff v21 — F1b taksonomi + F1 lanjutan v3 (GATE PASS) + robustness_eval + F3 KB prototipe

> Supersedes `docs/handoff_v20.md`. Sesi ini menuntaskan seluruh rencana sesi v20
> (langkah 1–5). Keputusan user tetap: produksi = zero-touch, commit saja
> (user yang push), tanpa AI/LLM didahulukan, KB = opsi B (PG, bukan graph).

---

## Hasil sesi (committed: `753b9e3`, `4d62ec9`, `644e811`)

| Langkah | Hasil | Verdict |
|---|---|---|
| 0. Commit artefak untracked | `docs/roadmap-pipeline-v10.md` (baru diedit 10/08) + instruksi rangkuman + script summary v1/v2 + helper | DONE |
| 1. AGENTS.md | Protokol evaluasi WAJIB (k-fold/OOD, no-regress GT v9+matcher v2, snapshot router, offline reuse) + Gaya Komunikasi user | DONE |
| 2. `tests/robustness_eval.py` | Gabung k-fold + bootstrap CI + OOD probe, 1 perintah → `docs/report/robustness_eval.md`. Angka cocok ledger (CI MACRO 56.0–64.4%, router coverage 50.0–71.6%, noise −8.6/−16.4/−24.2pt) | PASS |
| 3. F1b taksonomi | 45 non-exact organizer → kelebihan 10 / kurang_lengkap 9 / format 12 / salah_org 8 / kosong 4 / format_residu 2. Ceiling: kelebihan→52.7%, kurang_lengkap→51.4%. **Temuan: 2 bug di lapisan F1** | PASS (report-only) |
| 4. **F1 lanjutan v3** | Organizer exact **39.2% → 45.9% (+6.7pt)** GATE PASS (≥44.2%), MACRO 58.3→59.6% no-regress, 0 LLM call, pytest 31 passed. 5 fix per-cert (R0 rule B bug, R1 suffix dept Inggris, R2 Library Class, R3 oleh, R4 tanggal, `_PREFIX_HELD` fix) | **PASS** |
| 5. F3 KB prototipe | `tests/kb/kb.py` + replay warm-up: LLM calls 31→29 (mekanisme bekerja), tingkat eval ≈ pipeline, collision 0. **Temuan: 74 cert cuma 2 key berulang** → asumsi unique organizer belum tervalidasi. `docs/kb_design.md` = desain final (opsi B + PG + mitigasi + skema) | PASS (prototipe) |

- Ledger baru: `F1B-001`, `ORG-003`, `F3-001` (semua PASS). Report:
  `robustness_eval.md`, `f1b_organizer_taxonomy.md`, `f1_organizer_v3.md`,
  `f3_kb_warmup.md`, `docs/kb_design.md`. `runs_summary.md` regenerated
  (organizer_v3 + kb_warmup terdaftar).

---

## Perbaikan yang direkomendasikan untuk produksi (masih menunggu keputusan user)

1. **Bug normalisasi F1 (benchmark_org_norm)**: `_TRAILING_ORG.sub("", v)` →
   `r"\1"` (sekarang menghapus seluruh string — rule B/C tak pernah efektif);
   `_PREFIX_JUNK` regex `\s+was?` tak pernah match "Which Held From" (1 spasi).
   Fix sudah tervalidasi di `tests/benchmark_organizer_v3.py` (lapisan v3).
2. **Lapisan organizer v3** (R0–R5, ORG-003): +6.7pt organizer, 0 LLM.
3. **Nomor pattern ke-4 + fallback raw** (ORG-002): +17.3pt.

Semua = tests-only; port ke produksi butuh keputusan eksplisit user.

---

## Frontier berikutnya (urutan saran)

1. **Matcher v2.1 / normalisasi alias** — keputusan user: DITUNDA sampai hasil
   F1 lanjutan; F1 v3 PASS → bucket `format` (12 kasus: alias UB↔Brawijaya,
   case/spasi, OCR) sekarang jadi pertimbangan. Opsi: (a) normalisasi
   pipeline-side lanjut (case/plural/alias kecil), (b) matcher v2.1 dengan
   re-baseline evaluasi — butuh keputusan user.
2. **F1 selanjutnya**: `kurang_lengkap` (9 kasus: enrich fakultas/prodi dari
   konteks teks, mis. `Himasada` → `Himasada, Fakultas Ilmu Komputer`) — 0 LLM,
   target organizer +~12pt. `salah_org`/`kosong` (12) butuh scoring organizer_v2.
3. **F3 lanjutan**: sampling data riil unique organizer lintas fakultas
   (validasi asumsi 1.000–10.000 unik) — prasyarat keputusan arsitektur KB.
4. **Eksperimen A (LLM per-field)**: TIDAK dijalankan — F1 v3 PASS gate
   (handoff v20: hanya jika F1 gagal).

## Frontier tertunda (sama dengan v20)

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
- Pytest di sesi ini: `uv run python -m pytest tests/ -q` (31 passed) —
  `pytest` langsung gagal spawn/module di env ini, pakai `python -m pytest`

## Key Files

| File | Peran |
|---|---|
| `tests/robustness_eval.py` | Gabungan k-fold + bootstrap + OOD (1 perintah, reuse stat_validation + ood_probe) |
| `tests/f1b_organizer_taxonomy.py` | Taksonomi mismatch organizer (ceiling riil) |
| `tests/benchmark_organizer_v3.py` | F1 lanjutan: lapisan normalisasi organizer v3 (R0–R5) + GATE |
| `tests/kb/kb.py`, `tests/benchmark_kb_warmup.py` | Prototipe KB in-memory (opsi B) + replay warm-up |
| `docs/kb_design.md` | Desain final KB (PG + index PK komposit + mitigasi + skema) |
| `docs/report/robustness_eval.md` dkk | Output eksperimen sesi ini |
| `docs/report/runs_summary.md` | Registry (organizer_v3 + kb_warmup terdaftar) |
