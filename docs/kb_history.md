# KB History — Perkembangan Knowledge Base Tingkat

> **Tujuan:** history kronologis pembuatan KB tingkat (decision cache) — alasan,
> keputusan, angka, dan next action. Commit hanya bukti kode; file ini sumber
> kebenaran naratif agar agent berikutnya tidak mengulang atau salah asumsi.
>
> - Desain arsitektur terkini: `docs/kb_design.md`
> - Status PASS/FAIL ringkas: `docs/experiments_ledger.md` (ID `KB-*`/`F3-*`)
> - Detail benchmark: `docs/report/f3_kb_warmup.md`, `docs/report/kb_shadow.md`
> - Registry angka: `docs/report/runs_summary.md`

## Format entri (wajib — satu per eksperimen/keputusan)

```text
ID | Tanggal | Konteks (handoff/ledger)
Hipotesis / Keputusan
Dataset & konfigurasi
Perubahan kode (file)
Hasil terukur
Gate / Verdict
Risiko
Commit terkait
Next action
```

---

## KB-002 | 2026-08-11 | seeded persistent KB (ceiling human-seed + persistence)

**Hipotesis.** KB yang SUDAH terisi knowledge terverifikasi (seed human_review)
aman (0 wrong) dan persisten (snapshot JSON identik antar-run); dan 1x confirm
(yang tadinya tidak teruji karena bug konfig) tidak aman.

**Koreksi KB-001/F3.** Mutasi `WARMUP_CONFIRMS` lewat package namespace
(`from tests import kb as kbmod`) TIDAK mengubah module `tests.kb.kb` — konfig
"1x" di F3-001 & KB-001 sebenarnya jalan dengan default 3x. Kesimpulan keduanya
tetap valid (3x = 0 wrong); angka "1x" yang dilaporkan = 3x. Fix:
`import tests.kb.kb as kbimpl` (module langsung).

**Dataset & konfigurasi.** 74 cert, GT v9 + matcher v2, pipeline run v9 + router
CURRENT, 0 LLM runtime. Seed = GT cert pertama utk key berulang (freq≥2,
source human_review, authoritative segera). Noise 25%. Persist configs:
1x/N=10 & 3x/N=20.

**Perubahan kode.**
- `tests/kb/store.py` (baru) — save/load JSON + key_version check + round-trip.
- `tests/kb/kb.py` — `items()` utk snapshot.
- `tests/benchmark_kb_seed.py` (baru) — smoke + ceiling + noise + persist + fragmentasi.
- Fix konfig di `benchmark_kb_shadow.py` + `benchmark_kb_warmup.py`.

**Hasil terukur.**
- Smoke: seed human_review authoritative langsung; konflik → non-auth (nilai
  asli utuh); key ber-noise → miss; round-trip identik.
- Ceiling seeded: 3 seed keys / 9 certs, hit 9, **saved_llm 0**, wrong 0,
  disagree 0. Noise 25%: hit 9, wrong 0.
- Persistence: mem == persist identik (1x: 51 hit / 13 saved / **5 wrong**;
  3x: 3 hit / 0 saved / 0 wrong).
- Fragmentasi: FST DEPT = 1 org logis terpecah 2 key (7 cert) → exact-match
  kehilangan hit (key "SYSTEMS" vs "SYSTEM").

**Gate / Verdict.** **PASS** — G1 round-trip identik, G2 seeded wrong 0
(+noise), G3 persist == mem, G4 saved_llm jujur. Temuan kunci: **1x confirm =
GATE FAIL precision** (error LLM label terkunci, wrong 5) → warm-up ≥3 wajib;
seeded ceiling saved 0 → korpus 74 tetap pembatas.

**Risiko.**
- Fragmentasi key = kerugian hit yang terukur (7 cert di 1 org) — kandidat
  normalisasi key case/punct/stem ATAU alias table saat produksi (hati-hati:
  over-merge = collision baru).
- `hit_count` per lookup (write contention) — counter batch di produksi.

**Commit terkait.** (commit sesi ini)

**Next action.**
1. Sampling data riil lintas fakultas (repeat key & collision) — gate utama.
2. Keputusan: normalisasi key lanjutan (fragmentasi) vs alias table.
3. Keputusan user: `jenis_kegiatan` beneran utk key (schema produksi).
4. `report_data.json` — butuh keputusan user (preseden v23/v24).

---

## KB-001 | 2026-08-11 | shadow replay key v1 (alur router → KB → LLM)

**Hipotesis.** Key v1 `(organizer v3+R6, role map_jabatan, KEY_VERSION)` menaikkan
repeat-key vs F3 (raw_role), dan shadow replay membuktikan adopsi KB tidak
mengubah hasil pipeline (no-regress) + aman terhadap OCR noise.

**Keputusan desain (sesi ini, sesuai plan user).**
- Alur produksi target: `router → KB → LLM` (bukan KB-first dari kb_design v1).
- Key: `(normalized_organizer_v3, normalized_role, KEY_VERSION)` — role
  dinormalisasi via `map_jabatan` (kategori stabil), versi dibawa dalam key.
- Role/organizer kosong → TIDAK lookup, TIDAK tulis.
- Konflik (key sama, tingkat beda) → entry non-authoritative permanen, nilai
  asli dipertahankan (tidak ditimpa diam-diam).
- KB hanya mengubah field `tingkat`. OCR/organizer tidak disentuh.

**Dataset & konfigurasi.** 74 cert, GT v9 + matcher v2, pipeline label = run v9
(`extracted_fields.csv`) + router CURRENT, 0 LLM runtime. Warm-up N = 10/20/37
urutan deterministik (sorted-stem). Konfig 1x vs 3x confirm. Noise OCR 10/25/50%.

**Perubahan kode.**
- `tests/kb/kb.py` — `conflicts` pada KBEntry; `write()` konflik → non-authoritative; `peek()` non-mutating.
- `tests/kb/key.py` (baru) — canonicalizer key v1.
- `tests/benchmark_kb_shadow.py` (baru) — shadow replay + safety noise.

**Hasil terukur.**
- Key unik 55, key berulang **3 (9 cert)** vs F3: 2 (raw_role) → normalisasi
  role menaikkan repeat, tapi korpus tetap membatasi.
- Hit 3 (semua exact vs GT), `saved_llm = 0`: semua key berulang di cert yang
  router sudah putuskan → alur router-first menghemat 0 LLM call di korpus ini.
- `shadow_disagree = 0`, `wrong_hits = 0` semua konfig, konflik 0.
- Noise 10/25/50%: wrong_hits 0, disagree 0 → safety by construction (exact
  key match; noise → miss, bukan salah-hit).
- Tingkat exact pipe 84.4/81.5/83.8% (konsisten F3/pipeline, variasi subset).
- **Koreksi (KB-002)**: konfig 1x tadinya tidak efektif (bug mutasi) — re-run
  1x = hit 51, saved 13, **wrong 5** → 1x confirm TIDAK aman; semua angka
  di atas adalah konfig 3x (default) dan tetap valid.

**Gate / Verdict.** PASS (shadow) — no-regress, 0 wrong, 0 konflik terpakai.
Catatan jujur: gain LLM call belum terbukti (0 di 74 cert) — korpus tidak punya
cukup key berulang, BUKAN desain gagal.

**Risiko.**
- Key v1 memakai normalizer organizer v3 default (semua rule R0-R6); port
  produksi harus pakai set KEEP OOD-003 (R0/R2/PREFIX_HELD/R6) → key bisa
  berubah → KEY_VERSION naik.
- `hit_count` ditambah per lookup (write contention) — produksi pakai
  counter batch/queue, bukan tiap request.

**Commit terkait.** (isi saat commit sesi ini)

**Next action.**
1. Sampling data riil lintas fakultas — hitung unique organizer & repeat key
   (asumsi 1.000–10.000 unik di 36k request belum tervalidasi; korpus 74 hanya
   3 key berulang).
2. Keputusan user: ekstrak `jenis_kegiatan` beneran utk key lebih presisi, atau
   tetap role proxy.
3. Prototipe → produksi (`organizer_tingkat_kb` + `ENABLE_KB_TINGKAT`) HANYA
   setelah data riil menunjukkan repeat key cukup.

---

## F3 | 2026-08-10 | replay warm-up prototipe (opsi B, in-memory)

**Hipotesis.** KB dengan key `(organizer, role)` proxy event_type bisa
menggantikan router+LLM pada key berulang (warm-up N pertama, eval sisa).

**Dataset & konfigurasi.** 74 cert, GT v9 + matcher v2, pipeline run v9 + router
CURRENT, 0 LLM runtime. Warm N = 10/20/37 (urutan seeded acak), 1x vs 3x confirm.

**Perubahan kode.** `tests/kb/kb.py`, `tests/benchmark_kb_warmup.py`,
`docs/kb_design.md` (desain final opsi B).

**Hasil terukur.** Hit 2 (3%), LLM calls 31→29 (−2), tingkat exact eval
84.4/81.5/81.1% ≈ pipeline, collision 0, KB size 61.

**Gate / Verdict.** PASS (mekanisme) — gain nyata butuh skala besar; hanya 2
key berulang di korpus 74 → wajib sampling data riil sebelum arsitektur final.

**Risiko.** key `(org, role)` dgn raw_role mentah (repeat rendah); opsi B
collision rendah tapi belum teruji di data besar.

**Commit terkait.** commit sesi handoff v20-v21 (kb_warmup run 20260810_111952).

**Next action.** → KB-001 (sesi ini): normalisasi role, alur router-first,
semantik konflik, safety noise.

---

## Keputusan desain v1 | 2026-08-11 | review plan KB (sesi ini)

**Keputusan.**
1. KB = decision cache field `tingkat` saja (tidak menyentuh organizer/OCR).
2. Alur: `router → KB → LLM` (KB-first berisiko: key sama bisa beda konteks
   lomba/seminar; router sudah divalidasi 100% precision @50/74).
3. Key v1: `(normalized_organizer_v3, normalized_role, KEY_VERSION)`;
   `event_type` = role proxy (pipeline belum ekstrak `jenis_kegiatan`).
4. Lookup exact-match saja; tanpa fuzzy (fuzzy = risiko salah-propagasi).
5. Semua eksperimen di `tests/` — produksi zero-touch sampai gate data riil.

**Alasan.** F3 membuktikan mekanisme tapi korpus 74 terlalu kecil (2-3 key
berulang). Router/organizer/OCR sudah banyak trial tertutup (ledger); KB adalah
satu-satunya jalur efisiensi yang belum terbukti rugi, tapi juga belum terbukti
untung — bukti harus datang dari data riil, bukan 74 cert.
