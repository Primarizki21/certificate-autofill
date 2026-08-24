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

## KB-005 | 2026-08-11 | event_type utk key (role vs jenis vs kelompok)

**Hipotesis.** `jenis_kegiatan`/`kelompok_kegiatan` (dari `map_kelompok_dan_jenis`,
0 LLM) memberi key lebih presisi daripada role proxy → repeat keys lebih tinggi
tanpa collision.

**Dataset & konfigurasi.** 74 cert, GT v9 + matcher v2, pipeline run v9 + router
CURRENT. 4 varian × 3 event = 12 kombinasi (cache label per cert sekali).
Metrik: keys/repeat/empty rate/collision/ceiling/shadow 3x/noise 25%.

**Perubahan kode.**
- `tests/kb/key.py` — `EVENTS`, `compute_event`, `make_key`, `build_key(event=...)`.
- `tests/benchmark_kb_event.py` (baru) — 12 kombinasi + noise.

**Hasil terukur.**
- **role**: collision 0 (satu-satunya), empty 13, repeat 3(9), ceiling hit 9,
  shadow hit 5 (stem/alias/both), wrong 0, noise 0.
- **jenis**: empty 52 (70% key mati — `"--"`), collision 1, wrong 1 → tidak layak.
- **kelompok**: repeat 5 (14 cert, tertinggi) TAPI collision 1, wrong 2 →
  over-merge 5 kategori, GATE FAIL.

**Gate / Verdict.** **PASS (role)** — G1 collision 0 hanya role; G2 wrong 0;
G3 shadow ≥5; G4 empty jujur. **Jawaban desain #1: tidak perlu ekstrak
`jenis_kegiatan` beneran — role proxy cukup dan paling aman** (menutup
pertanyaan schema produksi KB).

**Risiko.** kelompok_kegiatan hanya layak bila collision di-audit per key di
data riil (audit.py).

**Commit terkait.** (commit sesi ini)

**Next action.** — (jalur KB tuntas; lihat Verdict Final di bawah)

---

## KB-006 | 2026-08-11 | alias mining data-driven

**Hipotesis.** Kandidat alias bisa di-mining otomatis (stem-org sama + role
sama + tingkat pipeline sama) dengan keamanan yang sama seperti alias manual —
review manusia tetap, tapi kandidatnya tidak lagi manual.

**Dataset & konfigurasi.** 74 cert, GT v9 + matcher v2; kandidat divalidasi vs
GT (konsisten semua cert group); dampak diukur shadow 3x N=20 + ceiling + noise 25%.

**Perubahan kode.** `tests/kb/alias.py` (baru) — build_cache, mine_alias_candidates,
make_alias_map + demo; `tests/benchmark_kb_alias.py` (baru).

**Hasil terukur.** Mining menemukan PERSIS kandidat yang sama dengan alias
manual KB-003 (FST pair, 2/5), valid=True. auto-alias: shadow hit 5 (= manual),
wrong 0, disagree 0; noise 25% wrong 0. Precision kandidat 100% (0 over-merge).

**Gate / Verdict.** **PASS** — precision 100%, shadow ≥5, wrong 0; auto-alias =
alias manual di korpus ini (otomasi tanpa kehilangan keamanan).

**Risiko.** Validitas kandidat di data baru wajib diukur ulang (GT korpus baru
atau sampling manual) — stem bisa over-merge nama yang mirip tapi beda org.

**Commit terkait.** (commit sesi ini)

**Next action.** Siap dipakai bila data riil muncul: mine → review → make_key(aliases=...).

---

## KB-SCALE-001 | 2026-08-14 | simulasi workload produksi skewed

**Konteks.** Verdict Final v27 menutup KB karena saved_llm = 0 di korpus 74
seragam. Pertanyaan baru: **efisiensi saat scale produksi besar** — produksi
tidak seragam (beberapa organizer/event dominan, request ribuan). Dimensi ini
belum pernah diuji; verdict lama tidak dibatalkan (berlaku utk klaim data
riil), KB-SCALE = proyeksi pola + parameter.

**Hipotesis.** Hemat LLM proporsional request per key: di workload skew besar,
warmup 3x terbayar → mayoritas request non-routed dijawab KB.

**Dataset & konfigurasi.** Key space 55 (korpus 74), N=500 & N=5000 request
sintetis (SEED=42), skew 70/30/80/20/90/10 (20% key terpopuler menampung R%
request, bobot freq^alpha), replay ROUTER→KB→LLM, confirm 3x, label pipeline
= `audit.pipeline_label` (0 LLM runtime), GT v9 + matcher v2.

**Perubahan kode.** `tests/benchmark_kb_scale.py` (baru); `scripts/
generate_runs_summary.py` (kind `kb_scale`).

**Hasil terukur.** N=5000 80/20: saved 391/448 = **87%**, hit 97%, wrong 2.8%
(136) — **GATE PASS** (≥50% saved, ≥60% hit, <5% wrong). N=500 80/20: saved
12% — **FAIL volume kecil** (warmup menelan porsi). Est. latency saved ~978s/
5000 req (2.5s/call v4, ESTIMASI). 55/55 key authoritative. Wrong = warisan
error pipeline (key populer benar → serve error 2.8% < pipeline ~19%).

**Gate / Verdict.** **PASS** di volume produksi (5000) — KB efisien saat scale
besar + skew; volume kecil tidak. Synthetic = proyeksi pola, bukan bukti riil.

**Risiko.** Distribusi produksi asumsi (Pareto) belum tervalidasi; angka hemat
bergantung request/key aktual. Gate data riil tetap `tests.kb.audit`.

**Commit terkait.** (commit KB-SCALE-001/002).

**Next action.** Data riil lintas fakultas → audit.py; bila request/key ≥ ~10
dgn skew → KB layak produksi (keputusan user).

---

## KB-SCALE-002 | 2026-08-14 | race tulis multi-worker

**Konteks.** Produksi = multi-worker (api + db_worker). KB in-memory per worker
= cache terpisah + race saat tulis key sama → lost update `confirms` (entry
tak pernah authoritative walau 3x).

**Hipotesis.** `threading.Lock` di TingkatKB membuat write deterministik.

**Perubahan kode.** `tests/kb/kb.py` (lock di write/lookup/peek, produksi
tetap zero-touch); `tests/test_kb_scale_concurrency.py` (baru).

**Hasil terukur.** 8 thread × 500 write key sama: confirms == 4000, tanpa lock
test gagal; 20 key deterministik: per key == 8×300. 0 lost update.

**Gate / Verdict.** **PASS** — write aman multi-worker; PG production tetap
otoritas (lock = prototipe in-memory).

**Next action.** Per-key lock bila profiling butuh (sekarang global lock
cukup, ponytail).

---

## KB-SCALE-003 | 2026-08-14 | peta hemat KB (volume × key space × skew)

**Konteks.** kb_design.md berasumsi 1.000-10.000 unique organizer utk 36k
request — belum tervalidasi. Peta memvalidasi/menyanggah asumsi tsb.

**Hipotesis.** Hemat proporsional request per key populer; volume besar +
skew → warmup terbayar.

**Dataset & konfigurasi.** Grid 5 volume {500..36k} × 5 key space {55..10k} ×
3 skew (75 kombinasi); key sintetis freq zipf; routed share 61% (terukur
korpus); confirm 3x; SEED=42; 0 LLM.

**Perubahan kode.** `tests/benchmark_kb_scale_map.py` (baru); reuse
`alpha_for_skew`/`replay_workload` dari SCALE-001.

**Hasil terukur.** 36k @80/20: saved **92% (1k key) / 78% (5k) / 72% (10k)** —
semua ≥50%. Volume kecil + key space besar = rendah (500 req / 10k = 35%).
Insight: hemat dari key POPULER (top-20% menampung 80% request); 36k/10k =
3.6 req/key rata-rata tetap 72%.

**Gate / Verdict.** **PASS** — asumsi kb_design layak dgn skew; peta =
cold-start worst case.

**Risiko.** Key sintetis zipf = asumsi; distribusi riil tetap butuh audit.py.

**Next action.** KB persist lintas periode (KB-002) mengubah matematika —
warmup sekali, hemat selamanya; pertimbangkan di desain produksi.

---

## KB-SCALE-004 | 2026-08-14 | konfigurasi KB: confirm 2x vs 3x, key alias

**Konteks.** 1x confirm sudah gagal (KB-002: wrong 5); **2x belum pernah
diuji**. Di volume menengah (N=500) warmup 3x menelan porsi (SCALE-001: 12%).

**Hipotesis.** 2x mempercepat warmup → hemat naik, tanpa menambah salah.

**Dataset & konfigurasi.** Grid confirm {2,3} × key {plain, alias} × N
{500, 5000} × skew 80/20; korpus 74 (bukan sintetis); 0 LLM.

**Perubahan kode.** `tests/benchmark_kb_scale_conf.py` (baru).

**Hasil terukur.** **GATE FAIL**: wrong 2x **304** vs 3x **284** (+20 — error
pipeline terkunci lebih cepat); hemat N=500 naik (24% vs 5%) tapi tidak
sebanding dgn salah ekstra. Alias: keys 55→54, hit naik tipis @N=500 (409 vs
407), efek kecil (FST pair non-populer).

**Gate / Verdict.** **FAIL** — 3x confirm TETAP wajib; 2x = hemat palsu.

**Next action.** 2x jangan dipakai produksi; alias tetap kandidat di data
riil (fragmentasi lebih banyak di luar korpus).

---

## KB-SCALE-005 | 2026-08-14 | proyeksi akurasi & biaya produksi end-to-end

**Konteks.** SCALE-001 hitung hemat CALLS, belum kualitas akhir. Di sini
digabungkan dgn nilai terukur korpus.

**Hipotesis.** KB = cache yang LEBIH akurat dari LLM fallback (key populer =
jawaban terverifikasi 3x) → akurasi akhir naik + biaya turun.

**Dataset & konfigurasi.** Model (nilai TERUKUR): router 100% (45/45), KB
serve 97.2% (SCALE-001), LLM 58.6% (17/29 non-routed), 176 tok/call (v9);
grid N {500, 5000} × skew {70-90%}.

**Perubahan kode.** `tests/benchmark_kb_scale_e2e.py` (baru).

**Hasil terukur.** 80/20 N=5000: akurasi **96.3% → 99.3%** (dgn KB ≥ tanpa
KB di SEMUA kombinasi), hemat biaya **87%** (57 vs 446 LLM calls).

**Gate / Verdict.** **PASS** — KB menaikkan akurasi akhir & hemat biaya ≥50%.

**Risiko.** Label korpus terukur, tapi distribusi request simulasi; validasi
akhir audit.py data riil.

**Next action.** Cerita lengkap KB: hemat 87% + akurasi +3pt — bahan
keputusan produksi ke tim.

---

## KB-PROD-001 | 2026-08-14 | semantik produksi: servable, resolve, audit_due

**Konteks.** Eksperimen selesai (KB-001..006 + SCALE-001..005), tapi gap
produksi yang EKSPERIMEN tak bisa jawab belum ter-kode: propagasi label llm
kurang tepercaya, entry konflik mati selamanya (tanpa human review), entry
basi antar tahun. Data riil belum tersedia → semua gap ini bisa dikerjakan
di prototipe tanpa data.

**Hipotesis.** Produksi butuh semantik yang lebih ketat dari `authoritative`
(threshold seragam 3): llm butuh bukti lebih, human review = otoritas
langsung, entry basi = jangan dipakai.

**Perubahan kode.** `tests/kb/kb.py`: `servable()` (source-aware +
TTL, `AUTHORITATIVE_CONFIRMS = {router_rule: 3, llm: 5, human_review: 1}`,
`TTL_DAYS = 365`), `resolve()` (human review: conflicts=0, source=human,
servable langsung), `audit_due()` (sampling F0: source=llm + conflicts>0).
`authoritative` TIDAK diubah — eksperimen lama (benchmark_kb_scale/seed/
shadow, test concurrency) tetap valid. `tests/test_kb_production_semantics.py`
(baru, 4 test). `docs/kb_design.md` §4/§6 diperbarui (keputusan #1/#4
RESOLVED, skema `event_type`→`role`).

**Hasil terukur.** Pytest 60 → 64 passed, 0 regress. Demo: llm 3x =
authoritative legacy tapi non-servable → 5x servable; human_review langsung
servable; entry 2020 non-servable utk TTL 365, servable utk TTL None; resolve
membuka entry konflik; audit_due = llm+konflik saja.

**Gate / Verdict.** **PASS** — semantik produksi ter-kode di prototipe,
zero-touch produksi.

**Risiko.** `AUTHORITATIVE_CONFIRMS`/`TTL_DAYS` = nilai default yang perlu
validasi saat data riil datang; konflik utk `servable` masih permanen sampai
resolve (by design).

**Next action.** Port produksi (TIDAK dieksekusi): PG atomic upsert ganti
`threading.Lock` (multi-proses), hit_count counter batch, ukur tok/call path
produksi, gate data riil `audit.py`.

---

## Verdict Final Jalur KB | 2026-08-11 | penutup eksperimen (tanpa data baru)

**Posisi (keputusan user):** KB = eksperimen murni. Tidak masuk produksi sampai
ada pipeline yang menonjol; dan tidak ada data di luar korpus 74 (user
konfirmasi tidak bisa menambah data).

**Apa yang tervalidasi (KB-001..006, semuanya PASS di gates-nya):**
- Mekanisme aman: 0 wrong hit, noise-safe (exact-match → miss), konflik →
  non-authoritative, persistence JSON + version check, warm-up ≥3 confirm
  wajib (1x = 5 wrong), normalisasi key (stem/alias) menaikkan shadow hit
  3→5, role = event terbaik (jenis_kegiatan 70% empty, kelompok over-merge),
  alias mining otomatis = manual.

**Apa yang TIDAK bisa dibuktikan (batas korpus 74):**
- Gain LLM call: `saved_llm = 0` di semua konfigurasi aman (55 key unik, 3
  berulang, semuanya router-routed). Tanpa data baru, angka ini tidak akan
  berubah — **KB tidak akan menjadi pipeline pemenang pada metrik efisiensi
  di korpus ini**.

**Kesimpulan:** jalur KB ditutup sebagai eksperimen yang tuntas (desain
terjawab, alat siap: `audit.py`, `alias.py`, `store.py`). Bila suatu saat ada
data baru: jalankan `tests/kb/audit.py` → keputusan varian key → review alias
→ baru pertimbangkan produksi. Sampai saat itu, fokus pencarian "pipeline yang
menonjol" beralih ke jalur akurasi (organizer v3+R6, scoring, matcher) yang
sudah terukur naik tanpa data baru.

---

## KB-003 | 2026-08-11 | normalisasi key v2 (fragmentasi FST)

**Hipotesis.** Normalisasi key (stem / alias / both) menyatukan org logis yang
terpecah exact-match (FST DEPT: "INFORMATION SYSTEMS DEPT" vs "Information
System Dept.", 7 cert) → hit KB naik, tanpa collision baru.

**Dataset & konfigurasi.** 74 cert, GT v9 + matcher v2, pipeline run v9 + router
CURRENT, 0 LLM runtime. 4 varian: plain / stem / alias / both (key version
`v1-{variant}`). Metrik: ceiling seeded (GT cert pertama), collision, shadow 3x
N=20, noise 25%.

**Perubahan kode.**
- `tests/kb/key.py` — `build_key(..., variant)` + `KEY_ALIASES` (FST pair) +
  `_stem_org` + demo varian.
- `tests/benchmark_kb_norm.py` (baru) — evaluasi 4 varian.

**Hasil terukur.**
- plain: 55 key / 3 repeat (9 cert) / shadow hit 3.
- stem, alias, both: 54 key / 2 repeat (9 cert, FST menyatu) / ceiling hit 9
  (=) / **shadow hit 5 (+2)** / collision 0 / wrong 0 / disagree 0 / noise
  wrong 0.

**Gate / Verdict.** **PASS** — G1 collision 0, G2 wrong 0 (seeded+noise),
G3 hit ≥9 (imbang), G4 shadow no-regress. Normalisasi key menaikkan shadow hit
3→5 tanpa efek samping di korpus.

**Risiko.**
- stem = agresif ("universitas"→"universita") — over-merge risk di data baru;
  alias = konservatif tapi hanya 1 baris (FST). Pilih varian berdasar audit
  data riil (`tests/kb/audit.py --variant ...`).
- Alias menarget bentuk key persis ("...INFORMATION SYSTEMS DEPT") — rapuh
  terhadap perubahan titleize; pasangkan dgn stem/both utk ketahanan.

**Commit terkait.** (commit sesi ini)

**Next action.** Audit data riil per varian (KB-004 siap); keputusan varian
final saat data datang.

---

## KB-004 | 2026-08-11 | instrumen audit korpus (gate data riil)

**Hipotesis.** Gate produksi tidak boleh terblokir oleh tidak adanya GT: alat
audit yang mengukur repeat key, collision, dan proyeksi saved LLM langsung dari
teks (tanpa LLM/OCR) memungkinkan keputusan cepat saat data lintas fakultas
datang.

**Dataset & konfigurasi.** Dry-run korpus 74 (path default `run_20260728_131835/
extracted_texts`); variant plain; proyeksi 3x confirm, warm 20, urutan sorted.

**Perubahan kode.** `tests/kb/audit.py` (baru) — CLI `--dir --variant --out`.

**Hasil terukur.** Dry-run: keys 55==55, repeated 3==3 → **SELFCHECK PASS**
(konsisten KB-001); collision 0; saved_llm 0 (konsisten KB-001/002).

**Gate / Verdict.** **PASS** — alat berfungsi & angka konsisten; siap dipakai
pada korpus riil.

**Risiko.** Proyeksi saved LLM memakai urutan sorted-stem (proxy kronologis) —
di data riil dengan timestamp, urutan waktu lebih akurat.

**Commit terkait.** (commit sesi ini)

**Next action.** `uv run python -m tests.kb.audit --dir <data_riil>` → ukur
gate produksi: repeated keys, collision, saved_llm. Juga `--variant stem/alias`
utk perbandingan normalisasi.

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

---

## HYB-KB-001 & HYB-KB-002 | 2026-08-24 | efek KB pada pipeline HYB + proyeksi skala 360k

**Konteks.** Pertanyaan user: apakah KB harus masuk produksi dulu sebelum
dicampur pipeline HYB (winner HYB-LLM-001)? Jawaban: tidak — dicampur di
lapisan eksperimen, produksi tetap zero-touch. Sekalian disimulasikan
dengan asumsi ril user: ~360.000 request NON-concurrent.

**Hasil.**
- HYB-KB-001 (korpus 74): mekanisme ROUTER→KB→LLM ter-wire, no-regress
  exact, wrong 0, saved 0 — korpus pembatas (3 key berulang ≤3 kemunculan,
  `servable` butuh ≥4). Konsisten F3/KB-001: gain KB = skala.
- HYB-KB-002 (360k request, key space 1k–50k × skew 70–90% × TTL ∞/365):
  hemat LLM calls **72–98%** (gate @(10k, 80/20): **86,4%**), akurasi naik
  **+3–5 pp** di semua titik grid (gate: 86,2→89,5%), ≈42 jam proses &
  ~17,9 jt token terhemat di titik gate. TTL 365h murah (−0,1–0,2 pp).

**Pelajaran arsitektur.** Router SELALU menang; KB hanya melayani cert
unrouted. Melayani request routed dr KB = menimpa jawaban router @100%
dgn error turunan profil → akurasi −10 pp (terdeteksi saat iterasi).
Ini memperkuat keputusan desain v1 #2 (`router → KB → LLM`).

**Next action.** Tetap gate data riil (`tests/kb/audit.py`) — angka skala
berbasis profil korpus, bukan sampling riil. Port produksi setelah itu.
