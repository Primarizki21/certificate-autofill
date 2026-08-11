# Handoff v26 — KB-003 (normalisasi key PASS, shadow hit 3→5) + KB-004 (alat audit data riil)

> Supersedes `docs/handoff_v25.md`. Sesi ini = KB-003 (varian normalisasi key
> plain/stem/alias/both) + KB-004 (instrumen audit korpus tanpa GT, dry-run
> selfcheck PASS). Produksi tetap zero-touch. Commit saja, user yang push.

---

## Hasil sesi (committed: `1360df5` + commit baru)

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. `tests/kb/key.py` — `build_key(..., variant)` + `KEY_ALIASES` (FST pair) + `_stem_org` | Demo pass; alias menyatukan FST pair; versi key `v1-{variant}` tak tercampur | DONE |
| 2. `tests/benchmark_kb_norm.py` — KB-003: 4 varian (ceiling seeded + shadow 3x N=20 + noise 25%) | plain: 55 key/3 repeat, shadow hit 3. **stem/alias/both: 54 key/2 repeat, shadow hit 5 (+2), collision 0, wrong 0** | DONE (G1-G4 PASS) |
| 3. `tests/kb/audit.py` — KB-004: audit tanpa GT (router + fallback offline), CLI `--dir/--variant/--out` | Dry-run 74 cert: **SELFCHECK PASS** (55==55, 3==3, konsisten KB-001); collision 0, saved_llm 0 | DONE |
| 4. QA | pytest 31 passed; self-check key/store; registry runs_summary: kb_norm (83.8%) terindeks; kb_audit sengaja di luar registry (bukan run macro) | DONE |
| 5. Docs | Ledger KB-003 + KB-004; `kb_history.md` entri; `docs/report/kb_norm.md` + `kb_audit.md`; handoff ini | DONE |

---

## Temuan penting sesi ini

1. **Normalisasi key menaikkan shadow hit 3 → 5** (stem = alias = both, imbang
   di korpus ini) — FST pair menyatu, collision 0, wrong 0, noise-safe.
   Perbaikan nyata pertama yang terukur di level KB tanpa data baru.
2. **Pilih varian di data riil**: stem = agresif ("universitas"→"universita",
   over-merge risk), alias = konservatif tapi 1 baris saja. `audit.py --variant`
   siap membandingkan di korpus baru.
3. **KB-004 = gate produksi yang tidak lagi menunggu GT**: repeat key,
   collision, proyeksi saved LLM terukur langsung dari teks (0 LLM/OCR).
   Saat data lintas fakultas datang: `uv run python -m tests.kb.audit --dir <dir>`.
4. Alias menarget bentuk key persis (case) — rapuh thd perubahan titleize;
   pasangan alias/stem di `both` lebih tahan.
5. `report_data.json` tetap tidak disentuh (keputusan user, preseden v23/v24).

---

## Frontier berikutnya (urutan saran) — menunggu keputusan user

1. **Sampling data riil lintas fakultas** → jalankan `tests/kb/audit.py`
   (repeat key, collision, saved_llm) + `--variant` utk pilih normalisasi key.
   **Gate utama KB — alat sudah siap.**
2. **Port produksi v3+R6** (KEEP R0/R2/PREFIX_HELD/R6, GUARD R1/R4, hapus
   R3/R5) — keputusan user (produksi zero-touch).
3. Scoring organizer_v2 (2160238 + salah_org/kosong 12 kasus) — produksi.
4. Matcher v2.1 / alias — keputusan user.
5. Ekstrak `jenis_kegiatan` beneran utk key lebih presisi (schema produksi).

## Frontier tertunda (sama dengan v24/v25)

- F4 fingerprint dedup, F5 distillation, F7 infra OCR queue, Eksperimen A
  (LLM per-field — TIDAK, F1 v3+R6 PASS).

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Jangan sentuh `backend/` tanpa keputusan user (eksperimen tetap di `tests/`)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..006, LLM-001..003, ROUTER-001, NC-001/002
- Pytest: `uv run python -m pytest tests/ -q` (31 passed)
- Konfig KB: mutasi `WARMUP_CONFIRMS` WAJIB via `import tests.kb.kb as kbimpl`
- `results_comparison.xlsx` tidak di-commit — regenerate lokal bila perlu
- `report_data.json` belum berisi F1C/OOD-003/KB — keputusan user

## Key Files

| File | Peran |
|---|---|
| `tests/kb/key.py` | Key canonicalizer v1 + varian normalisasi (KB-003) |
| `tests/benchmark_kb_norm.py` | KB-003 — 4 varian (ceiling/shadow/noise) |
| `tests/kb/audit.py` | KB-004 — audit korpus tanpa GT (gate data riil) |
| `tests/kb/store.py` | Persistence JSON + key_version check |
| `docs/report/kb_norm.md` | Report KB-003 |
| `docs/report/kb_audit.md` | Report KB-004 (dry-run) |
| `docs/kb_history.md` | History naratif KB (KB-003/004) |
| `docs/experiments_ledger.md` | KB-003 + KB-004 |
