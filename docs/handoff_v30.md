# Handoff v30 — KB-SCALE lengkap: peta hemat PASS, 2x confirm FAIL, akurasi+biaya PASS

> Supersedes `docs/handoff_v29.md`. Sesi ini = lanjutan pertanyaan "KB lebih
> efisien saat produksi besar?" — tiga eksperimen melengkapi bukti:
> **KB-SCALE-003** (peta hemat volume×keyspace×skew, GATE PASS), **KB-SCALE-004**
> (confirm 2x vs 3x + alias, GATE FAIL — 3x tetap wajib), **KB-SCALE-005**
> (akurasi & biaya end-to-end, GATE PASS — KB sekaligus menaikkan akurasi).

---

## Hasil sesi (committed: `09ebd29` + commit ini)

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. KB-SCALE-003 peta hemat (75 kombinasi, key sintetis zipf, routed 61% terukur) | 36k @80/20: **92% (1k key) / 78% (5k) / 72% (10k)** — semua ≥50%; volume kecil + keyspace besar rendah (500/10k = 35%) | **PASS** — asumsi kb_design layak dgn skew |
| 2. KB-SCALE-004 confirm 2x vs 3x + alias (korpus 74) | wrong 2x **304** vs 3x **284** (+20); hemat N=500 naik 24% vs 5% tapi tidak sebanding; alias efek tipis | **FAIL** — 3x confirm TETAP wajib |
| 3. KB-SCALE-005 akurasi & biaya end-to-end (nilai terukur: router 100%, KB serve 97.2%, LLM 58.6%) | 80/20 N=5000: akurasi **96.3% → 99.3%**, hemat biaya **87%** (57 vs 446 calls) | **PASS** |
| 4. QA | pytest **60 passed**; runs_summary + ledger + kb_history + handoff | DONE |

---

## Temuan penting sesi ini

1. **KB = cache yang LEBIH AKURAT dari LLM**: serve KB 97.2% vs LLM fallback
   58.6% (terukur). KB bukan cuma hemat biaya — menaikkan akurasi akhir
   (99.3% vs 96.3%) karena key populer = jawaban terverifikasi 3x.
2. **Peta hemat (SCALE-003)**: hemat berasal dari KEY POPULER (top-20% key
   menampung 80% request). Request/key rata-rata global MENYESATKAN: 36k/10k
   = 3.6 req/key rata-rata tetap hemat 72%. Volume kecil + keyspace besar =
   tidak layak (500/10k = 35%).
3. **2x confirm = hemat palsu**: wrong +20 (304 vs 284) — error pipeline
   terkunci lebih cepat. Konsisten KB-002 (1x = wrong 5). 3x wajib.
4. **Rangkaian KB-SCALE selesai**: 001 hemat 87% @produksi + 002 aman
   multi-worker + 003 peta keputusan + 004 3x wajib + 005 akurasi+biaya.

---

## Frontier berikutnya (urutan saran)

1. **Port produksi organizer v3+R6+format** (R0/R2/PREFIX_HELD/R6 + F1 alias
   map + F3 BEM FKM KEEP; R1/R4 GUARD; R3/R5 hapus) — re-eval GT v9 pasca-port.
2. **Fix GT v9 inkonsistensi** (FMIPA "dan" 2954933 vs ACTION; HIMA
   pendek/panjang) → GT v10 (butuh keputusan user) — membuka F2/HIMASTA.
3. **KB produksi**: bukti lengkap hemat 87% + akurasi +3pt + aman
   multi-worker (lock; PG tetap otoritas). Data riil → `tests.kb.audit` gate.
   Keputusan user: kapan (ada data riil?) & skema (PG, key role, confirm 3x).
4. **Scoring organizer_v2**: hanya bila data baru ATAU keputusan user rewrite
   extractor + re-baseline penuh.

### Peta dokumen (agar agent sesi berikutnya tidak salah alamat)

- **KB** (KB-001..006 Verdict Final + KB-SCALE-001..005) → `docs/kb_history.md`
  (naratif) + `docs/experiments_ledger.md` (ringkas) + `docs/report/kb_scale*.md`
  (angka: kb_scale, kb_scale_map, kb_scale_conf, kb_scale_e2e) +
  `docs/report/team_review_kb.md`/`team_review_kb.xlsx` (review tim, xlsx
  lokal — `*.xlsx` di-gitignore, bikin ulang via skill xlsx bila perlu).
- **ORG** (F1/ORG-003/F1C/ORG-004/ORG-005) → `docs/experiments_ledger.md` +
  `docs/report/report_data.json` → `scripts/generate_report.py`.
- **AKT** (AKT-001..005) → `docs/report/akt{1..5}_activity_*.md`.
- Jika eksperimen baru: ledger SELALU diisi; report_data.json HANYA eksperimen
  relevan perbandingan laporan (bukan probe/failed seperti ORG-005/KB-SCALE-004).

---

## File terkait sesi ini

| File | Keterangan |
|---|---|
| `tests/benchmark_kb_scale_map.py` | SCALE-003 (peta; key sintetis zipf) |
| `tests/benchmark_kb_scale_conf.py` | SCALE-004 (2x/3x + alias) |
| `tests/benchmark_kb_scale_e2e.py` | SCALE-005 (akurasi + biaya) |
| `docs/report/kb_scale_map.md` | Peta hemat (3 tabel skew) |
| `docs/report/kb_scale_conf.md` | Konfigurasi (verdict FAIL jujur) |
| `docs/report/kb_scale_e2e.md` | Akurasi + biaya (verdict PASS) |
| `docs/kb_history.md` | Entri SCALE-003/004/005 (naratif) |
| `docs/experiments_ledger.md` | SCALE-003 PASS + SCALE-004 FAIL + SCALE-005 PASS |
| `docs/report/runs_summary.md/csv` | + 3 run kb_scale_* |

---

## Gotchas sesi ini

- `replay_workload` (SCALE-001) menghitung `hits` utk SEMUA request (routed +
  non-routed) — jangan pakai `hits` utk akurasi end-to-end; SCALE-005 pakai
  `saved`/`non_routed_miss` saja (double-count bug ditemukan & diperbaiki).
- Angka terukur korpus (0 LLM runtime): router 100% (45/45 routed), LLM
  tingkat 58.6% (17/29 non-routed, extracted_fields v9), token/call 176 (v9).
- SCALE-003/005 pakai key sintetis/assumsi — dilaporkan eksplisit sbg
  proyeksi; SCALE-004 = korpus murni (bukti paling kuat).
- Konfigurasi final KB produksi: **confirm 3x wajib** (2x = wrong +20),
  key role (KB-005), alias opsional di data riil.
