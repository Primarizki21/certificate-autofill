# KB Design — Organizer/Event Tingkat Knowledge Base (opsi B)

> Status: desain final (keputusan user sesi v19, handoff v20) + prototipe replay
> (F3 `tests/benchmark_kb_warmup.py`) + **KB-001 shadow v1** (`tests/kb/key.py` +
> `tests/benchmark_kb_shadow.py`, 2026-08-11). Produksi **belum** disentuh.
> Perkembangan naratif: `docs/kb_history.md`.

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
- event_type             text  (PK, komposit; NULL = tidak tahu)
- tingkat                text
- confidence             float
- source                 enum (router_rule | llm | human_review)
- hit_count              int
- confirms               int   (warm-up: perlu >=3 sebelum authoritative)
- last_verified_at       timestamp
- created_from_cert_id   text  (traceability)
```

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
- **Warm-up**: 2-3 konfirmasi konsisten sebelum authoritative (prototipe:
  `WARMUP_CONFIRMS=3`); jangan trust 1 hit.
- **Collision** (key sama, tingkat beda): **sudah diimplementasi KB-001** —
  `write()` konflik → `conflicts += 1`, nilai asli dipertahankan, entry
  non-authoritative permanen (sampai human review). Tidak pernah autofill dari
  entry konflik.
- `hit_count`, `last_verified_at`, `created_from_cert_id` untuk traceability.
  Catatan: `hit_count` per lookup = write contention di produksi → counter
  batch/queue saat promosi.

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

1. Pipeline perlu ekstrak `jenis_kegiatan` (event_type presisi) atau cukup role?
   (KB-001 memakai role proxy; keputusan memengaruhi schema)
2. **Sampling data riil unique organizer lintas fakultas** = prasyarat gate
   produksi (korpus 74: hanya 3 key berulang). Bisa paralel.
3. Prototipe `tests/kb/` → tabel `models.py` + flag `ENABLE_KB_TINGKAT` hanya
   saat promosi produksi (keputusan user, masih jauh).
4. Konfig 1x vs 3x confirm identik di korpus ini (tak ada key ter-confirm >1x)
   — validasi ulang di data riil.
