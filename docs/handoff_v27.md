# Handoff v27 — KB-005 (role = event terbaik) + KB-006 (alias mining PASS) + Verdict Final jalur KB

> Supersedes `docs/handoff_v26.md`. Sesi ini = penutup jalur eksperimen KB:
> KB-005 (event_type, jawaban desain #1) + KB-006 (alias mining) PASS, lalu
> **Verdict Final** — KB tuntas sebagai eksperimen, produksi tidak
> dipertimbangkan (keputusan user: eksperimen murni sampai ada pipeline yang
> menonjol; tidak ada data di luar korpus 74).

---

## Hasil sesi (committed: `2c60abb` + commit baru)

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. `tests/kb/key.py` — `EVENTS` + `compute_event` + `make_key` + `build_key(event=...)` | Demo pass; backward-compat (event=role = versi lama) | DONE |
| 2. KB-005 `tests/benchmark_kb_event.py` — 4 varian × 3 event = 12 kombinasi | **role = satu-satunya collision 0** (empty 13, shadow hit 5 utk stem/alias/both, wrong 0); jenis empty 52 + wrong 1; kelompok collision 1 + wrong 2 | PASS (role) — jawaban desain #1: role proxy cukup |
| 3. KB-006 `tests/kb/alias.py` + `benchmark_kb_alias.py` — mining + precision + dampak | Mining = PERSIS alias manual (FST pair, valid=True); auto-alias shadow hit 5, wrong 0, noise 0 | PASS — precision 100% |
| 4. QA | pytest 31 passed; self-check key/store/alias; registry: kb_event + kb_alias (83.8%) | DONE |
| 5. Verdict Final jalur KB + docs | `kb_history.md` (KB-005/006 + Verdict Final); ledger KB-005/006; handoff ini | DONE |

---

## Temuan penting sesi ini

1. **Role proxy = keputusan final utk event_type** (menutup pertanyaan desain
   #1 & schema): jenis_kegiatan 70% empty (`"--"`) + collision; kelompok
   over-merge 5 kategori (collision 1, wrong 2). Tidak perlu ekstrak
   `jenis_kegiatan` beneran.
2. **Alias mining otomatis = manual** (FST pair ditemukan persis, precision
   100%) — mekanisme siap utk data riil (mine → review → pakai).
3. **VERDICT FINAL KB**: jalur eksperimen tuntas. Aman (0 wrong, noise-safe,
   konflik aman, persistence, 3x confirm, normalisasi key 3→5, role terbaik,
   alias terotomasi) tapi **gain LLM call tidak terukur (saved 0) dan tidak
   akan terukur tanpa data baru** — KB bukan pipeline pemenang metrik
   efisiensi di korpus 74. Alat siap bila data muncul (`audit.py`, `alias.py`,
   `store.py`).
4. Fokus pencarian pipeline terbaik beralih ke **jalur akurasi** yang sudah
   terukur naik tanpa data baru (organizer v3+R6: 39.2%→54.1%, MACRO 61.2%).

---

## Frontier berikutnya (urutan saran) — menunggu keputusan user

1. **Jalur akurasi** (semua di `tests/`, terukur, produksi tetap zero-touch):
   - Port organizer v3+R6 (R0/R2/PREFIX_HELD/R6 KEEP, R1/R4 GUARD, R3/R5
     hapus) — pasca-port re-eval GT v9 + matcher v2 (ekspektasi organizer
     naik dari 39.2% produksi)
   - Scoring organizer_v2 (2160238 + salah_org/kosong 12 kasus)
   - Matcher v2.1 / alias bucket (12 kasus format)
2. **KB**: TUTUP — hanya dibuka kembali bila data baru tersedia (jalankan
   `tests/kb/audit.py` dulu).

## Frontier tertunda (sama dengan v24-v26)

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
| `tests/benchmark_kb_event.py` | KB-005 — event_type (12 kombinasi) |
| `tests/kb/alias.py` | KB-006 — alias mining + precision |
| `tests/benchmark_kb_alias.py` | KB-006 — dampak shadow hit |
| `tests/kb/key.py` | Key canonicalizer v1 + varian + events |
| `tests/kb/audit.py` | Alat gate data riil (siap pakai) |
| `docs/kb_history.md` | History + **Verdict Final jalur KB** |
| `docs/report/kb_event.md`, `kb_alias.md` | Report KB-005/006 |
| `docs/experiments_ledger.md` | KB-001..006 |
