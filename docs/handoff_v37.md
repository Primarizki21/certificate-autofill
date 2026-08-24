# Handoff v37 — HYB-KB-001 & HYB-KB-002: KB × HYB, proyeksi skala ~360k request

> Supersedes `docs/handoff_v36.md`. Sesi ini = jawaban pertanyaan user:
> *"kalau mau KB masuk pipeline HYB, apakah harus masuk produksi dulu?
> bisa tetap di eksperimen tapi HYB + KB? sekalian scale sesuai kondisi
> ril ~360.000 request non-concurrent."*
> Jawaban: **tidak perlu produksi** — seluruh rangkaian KB sejak awal
> zero-touch produksi (`tests/kb/`, `tests/benchmark_kb_*.py`), dan HYB
> juga eksperimen. Keduanya dicampur di lapisan eksperimen.

---

## Hasil sesi

| Eksperimen | Pertanyaan | Hasil | Verdict |
|---|---|---|---|
| **HYB-KB-001** (`tests/benchmark_hyb_kb.py`, korpus 74, replay online ROUTER→KB→LLM, label dr artefak HYB-LLM-001 run 20260821_135619, 0 LLM runtime) | Apa efek KB di korpus? | Exact **60/74 = baseline persis**, wrong 0, saved_llm 0 (aritmetika: korpus cuma 3 key berulang ≤3 kemunculan; `servable()` butuh ≥4 kemunculan utk 1 hemat; label source=llm butuh 5 confirm), kb_size 55 | **PASS** (G1 no-regress, G2 wrong=0) |
| **HYB-KB-002** (`tests/benchmark_hyb_kb_scale.py`, N=360.000 NON-concurrent, horizon 1095 hari, key space {1k..50k} × skew {70–90%} × TTL {∞,365h}, profil key clone dr korpus) | Berapa hemat & dampak akurasi di skala ril? | **GATE PASS** @(keys 10k, 80/20, TTL ∞): hemat **86,4%** LLM calls (**101.446 / 117.349**), akurasi **86,2% → 89,5% (+3,3pp)**, ≈**42 jam** proses terhemat (1,5 s/call terukur) ≈ **17,9 jt token**; hemat grid penuh **72–98%**, akurasi naik di SEMUA kombinasi | **PASS** |

Detail lengkap: `docs/report/hyb_kb_scale.md` + `tests/benchmark_runs/hyb_kb_*/` + `hyb_kb_scale_*/`.

---

## Temuan penting sesi ini

1. **KB tidak perlu port produksi dulu.** Semantik yang dibutuhkan produksi
   (`servable()` source-aware + TTL, `resolve()`, `audit_due()`) sudah
   ter-kode sejak KB-PROD-001 dan bisa direplay/di-simulasikan langsung.
2. **Efek KB tidak terlihat di korpus 74 — dan itu konsisten** dengan
   F3-001/KB-001: gain KB proporsional terhadap key BERULANG. Nilainya
   baru muncul di skala (HYB-KB-002) atau data riil dengan organizer
   berulang lintas fakultas.
3. **Pelajaran arsitektur (wajib utk port produksi nanti): router SELALU
   menang.** Versi awal simulasi melayani KB untuk request ROUTED juga →
   akurasi jeblok ±10 pp (error turunan profil KB menimpa jawaban router
   @100%). Fix: KB hanya menggantikan LLM fallback pada cert unrouted.
   Ini memperkuat desain alur ROUTER→KB→LLM (bukan KB-first).
4. **TTL murah di workload skewed**: selisih hemat TTL 365 hari vs ∞ hanya
   ±0,1–0,2 pp — key populer selalu segar karena write tiap miss;
   key jarang memang hampir tak pernah di-hit. Model harness-side,
   `tests/kb/kb.py` tak disentuh.
5. **Rekonsiliasi baseline HYB-LLM**: summary runtime resmi = tingkat
   **62/74 (83,8%)**, LLM benar **17/26**. Artefak
   `per_cert_results.json` (file input sesi ini; penulisnya tidak ada di
   repo) memberi **60/74** & **15/26** dgn matcher current — dipakai
   sebagai bound konservatif. Bukan drift matcher (`matchers.py` terakhir
   berubah 5 Agu, sebelum run 21 Agu).
6. Non-concurrent berarti hemat call = hemat waktu proses berurutan.
   Race multi-worker sudah ditutup terpisah (KB-SCALE-002, lock).

---

## Frontier berikutnya (urutan saran)

1. **Gate data riil (TERTUNDA — belum ada data)**: sampling unique
   organizer lintas fakultas → `uv run python -m tests.kb.audit --dir <dir>`.
   Angka HYB-KB-002 adalah proyeksi berbasis profil korpus; angka final
   menunggu sampling ini. Sampai ada, JANGAN port produksi.
2. **Port produksi KB+HYB** (setelah gate + approval user): tabel
   `organizer_tingkat_kb` di `models.py` + flag `ENABLE_KB_TINGKAT`
   default OFF + PG atomic upsert + service layer
   `servable()/resolve()/audit_due()` + urutan ROUTER→KB→LLM (temuan #3)
   + ukur ulang tok/call path produksi.
3. R1/R4 + GUARD F6 (organizer 66,2%, independen KB).
4. GT v10 (inkonsistensi terkumpul handoff v35).

### Peta dokumen

- **HYB-COMBINED/HYB-LLM**: ledger + `docs/report/hyb_llm_pipeline.md`.
- **HYB-KB**: ledger (2 entri baru) + `docs/report/hyb_kb_scale.md` +
  handoff ini.
- **KB lineage**: `docs/kb_history.md` + `docs/kb_design.md`.

---

## File terkait sesi ini

| File | Keterangan |
|---|---|
| `tests/benchmark_hyb_kb.py` | Baru — replay korpus ROUTER→KB→LLM (HYB-KB-001) |
| `tests/benchmark_hyb_kb_scale.py` | Baru — proyeksi skala 360k (HYB-KB-002); `KB_SCALE_N` env override |
| `docs/report/hyb_kb_scale.md` | Auto-generated oleh benchmark skala |
| `docs/experiments_ledger.md` | + HYB-KB-001, HYB-KB-002 |
| `docs/kb_history.md` | + entri HYB-KB |

---

## Gotchas sesi ini

- Pytest dari root butuh `PYTHONPATH=. uv run pytest tests/` — tanpa itu
  3 modul test gagal koleksi (`No module named 'tests'`, pre-existing).
  Suite: **64 passed** (= handoff v36, 0 regress).
- `benchmark_hyb_kb_scale.py` membaca artefak
  `hyb_llm_20260821_135619/per_cert_results.json`; ganti artefak →
  router share & llm_acc ikut berubah (dihitung live, bukan hardcode).
- `alpha_for_skew` menerima freq apa pun >0, tapi dgn base freq zipf
  hasilnya beda makna vs freq uniform — jangan bandingkan alpha antar
  benchmark secara langsung.
- Edit file paralel/stale-anchor dua kali merusak struktur fungsi di
  sesi ini — selalu re-read setelah edit yang warning "stale".
