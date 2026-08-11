# Handoff v25 — KB-002: seeded persistent KB PASS + koreksi konfig KB-001/F3 (1x confirm = GATE FAIL)

> Supersedes `docs/handoff_v24.md`. Sesi ini = eksperimen KB-002 (seeded
> persistent KB: ceiling human-seed + persistence JSON + fragmentasi key) +
> koreksi bug konfig `WARMUP_CONFIRMS` yang memengaruhi F3-001/KB-001.
> Produksi tetap zero-touch (eksperimen di `tests/`). Commit saja, user yang push.

---

## Hasil sesi (committed: `b3c4f3d` + commit baru)

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. `tests/kb/store.py` — persistence JSON + key_version check + round-trip | Round-trip identik (ukuran + authoritative + konflik) | DONE (G1 PASS) |
| 2. `tests/kb/kb.py` — `items()` snapshot view | Dipakai save_kb + collision stats | DONE |
| 3. `tests/benchmark_kb_seed.py` — smoke + ceiling seeded + noise 25% + learning persist + fragmentasi | Smoke ok; ceiling: seed 3 keys/9 certs, hit 9, **saved_llm 0**, wrong 0; noise 25% wrong 0; persist mem==identik (1x: 51/13/**wrong 5**; 3x: 3/0/0); fragmentasi FST DEPT 1 org → 2 key (7 cert) | DONE |
| 4. **Koreksi bug konfig** — `WARMUP_CONFIRMS` dimutasi via package namespace (`from tests import kb`) tidak efektif; fix `import tests.kb.kb as kbimpl` di `benchmark_kb_seed.py` + `benchmark_kb_shadow.py` + `benchmark_kb_warmup.py` | Re-run shadow: **1x = hit 51, saved_llm 13, wrong 5**; 3x = hit 3, wrong 0 (angka KB-001 lama = 3x valid). F3-001: semua baris sebenarnya 3x — kesimpulan F3 tetap valid | DONE (1x = GATE FAIL precision) |
| 5. Registry | `runs_summary` regenerated: kb_seed (83.8%), kb_shadow (84.4%) | DONE |
| 6. Pytest + ledger + history | pytest 31 passed; ledger **KB-002** + addendum KB-001; `docs/kb_history.md` entri KB-002 + koreksi | DONE |

---

## Temuan penting sesi ini

1. **Seeded KB (human_review) = aman**: 9/9 hit exact vs GT, 0 wrong, 0
   disagree; noise 25% tetap 0 wrong. Ceiling knowledge terverifikasi tidak
   merusak apa pun — tapi **saved_llm = 0** di korpus 74 (key berulang
   semuanya cert yang router sudah putuskan).
2. **1x confirm = GATE FAIL precision (wrong 5)** — error label LLM yang
   masuk KB di 1 kemunculan langsung authoritative & menyebar. Warm-up ≥3
   confirm WAJIB (3x: 0 wrong). Sebelumnya konfig ini tidak pernah benar-benar
   teruji (bug mutasi module).
3. **Persistence terbukti**: snapshot JSON + key_version check; hasil evaluasi
   dari KB yang disimpan == KB in-memory (1x dan 3x identik).
4. **Fragmentasi key**: 1 org logis (FST INFORMATION SYSTEMS DEPT) terpecah
   2 key ("SYSTEMS" vs "SYSTEM", 7 cert) oleh exact-match → hit rate KB turun.
   Kandidat perbaikan: normalisasi key case/punct/stem ATAU alias table
   (hati-hati over-merge → collision baru).
5. `report_data.json` TIDAK disentuh (preseden v23/v24 — butuh keputusan user).

---

## Frontier berikutnya (urutan saran) — menunggu keputusan user

1. **Sampling data riil lintas fakultas** — validasi asumsi unique organizer
   1.000–10.000 + repeat key & collision di data besar. **Gate utama KB.**
2. **Normalisasi key lanjutan** (fragmentasi FST, case/punct/stem) vs alias
   table — eksperimen `tests/` sebelum produksi.
3. Port produksi v3+R6 (KEEP R0/R2/PREFIX_HELD/R6, GUARD R1/R4, hapus R3/R5)
   — keputusan user (produksi zero-touch).
4. Scoring organizer_v2 (2160238 + salah_org/kosong 12 kasus) — produksi.
5. Matcher v2.1 / alias — keputusan user.
6. Ekstrak `jenis_kegiatan` beneran utk key lebih presisi (schema produksi).

## Frontier tertunda (sama dengan v24)

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
  (package namespace tidak efektif)
- `results_comparison.xlsx` tidak di-commit — regenerate lokal bila perlu
- `report_data.json` belum berisi F1C/OOD-003/KB — keputusan user

## Key Files

| File | Peran |
|---|---|
| `tests/benchmark_kb_seed.py` | KB-002 — smoke/ceiling/persist/fragmentasi |
| `tests/kb/store.py` | Persistence JSON + key_version check |
| `tests/kb/kb.py` | Conflict semantics + `items()` |
| `tests/kb/key.py` | Key canonicalizer v1 |
| `docs/report/kb_seed.md` | Report KB-002 |
| `docs/report/kb_shadow.md` | Report KB-001 (re-run konfig benar) |
| `docs/kb_history.md` | History naratif KB (KB-002 + koreksi) |
| `docs/experiments_ledger.md` | KB-002 + addendum KB-001 |
