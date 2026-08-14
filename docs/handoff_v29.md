# Handoff v29 — KB-SCALE (efisiensi saat produksi besar): simulasi workload skew PASS + race multi-worker PASS

> Supersedes `docs/handoff_v28.md`. Sesi ini menjawab pertanyaan user: "KB
> lebih efisien saat scale produksi besar?" — jalur KB sempat ditutup (Verdict
> Final v27: saved_llm=0 di korpus 74 seragam), tapi 2 dimensi produksi belum
> pernah diuji: **workload skewed** (hemat LLM) dan **race multi-worker**
> (keamanan tulis). Dua eksperimen baru: **KB-SCALE-001** (simulasi workload,
> GATE PASS di volume produksi) dan **KB-SCALE-002** (race + fix lock, PASS).

---

## Hasil sesi (committed: `c352f6f` + commit ini)

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. KB-SCALE-001 `tests/benchmark_kb_scale.py` — simulasi workload skew (N=500/5000, 80/20 dsb, replay ROUTER→KB→LLM, 0 LLM) | **N=5000 80/20: saved 87% (391/448), hit 97%, wrong 2.8%**; N=500: saved 12% (FAIL volume kecil) | **GATE PASS** (80/20, N=5000) |
| 2. KB-SCALE-002 race multi-worker — lock `threading.Lock` di `tests/kb/kb.py` | 8 thread × 500 write: confirms == 4000; 20 key deterministik; tanpa lock test gagal (lost update) | **PASS** |
| 3. QA | pytest **60 passed** (termasuk 2 test concurrency baru); runs_summary + ledger + kb_history + handoff | DONE |

---

## Temuan penting sesi ini

1. **KB hemat LLM = fungsi request per key, bukan ukuran korpus.** N=5000 +
   skew 80/20 → 87% request non-routed dijawab KB (warmup 3x terbayar). N=500
   → 12% (warmup menelan porsi). Produksi 36k request / 1-10k key unik
   (kb_design.md) berada di tengah — layak bila request/key tinggi.
2. **Gate lama v27 tidak dibatalkan**: saved_llm=0 berlaku utk korpus 74
   seragam; KB-SCALE = proyeksi pola (synthetic, SEED=42), bukan bukti
   distribusi riil. Gate data riil tetap `uv run python -m tests.kb.audit`
   lintas fakultas.
3. **Wrong 2.8% (N=5000) = warisan error pipeline, bukan kesalahan KB**: key
   populer cenderung benar → error serve KB lebih rendah dari pipeline
   offline (~19% tingkat). KB tidak memperkenalkan error baru.
4. **Race multi-worker nyata**: tanpa lock, `confirms` lost-update → entry tak
   pernah authoritative walau 3x. Lock global cukup di skala ini (ponytail:
   per-key bila profiling butuh).

---

## Frontier berikutnya (urutan saran)

1. **Port produksi organizer v3+R6+format** (R0/R2/PREFIX_HELD/R6 + F1 alias
   map + F3 BEM FKM KEEP; R1/R4 GUARD; R3/R5 hapus) — re-eval GT v9 pasca-port.
2. **Fix GT v9 inkonsistensi** (FMIPA "dan" 2954933 vs ACTION; HIMA
   pendek/panjang) → GT v10 (butuh keputusan user) — membuka F2/HIMASTA
   yang sekarang dilarang.
3. **KB produksi**: bila data riil datang → `tests.kb.audit` (gate: repeated
   keys, collision, saved_llm). KB-SCALE memberi parameter: request/key ≥ ~10
   + skew → hemat 50%+; multi-worker aman (lock; PG tetap otoritas).
4. **Scoring organizer_v2**: hanya bila data baru ATAU keputusan user rewrite
   extractor + re-baseline penuh.

### Peta dokumen (agar agent sesi berikutnya tidak salah alamat)

- **KB** (KB-001..006 Verdict Final + KB-SCALE-001/002) → `docs/kb_history.md`
  (naratif) + `docs/experiments_ledger.md` (ringkas) + `docs/report/kb_scale.md`
  (angka) + `docs/report/team_review_kb.md`/`team_review_kb.xlsx` (review tim,
  xlsx lokal — `*.xlsx` di-gitignore, bikin ulang via skill xlsx bila perlu).
- **ORG** (F1/ORG-003/F1C/ORG-004/ORG-005) → `docs/experiments_ledger.md`
  (ledger) + `docs/report/report_data.json` (laporan resmi: org_002_f1 +
  org_003_v3 + org_004_format) → `scripts/generate_report.py` (docx/md/xlsx).
- **AKT** (AKT-001..005 nama_kegiatan) → `docs/report/akt{1..5}_activity_*.md`.
- Jika eksperimen baru: ledger SELALU diisi; report_data.json HANYA eksperimen
  relevan perbandingan laporan (bukan probe/failed seperti ORG-005).

---

## File terkait sesi ini

| File | Keterangan |
|---|---|
| `tests/benchmark_kb_scale.py` | KB-SCALE-001 (simulasi skew; `KB_SCALE_N` env utk volume) |
| `tests/test_kb_scale_concurrency.py` | KB-SCALE-002 (2 test race) |
| `tests/kb/kb.py` | + `threading.Lock` (write/lookup/peek) |
| `docs/report/kb_scale.md` | Report KB-SCALE-001 (angka + gate + interpretasi) |
| `docs/kb_history.md` | Entri KB-SCALE-001/002 (naratif) |
| `docs/experiments_ledger.md` | KB-SCALE-001 PASS + KB-SCALE-002 PASS |
| `docs/report/runs_summary.md/csv` | + run `kb_scale_*` (kind kb_scale) |
| `scripts/generate_runs_summary.py` | + kind `kb_scale` |

---

## Gotchas sesi ini

- `random.Random(SEED)` dibagi antar varian di `main()` — hasil deterministik
  per SEED; jangan ganti SEED saat membandingkan varian.
- `alpha_for_skew` binary-search alpha (1.0-8.0) agar top-20% key menampung
  target ratio — alpha 3.12 = 80/20 di key space ini.
- Metrik: `saved_llm` = hit request NON-routed; `non_routed_total` =
  non_routed_miss + saved (jangan salah pakai miss saja utk pct).
- KB-SCALE-002: mutasi `WARMUP_CONFIRMS` via `import tests.kb.kb as kbimpl`
  (bukan `from tests import kb`) — pola lama, lihat KB-001 koreksi protokol.
