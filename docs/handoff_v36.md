# Handoff v36 — KB-PROD-001: semantik produksi KB (servable/resolve/audit_due)

> Supersedes `docs/handoff_v35.md`. Sesi ini = jawaban "KB sudah selesai?
> ada yang bisa diperbaiki utk produksi?" → **eksperimen KB selesai**; yang
> dikerjakan = gap produksi yang EKSPERIMEN tak bisa jawab, di prototipe
> (`tests/kb/`, **produksi zero-touch**). Gate data riil TERTUNDA (belum ada).

---

## Hasil sesi

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. Stage 0: `kb_design.md` — keputusan #1/#4 RESOLVED (KB-005: role cukup; SCALE-004: 3x wajib), skema `event_type`→`role`, §4 gap produksi | Dokumen sinkron dgn kode | DONE |
| 2. Stage 1: `kb.py` — `servable()` (source-aware + TTL), `resolve()`, `audit_due()` | `authoritative` TIDAK diubah → eksperimen lama valid | DONE |
| 3. `test_kb_production_semantics.py` (4 test) + demo asserts | Pytest **60 → 64 passed**, 0 regress | DONE |
| 4. Docs: ledger KB-PROD-001 + kb_history + handoff v36 | DONE | DONE |

---

## Temuan penting sesi ini

1. **Eksperimen KB selesai** (KB-001..006 + SCALE-001..005 + Verdict Final).
   Yang tersisa utk produksi BUKAN eksperimen: 1 gate data riil (tertunda) +
   engineering (PG atomic upsert, counter batch, verifikasi token) + semantik
   yang baru ter-kode di KB-PROD-001.
2. **Gap semantik yang dijawab KB-PROD-001**:
   - **llm label kurang tepercaya** → `servable()` source-aware:
     `AUTHORITATIVE_CONFIRMS = {router_rule: 3, llm: 5, human_review: 1}`.
     Eksperimen lama cek `entry.authoritative` (threshold seragam 3) — angka
     KB-001..006/SCALE tetap valid. **Produksi wajib cek `servable`, bukan
     `authoritative`.**
   - **Entry konflik mati selamanya** → `resolve(key, tingkat, reviewer)`:
     human review = source=human_review, conflicts=0, servable langsung.
   - **Entry basi antar tahun** → TTL: `servable(ttl_days=365)`; lewat batas
     = non-servable → di-refresh via LLM/human.
   - **Sampling F0** → `audit_due()`: prioritas source=llm + conflicts>0,
     urut last_verified_at paling lama.
3. **Bug saat iterasi**: `servable()` awal cek `authoritative` dulu →
   human_review confirms=1 tak pernah servable. Fix: `servable` hitung
   sendiri (conflicts==0 + threshold per-source + TTL).
4. **Keputusan desain yang TERTUTUP di sesi ini (bukan eksperimen baru)**:
   KB-005 → `role` = event proxy, skema produksi pakai `role` (bukan
   `event_type`); SCALE-004 → 3x confirm wajib (2x = wrong +20).

---

## Frontier berikutnya (urutan saran)

1. **Gate data riil (TERTUNDA — belum ada data)**: sampling unique organizer
   lintas fakultas → `uv run python -m tests.kb.audit --dir <dir_data_riil>`.
   Go/no-go final. Sampai ada, JANGAN port produksi.
2. **Port produksi KB** (setelah gate + approval user): tabel
   `organizer_tingkat_kb` di `models.py` + flag `ENABLE_KB_TINGKAT` default
   OFF + PG atomic upsert (`INSERT ... ON CONFLICT (normalized_organizer,
   role) DO UPDATE SET confirms = CASE ...`) ganti `threading.Lock` +
   `servable`/`resolve`/`audit_due` sebagai service layer + hit_count counter
   batch + ukur ulang tok/call path produksi `llm_tingkat.py` (f_bias,
   bukan 176 v9).
3. **R1/R4 + GUARD F6** (organizer 63.5→66.2%) — independen dari KB.
4. **GT v10** (inkonsistensi terkumpul v35).

### Peta dokumen

- **KB** (KB-001..006 + SCALE-001..005 + KB-PROD-001) → `docs/kb_history.md`
  + `docs/experiments_ledger.md` + `docs/report/kb_scale*.md` +
  `docs/kb_design.md` (status & keputusan terbuka) + `docs/report/team_review_kb.md`.
- Jika eksperimen baru: ledger SELALU diisi; report_data.json HANYA eksperimen
  relevan laporan (KB-PROD-001 = prototipe, bukan laporan metrik).

---

## File terkait sesi ini

| File | Keterangan |
|---|---|
| `tests/kb/kb.py` | + `servable()` (source-aware + TTL), `resolve()`, `audit_due()`; `authoritative` tetap |
| `tests/test_kb_production_semantics.py` | Baru — 4 test KB-PROD-001 |
| `docs/kb_design.md` | §4 gap produksi + §6 keputusan #1/#4 RESOLVED + skema role |
| `docs/experiments_ledger.md` | + KB-PROD-001 |
| `docs/kb_history.md` | + entri KB-PROD-001 |

---

## Gotchas sesi ini

- `servable()` != `authoritative`: authoritative = legacy (threshold seragam
  WARMUP_CONFIRMS); servable = produksi (per-source + TTL). Jangan ganti
  `authoritative` — benchmark_kb_scale/seed/shadow + test concurrency
  bergantung padanya.
- `resolve()` pada key BARU = bootstrap human (KBEntry baru langsung
  servable) — berguna utk seeding manual sebelum warmup alami.
- TTL default 365 hari; `servable(ttl_days=None)` = tanpa batas (dipakai
  benchmark utk tidak terpengaruh waktu).
- Pytest sekarang **64 passed**.
