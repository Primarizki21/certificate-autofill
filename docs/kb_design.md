# KB Design — Organizer/Event Tingkat Knowledge Base (opsi B)

> Status: desain final (keputusan user sesi v19, handoff v20) + hasil prototipe
> replay (`tests/benchmark_kb_warmup.py`). Produksi **belum** disentuh.

## 1. Key — opsi B: komposit `(normalized_organizer, event_type)`

| | A (organizer saja) | **B (organizer + tipe kegiatan)** | C (fingerprint teks) |
|---|---|---|---|
| Risiko salah-kontek | tinggi | rendah | minimal |
| Kompleksitas | paling sederhana | sedang | paling kompleks |
| Generalisasi | tingkat saja | tingkat + siap F4 | short-circuit semua field |

- B dipilih: risiko salah-propagasi jauh lebih kecil dari A, jauh lebih sederhana
  dari C (C rawan OCR noise). Upgrade ke C untuk F4 nanti.
- **event_type di pipeline saat ini**: `jenis_kegiatan` (FORM_OPTIONS) tidak
  diekstrak; prototipe memakai `role` (`extract_role`) sebagai proxy. Sebelum
  produksi, putuskan apakah pipeline perlu mengekstrak `jenis_kegiatan` beneran
  (untuk key yang lebih presisi) — keputusan ini memengaruhi schema.

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

```
KB lookup (O(1), zero token)
  → hit & authoritative  → pakai hasil KB
  → miss / belum auth    → Stage 5 Router (13+ rule)
       → rule hit        → pakai router, WRITE/confirm KB (source=router_rule)
       → rule miss       → Stage 6 LLM fallback
             → LLM hasil → WRITE/confirm KB (source=llm)
                           → tetap needs_review bila confidence < threshold
```

## 4. Mitigasi risiko

- **Salah propagate ke ribuan mahasiswa** → audit sampling: X% KB hit direview
  manual per batch (protokol F0). Entry `source=llm` diaudit lebih sering.
- **Warm-up**: 2-3 konfirmasi konsisten sebelum authoritative (prototipe:
  `WARMUP_CONFIRMS=3`); jangan trust 1 hit.
- **Collision** (key sama, tingkat beda): prototipe replay = 0 di 74 cert;
  di data besar, entry conflict → downgrade ke non-authoritative + flag review.
- `hit_count`, `last_verified_at`, `created_from_cert_id` untuk traceability.

## 5. Hasil prototipe replay (`tests/kb/kb.py` + `benchmark_kb_warmup.py`)

| Konfig | N warm-up | Hit (eval) | LLM calls (no-KB 31) | Tingkat exact (eval) | Collision |
|---|---|---|---|---|---|
| 1x confirm | 10/20/37 | 2 (3%) | 29 (−2) | 84.4/81.5/81.1% | 0 |
| 3x confirm | 10/20/37 | 2 (3%) | 29 (−2) | 84.4/81.5/81.1% | 0 |

- **Mekanisme bekerja** (KB menggantikan router+LLM pada key berulang), tapi di
  korpus 74 hanya **2 key berulang** → gain nyata baru di skala besar.
- Tingkat exact eval ≈ pipeline (selisih = variasi subset, bukan regress KB).
- **Implikasi**: validasi asumsi unique organizer (1.000–10.000) dengan sampling
  data riil lintas fakultas = prasyarat keputusan arsitektur final. Kalau asumsi
  benar, KB bounded (LLM call ~ unique organizer baru/period), bukan proporsional
  request.

## 6. Keputusan terbuka (belum dieksekusi)

1. Pipeline perlu ekstrak `jenis_kegiatan` (event_type presisi) atau cukup role?
2. Sampling data riil unique organizer lintas fakultas (bisa paralel).
3. Prototipe `tests/kb/` → tabel `models.py` + flag `ENABLE_KB_TINGKAT` hanya
   saat promosi produksi (keputusan user, masih jauh).
