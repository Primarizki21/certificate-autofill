# Handoff v20 — Plan final: KB opsi B (PG, bukan graph) + protokol evaluasi wajib + F1 lanjutan

> Supersedes `docs/handoff_v19.md`. Keputusan user di sesi v19: (1) tidak push,
> hanya commit; (2) produksi = zero-touch sampai eksperimen mentok; (3) gaya
> komunikasi = bahasa mudah + contoh konkret, ringkas; (4) KB = opsi B
> (komposit organizer + tipe kegiatan), storage PostgreSQL (bukan graph DB),
> dengan index primary key; (5) preferensi: pendekatan tanpa AI/LLM didahulukan.

---

## Hasil sesi v19 (sudah committed — `f921a49`, `166a4e5`, `9484146`, `20d452b`, `2666688`)

| Fase | Hasil | Verdict |
|---|---|---|
| F0 stat validasi | Router **45/74 @100%** tervalidasi (5-fold, semua rule min-fold 100%); **8/13 rule LOW-N** (fire <5); bootstrap CI MACRO exact 56.0–64.4%, fuzzy 70.3–78.3%, coverage 50.0–71.6% | PASS |
| F0 OOD probe | Mutation: field bebas-institusi −1.2pt (tingkat −4.1pt = kerapuhan riil); organizer/nomor drop = artefak GT (token institusi di jawaban). Noise: 10/25/50% = −8.6/−16.4/−24.2pt | PASS (report-only) |
| F1 normalisasi | **Nomor 59.6→76.9% (+17.3pt)** — pattern SERT- + fallback raw text (normalize_text memecah UN27/NACOESTA4.0). Organizer 37.8→39.2% (+1.4pt) **gate FAIL** | PARTIAL PASS |
| F2 rule mining | Router **45→50/74 @100%** (ukm_org 3/3, hima_dept 2/2, 5-fold semua 100%); LLM calls 29→24; LLM benar cuma 17/29 (58.6%) di unrouted | PASS |
| F6 needs_review | Confidence berbasis pola (PKKMB 0.95/struktural 0.60/keyword 0.50/None 0) + ambang per-field; recall cert-level **98.6%**, FP 1 cert; 73/74 ter-flag (trade-off safety net) | PASS |

- Ledger: `STAT-001`, `OOD-001`, `ORG-002`, `ROUTER-004`, `REVIEW-001` — semua PASS/PARTIAL
- Reports: `docs/report/stat_validation.md`, `ood_probe.md`, `f1_org_norm.md`, `f2_rule_mining.md`, `f6_needs_review.md`
- `pipeline_data.json` + `v10_experiments`; `runs_summary.md` regenerated
- pytest 31 passed; **produksi tak disentuh**

---

## Protokol evaluasi WAJIB (untuk semua eksperimen baru)

1. **Rule router baru → k-fold dulu** (`tests/stat_validation.py`): precision
   per-rule di fold uji; klaim hanya valid dengan CI; fire <5 (LOW-N) = jangan
   diklaim robust. Ini protokol F0 yang jadi gate semua klaim.
2. **Setiap perubahan ekstraktor/router → `pytest tests/` (31 test)** + no-regress
   vs baseline GT v9 + matcher v2 (`GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`).
3. **JANGAN bandingkan decision router lama** (snapshot `router_decisions.json`
   run v9) vs code baru tanpa recompute organizer — snapshot memakai organizer
   pre-85f5cc8 (6/74 beda, memicu 2 false rule). Selalu recompute organizer
   dengan `tests/organizer_extractor_v2` current.
4. **Benchmark run**: `uv run python -m tests.X`; format run dir
   `tests/benchmark_runs/{kind}_{ts}`; update ledger + report .md per eksperimen.
5. **Matcher v2 + GT v9 = baseline evaluasi, jangan diubah** tanpa re-baseline
   eksplisit. Normalisasi pipeline-side dulu; evaluator hanya jika disetujui user.
6. **`offline_fields()`/`offline_variant()`** (di `tests/ood_probe.py`,
   `tests/benchmark_org_norm.py`) = pipeline offline tanpa LLM/OCR untuk semua
   evaluasi cepat — reuse, jangan duplikasi.

---

## Keputusan KB (final, dari sesi v19)

### Key: opsi B — komposit `(normalized_organizer, event_type)`

| | A (organizer saja) | **B (organizer + tipe kegiatan)** | C (fingerprint teks) |
|---|---|---|---|
| Risiko salah-kontek | tinggi | rendah | minimal |
| Kompleksitas | paling sederhana | sedang | paling kompleks |
| Generalisasi | tingkat saja | tingkat + siap F4 | short-circuit semua field |

**Dipilih B** — risiko salah-propagasi jauh lebih kecil dari A, jauh lebih
sederhana dari C (C rawan OCR noise). Bisa di-upgrade ke C untuk F4 nanti.

### Storage production: PostgreSQL (bukan graph DB)

- **Angka terukur**: 74 cert → 56 organizer unik (teratas BEM FTMM 7×).
  Proyeksi produksi 36k request: 1.000–10.000 unik (15 fakultas × BEM/HIMA/UKM
  + event tahunan). **Asumsi wajib divalidasi** dengan sampling data riil
  lintas fakultas sebelum keputusan arsitektur final (roadmap F3).
- **Kenapa PG menang vs graph DB**: point lookup = kecepatan imbang (keduanya
  O(log n) sub-ms di skala ribuan baris); PG = sudah di stack, transaksi +
  foreign key + audit SQL natural, concurrency teruji; Neo4j = server tambahan
  (JVM/RAM, beban operasional) tanpa keuntungan di skala ini.
- **Index**: composite primary key `(normalized_organizer, event_type)` = B-tree
  otomatis (O(log n) sub-ms). Tambah index `source`/`last_verified_at` hanya
  kalau query audit terasa lambat. Redis cache layer = hanya kalau profiling
  menunjukkan butuh (jangan dulu).
- **Tidak terkunci**: migrasi ke graph DB masa depan murah (LOAD CSV) — data
  berbentuk node/edge sederhana.
- **Prototipe**: in-memory dict di `tests/` (tanpa DB). Tabel
  `organizer_tingkat_kb` di `models.py` + flag `ENABLE_*` HANYA saat promosi
  produksi (masih jauh, butuh keputusan user).

### Mitigasi risiko KB

- `source` enum (router_rule | llm | human_review) — entry LLM diaudit lebih sering
- Warm-up: minggu pertama rollout, butuh 2-3 konfirmasi konsisten sebelum
  authoritative (jangan langsung trust 1 hit)
- Audit sampling: sekian % KB hit direview manual per batch (protokol F0)
- `hit_count`, `last_verified_at`, `created_from_cert_id` untuk traceability

---

## Rencana sesi berikutnya (urutan eksekusi)

1. **AGENTS.md**: tambah protokol k-fold/OOD wajib (Testing section) + gaya
   komunikasi user (bahasa mudah + contoh konkret, ringkas).
2. **`tests/robustness_eval.py`**: gabung k-fold + bootstrap CI + OOD probe
   dalam 1 perintah, 1 report (`docs/report/robustness_eval.md`) — reuse
   `stat_validation.py` + `ood_probe.py`, jangan duplikasi logika.
3. **F1b — taksonomi fuzzy penyelenggara** (`tests/f1b_organizer_taxonomy.py`):
   klasifikasi 28 kasus fuzzy (benar-tapi-kurang-lengkap vs sampah) → ceiling
   riil + daftar perbaikan. Output `docs/report/f1b_organizer_taxonomy.md`.
4. **F1 lanjutan — perbaiki pemilihan penyelenggara tanpa AI**
   (`tests/benchmark_organizer_v3.py`): fokus 2 kategori terbesar dari
   taksonomi (lengkapi "Himasada" + fakultas; buang sampah "Which Held From…").
   **GATE**: organizer exact naik ≥+5pt (dari 39.2%), no-regress field lain,
   0 LLM call. Produksi tidak disentuh — extend copy di tests.
5. **F3 — `docs/kb_design.md`** (opsi B + storage PG + mitigasi di atas) →
   prototipe KB in-memory `tests/kb/` + benchmark replay warm-up (populate dari
   N cert pertama, ukur penurunan LLM call).
6. **Eksperimen A** (LLM per-field nama_kegiatan/organizer, dari handoff v18)
   — **HANYA** kalau langkah 4 gagal gate. GATE: nama_kegiatan exact ≥30%
   (dari 25.7%), penyelenggara no-regress, tok ≤200/cert, extra calls ≤30/74,
   tingkat no-regress. JANGAN ulangi EXP5-001 (multi-field satu call = token FAIL).

---

## Frontier tertunda

- **F4 fingerprint dedup** — butuh KB stabil sebagai referensi (roadmap urutan #6)
- **F5 distillation classifier** — butuh volume data dari F3 warm-up (#7)
- **F7 infra OCR queue** — independen, menyentuh produksi, butuh keputusan user (#8)
- **Promosi produksi**: TIDAK — sampai eksperimen mentok + keputusan user eksplisit

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` masih diedit manual — **JANGAN jalankan**
  `generate_pipeline_doc.py` (menimpa edit manual)
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Jangan run benchmark tanpa `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Jangan sentuh `backend/` tanpa keputusan user (eksperimen tetap di `tests/`)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run pendekatan closed di ledger (EXP5-001, OCR-001..006, LLM-001..003, ROUTER-001, NC-001/002) tanpa re-try condition
- Jangan re-run multi-field LLM / CnOCR/MMOCR/DocTR full-replacement

---

## Key Files

| File | Peran |
|---|---|
| `tests/stat_validation.py` | F0: k-fold router + bootstrap CI (protokol wajib rule baru) |
| `tests/ood_probe.py` | F0: OOD probe (mutation + noise) + `offline_fields()` |
| `tests/benchmark_org_norm.py` | F1: normalisasi organizer/nomor + `offline_variant()` |
| `tests/rule_mining.py` | F2: kandidat rule ukm_org/hima_dept + k-fold |
| `tests/benchmark_needs_review.py` | F6: prototipe needs_review |
| `docs/report/stat_validation.md` | Output F0 |
| `docs/report/ood_probe.md` | Output F0 |
| `docs/report/f1_org_norm.md` | Output F1 |
| `docs/report/f2_rule_mining.md` | Output F2 |
| `docs/report/f6_needs_review.md` | Output F6 |
| `docs/report/pipeline_data.json` | Source pipeline_best (+v10_experiments) |
