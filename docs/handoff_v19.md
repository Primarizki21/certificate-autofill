# Handoff v19 — Roadmap v10 F0-F2+F6 selesai: router tervalidasi, nomor +17.3pt, coverage 50/74

> Supersedes `docs/handoff_v18.md`. Sesi ini eksekusi roadmap-pipeline-v10
> F0 (stat validasi + OOD probe) → F1 (normalisasi organizer/nomor) → F2
> (rule mining) → F6 (needs_review). **Produksi TIDAK disentuh** (keputusan
> user: eksperimen terus sampai pipeline terbaik ditemukan).
> Commit: `f921a49` (F0), `166a4e5` (F1), `9484146` (F2), `20d452b` (F6).

---

## Hasil per fase

### F0 — Stat validasi + OOD probe (ledger STAT-001, OOD-001 — PASS)

- **Router v9 tervalidasi: 45/74 @100% precision** — recompute dengan organizer
  code CURRENT (bukan snapshot run v9 yang 6/74 beda). Semua 13 rule min-fold
  precision 100%. **8/13 rule LOW-N (fire <5)** — robustness tak bisa diklaim.
- Bootstrap CI (1000×): MACRO exact **56.0–64.4%**, fuzzy 70.3–78.3%, router
  coverage 50.0–71.6%.
- **OOD**: template mutation — MACRO field bebas-institusi hanya −1.2pt
  (tingkat −4.1pt = sinyal kerapuhan riil); drop organizer/nomor = artefak GT
  (token institusi di jawaban). OCR noise: 10% −8.6pt, 25% −16.4pt, 50% −24.2pt.
- ⚠️ **Temuan snapshot**: `router_decisions.json` run v9 memakai organizer lama
  (pre-85f5cc8) — memicu 2 false rule. Jangan bandingkan decision lama vs code
  baru tanpa recompute organizer.

### F1 — Normalisasi organizer & nomor (ledger ORG-002 — PARTIAL PASS)

- **Nomor: 59.6 → 76.9% (+17.3pt)** — pattern ke-4 prefix `SERT-` + fallback
  ekstraksi pada raw text (normalize_text memecah `UN27`/`NACOESTA4.0` sehingga
  regex nomor gagal). Gate PASS, 0 LLM call.
- **Organizer: 37.8 → 39.2% (+1.4pt)** — gate FAIL (target +5pt). Klasifikasi
  46 non-exact: 28 fuzzy = ekstraksi-parsial (PL benar tapi tidak lengkap),
  18 genuine-wrong. Normalisasi matcher v2.1 TIDAK akan menutup gap (fuzzy
  sudah contains/overlap; butuh nilai lengkap untuk exact).
- **Arah selanjutnya organizer**: scoring/candidate organizer_v2, fallback LLM
  per-field (eksperimen A v18), atau KB (F3). Bukan matcher.

### F2 — Rule mining (ledger ROUTER-004 — PASS)

- **Router coverage 45 → 50/74 @100% precision**, LLM calls 29 → 24.
- Rule baru (diuji 5-fold, semua fold 100%): `ukm_org` (organizer UKM tanpa
  lomba/luar/nasw/sem/fak/dept → Universitas, 3/3) + `hima_dept` (hima_org +
  dept → Departemen, 2/2; aman via guard ordering hima+luar duluan).
- LLM benar cuma 17/29 (58.6%) di unrouted — rule mining masih menang di
  subset yang LLM-nya ambigu.
- Implementasi rule: `tests/rule_mining.py` RULES dict — port ke
  `tingkat_router.py` saat promosi.

### F6 — needs_review field lemah (ledger REVIEW-001 — PASS)

- Masalah: confidence regex di-set tinggi begitu value ada (0.86/0.95) →
  field lemah tak pernah ter-flag walau salah.
- Prototipe: confidence berbasis pola (PKKMB 0.95 / struktural 0.60 /
  keyword-hardcode 0.50 / None 0.0) + ambang per-field (nama_kegiatan 0.55,
  nomor 0.80).
- **Cert-level recall 98.6%** (68/69 wrong-cert ter-flag), FP = 1 cert
  (satu-satunya cert exact-all di corpus). 73/74 cert ter-flag butuh review —
  trade-off safety net vs biaya review, sesuai arahan roadmap F6.
- Keyword hardcode (SPECTA 0/2 exact di corpus!) = confidence terendah +
  kandidat KB F3.

---

## Frontier berikutnya (urutan roadmap v10)

1. **F3 — Knowledge Base** (solusi struktural skala). Sebelum implementasi:
   tulis 2-3 opsi key (organizer murni vs komposit organizer+tipe event vs
   fingerprint) di `docs/kb_design.md`, minta keputusan user — roadmap F3
   eksplisit soal ini.
2. **F1 lanjutan — organizer**: perbaikan scoring/candidate organizer_v2
   (bukan normalisasi lagi) atau eksperimen A v18 (fallback LLM per-field,
   gate: nama_kegiatan ≥30%, tok ≤200/cert, calls ≤30).
3. **F4 fingerprint dedup** — butuh KB stabil. **F5 distillation** — butuh
   volume KB. **F7 infra OCR queue** — independen, butuh keputusan user.
4. **Promosi pipeline terbaik** — hanya dengan keputusan user eksplisit;
   kandidat saat ini: nomor fix F1 + rule F2 + needs_review F6 (semua di tests).

---

## Pekerjaan USER berjalan (agent JANGAN kerjakan)

- **User masih memperbaiki `docs/report/pipeline_best.docx` manual** — agent
  tidak menjalankan `generate_pipeline_doc.py` (menimpa edit manual).
- `pipeline_data.json` sudah di-update +v10_experiments — sinkronisasi docx
  manual menunggu keputusan user.

---

## What Was Done (sesi ini)

1. `tests/stat_validation.py` (baru) — 5-fold per-rule router + bootstrap CI →
   `docs/report/stat_validation.md`.
2. `tests/ood_probe.py` (baru) — template mutation + OCR noise kurva →
   `docs/report/ood_probe.md`.
3. `tests/benchmark_org_norm.py` (baru) — normalisasi organizer/nomor →
   `docs/report/f1_org_norm.md`.
4. `tests/rule_mining.py` (baru) — kandidat rule + k-fold →
   `docs/report/f2_rule_mining.md`.
5. `tests/benchmark_needs_review.py` (baru) — prototipe needs_review →
   `docs/report/f6_needs_review.md`.
6. `docs/experiments_ledger.md` — +STAT-001, OOD-001, ORG-002, ROUTER-004,
   REVIEW-001.
7. `docs/report/pipeline_data.json` — +v10_experiments.
8. `docs/report/runs_summary.md` — regenerated (run dirs baru report-only,
   tidak masuk registry).

`uv run python -m pytest tests/` → **31 passed**. Produksi tak disentuh.

---

## Key Files

| File | Peran |
|---|---|
| `tests/stat_validation.py` | F0: k-fold router + bootstrap CI |
| `tests/ood_probe.py` | F0: OOD probe (mutation + noise) |
| `tests/benchmark_org_norm.py` | F1: normalisasi organizer/nomor (offline_fields dipakai ood_probe juga) |
| `tests/rule_mining.py` | F2: kandidat rule ukm_org/hima_dept |
| `tests/benchmark_needs_review.py` | F6: prototipe needs_review |
| `docs/report/stat_validation.md` | Output F0 |
| `docs/report/ood_probe.md` | Output F0 |
| `docs/report/f1_org_norm.md` | Output F1 |
| `docs/report/f2_rule_mining.md` | Output F2 |
| `docs/report/f6_needs_review.md` | Output F6 |

---

## Jangan Lakukan

- Ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Run benchmark tanpa `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Bandingkan decision router lama (snapshot run v9) vs code baru tanpa
  recompute organizer (artefak pre-85f5cc8)
- Jalankan `generate_pipeline_doc.py` saat user masih edit pipeline_best.docx
- Sentuh `backend/` tanpa keputusan user (eksperimen tetap di `tests/`)
- Re-run multi-field LLM (EXP5-001) / CnOCR/MMOCR/DocTR full-replacement
  (OCR-005/006) — closed
