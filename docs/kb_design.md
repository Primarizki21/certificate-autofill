# KB Design — Organizer/Event Tingkat Knowledge Base (opsi B)

> Status: desain final (keputusan user sesi v19, handoff v20) + prototipe replay
> (F3 `tests/benchmark_kb_warmup.py`) + **KB-001 shadow v1** (`tests/kb/key.py` +
> `tests/benchmark_kb_shadow.py`, 2026-08-11) + **KB-SCALE-001..005** (2026-08-14,
> `docs/report/kb_scale*.md`) + **semantik produksi KB-PROD-001** (`tests/kb/kb.py`
> `servable`/`resolve`/`audit_due`, 2026-08-14, handoff v36). Produksi **belum**
> disentuh. Perkembangan naratif: `docs/kb_history.md`.

## 1. Key — opsi B: komposit `(normalized_organizer, event_type)`

| | A (organizer saja) | **B (organizer + tipe kegiatan)** | C (fingerprint teks) |
|---|---|---|---|
| Risiko salah-kontek | tinggi | rendah | minimal |
| Kompleksitas | paling sederhana | sedang | paling kompleks |
| Generalisasi | tingkat saja | tingkat + siap F4 | short-circuit semua field |

- B dipilih: risiko salah-propagasi jauh lebih kecil dari A, jauh lebih sederhana
  dari C (C rawan OCR noise). Upgrade ke C untuk F4 nanti.
- **Key v1 (KB-001)**: `(normalized_organizer_v3, normalized_role, KEY_VERSION)`.
  - Organizer: `_norm_organizer_v3` (R0-R6). Port produksi pakai set KEEP OOD-003.
  - Role: `map_jabatan` → kategori stabil (Peserta/Panitia/Ketua/...) — menaikkan
    repeat-key vs raw_role mentah (F3: 2 → KB-001: 3 di 74 cert).
  - `KEY_VERSION` dibawa DALAM key: normalizer berubah → entry lama tak tercampur.
  - Role/organizer kosong → tidak lookup/tulis.
- **`event_type` di pipeline saat ini**: `jenis_kegiatan` (FORM_OPTIONS) tidak
  diekstrak; v1 memakai `role` sebagai proxy. Keputusan terbuka (bawah).

## 2. Storage production — PostgreSQL (bukan graph DB)

- **Angka terukur**: 74 cert → 56 organizer unik (top BEM FTMM 7×). Proyeksi
  produksi 36k request: 1.000–10.000 unik (15 fakultas × BEM/HIMA/UKM + event
  tahunan). **Asumsi wajib divalidasi** dengan sampling data riil lintas
  fakultas sebelum arsitektur final.
- **Kenapa PG**: point lookup = kecepatan imbang vs graph (O(log n) sub-ms di
  ribuan baris); PG sudah di stack, transaksi + FK + audit SQL natural;
  Neo4j = server tambahan (JVM/RAM) tanpa keuntungan di skala ini.
- **Index**: composite primary key `(normalized_organizer, event_type)` =
  B-tree otomatis. Index `source`/`last_verified_at` hanya kalau query audit
  lambat. Redis = hanya kalau profiling menunjukkan butuh (jangan dulu).
- **Migrasi masa depan murah** (LOAD CSV) — data berbentuk node/edge sederhana.

### Skema (tabel baru, bukan replace `models.py` — flag `ENABLE_*` saat promosi)

```
organizer_tingkat_kb
- normalized_organizer   text  (PK, komposit)
- role                   text  (PK, komposit; = event proxy, KB-005 — TIDAK perlu event_type)
- tingkat                text
- confidence             float
- source                 enum (router_rule | llm | human_review)
- hit_count              int
- confirms               int   (warm-up: perlu >=3 sebelum authoritative)
- last_verified_at       timestamp
- created_from_cert_id   text  (traceability)
```

> **KB-005 (keputusan desain #1)**: `role` (via `map_jabatan`) = satu-satunya
> event yang collision 0 & aman. `jenis_kegiatan` tidak diekstrak pipeline
> (70% key mati), `kelompok_kegiatan` over-merge (collision 1, wrong 2).
> Skema produksi memakai `role`, bukan `event_type`.

## 3. Runtime flow (extend Stage 5, sebelum router)

KB hanya decision cache field `tingkat` (organizer/OCR tidak disentuh).
**Alur v1: ROUTER → KB → LLM** (revisi dari draft awal KB-first — key sama
bisa beda konteks lomba/seminar, router sudah divalidasi 100% precision):

```
Stage 5 Router (13+ rule, precision >=95%)
  → rule hit        → pakai router, WRITE/confirm KB (source=router_rule)
  → rule miss       → KB lookup (O(1), zero token)
       → hit & authoritative → pakai KB, WRITE/confirm (source=router_rule|llm)
       → miss / belum auth / konflik → Stage 6 LLM fallback
             → LLM hasil → WRITE/confirm KB (source=llm)
                           → tetap needs_review bila confidence < threshold
```

Lookup exact-match saja — tanpa fuzzy (fuzzy = risiko salah-propagasi).

## 4. Mitigasi risiko

- **Salah propagate ke ribuan mahasiswa** → audit sampling: X% KB hit direview
  manual per batch (protokol F0). Entry `source=llm` diaudit lebih sering.
  **KB-PROD-001**: `TingkatKB.audit_due()` (prototipe) = sampling entry
  source=llm + conflicts>0 utk review manual.
- **Warm-up**: 2-3 konfirmasi konsisten sebelum authoritative (prototipe:
  `WARMUP_CONFIRMS=3`); jangan trust 1 hit.
- **Propagasi router-salah / LLM kurang tepercaya** → **KB-PROD-001**:
  `servable()` source-aware — threshold per source
  (`AUTHORITATIVE_CONFIRMS = {router_rule: 3, llm: 5, human_review: 1}`).
  LLM label butuh bukti lebih banyak sebelum dipakai autofill.
  (`authoritative` lama tetap dipakai eksperimen KB-001..006/SCALE; produksi
  wajib cek `servable`.)
- **Entry basi (event berubah antar tahun)** → **KB-PROD-001**: `servable()`
  cek `last_verified_at` dalam `TTL_DAYS` (default 365); entry lewat TTL =
  non-servable → di-refresh via LLM/human.
- **Collision** (key sama, tingkat beda): **sudah diimplementasi KB-001** —
  `write()` konflik → `conflicts += 1`, nilai asli dipertahankan, entry
  non-authoritative permanen (sampai human review). Tidak pernah autofill dari
  entry konflik. **KB-PROD-001**: `TingkatKB.resolve()` = jalur human review —
  entry konflik bisa di-resolve (source=human_review, conflicts=0, langsung
  servable). Tanpa resolve, entry konflik mati selamanya.
- `hit_count`, `last_verified_at`, `created_from_cert_id` untuk traceability.
  Catatan: `hit_count` per lookup = write contention di produksi → counter
  batch/queue saat promosi.
- **Concurrency multi-worker (api + db_worker)** → SCALE-002: `threading.Lock`
  validasi semantik in-memory. **Produksi WAJIB DB atomic upsert**
  (`INSERT ... ON CONFLICT (normalized_organizer, role)
  DO UPDATE SET confirms = CASE WHEN ... END`), bukan lock Python (per-proses).

## 5. Hasil prototipe

### F3 — replay warm-up (`tests/kb/kb.py` + `benchmark_kb_warmup.py`)

| Konfig | N warm-up | Hit (eval) | LLM calls (no-KB 31) | Tingkat exact (eval) | Collision |
|---|---|---|---|---|---|
| 1x confirm | 10/20/37 | 2 (3%) | 29 (−2) | 84.4/81.5/81.1% | 0 |
| 3x confirm | 10/20/37 | 2 (3%) | 29 (−2) | 84.4/81.5/81.1% | 0 |

- Mekanisme bekerja, tapi korpus 74 hanya punya **2 key berulang** (raw_role)
  → gain nyata baru di skala besar. Detail: `docs/report/f3_kb_warmup.md`.

### KB-001 — shadow v1 (key v1 + alur router→KB→LLM)

| Konfig | Warm N | Hit | Saved LLM | Disagree | Wrong | Konflik | Tingkat exact pipe |
|---|---|---|---|---|---|---|---|
| 1x/3x confirm | 10/20/37 | 3 | 0 | 0 | 0 | 0 | 84.4/81.5/83.8% |

- Key unik 55, **key berulang 3 (9 cert)** — normalisasi role menaikkan repeat
  vs F3. `saved_llm = 0`: key berulang semuanya cert yang router putuskan →
  di korpus ini KB tidak menghemat LLM call.
- `shadow_disagree`/`wrong_hits` = 0 semua konfig + noise OCR 10/25/50% (wrong 0)
  → adopsi KB tidak mengubah hasil pipeline (no-regress) & aman di noise.
- Detail: `docs/report/kb_shadow.md`. **Implikasi**: bukti gain tetap menunggu
  sampling data riil lintas fakultas (asumsi unique organizer 1.000–10.000).

## 6. Keputusan terbuka (belum dieksekusi)

1. ~~Pipeline perlu ekstrak `jenis_kegiatan` (event_type presisi) atau cukup role?~~
   **RESOLVED (KB-005)**: role proxy cukup & paling aman — TIDAK ekstrak
   `jenis_kegiatan`; skema pakai `role` (lihat §2).
2. **Sampling data riil unique organizer lintas fakultas** = prasyarat gate
   produksi (korpus 74: hanya 3 key berulang). Bisa paralel. **TERTUNDA — data
   riil belum tersedia (2026-08-14)**.
3. Prototipe `tests/kb/` → tabel `models.py` + flag `ENABLE_KB_TINGKAT` hanya
   saat promosi produksi (keputusan user, masih jauh).
4. ~~Konfig 1x vs 3x confirm identik di korpus ini~~ **RESOLVED (KB-SCALE-004)**:
   3x wajib (2x = wrong +20). Threshold per-source: `AUTHORITATIVE_CONFIRMS`.
