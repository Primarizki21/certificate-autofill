# Roadmap Eksperimen Pipeline v10 — Robustness & Cost Efficiency at Scale

*Base: Pipeline v9 (organizer_v2 + tingkat_router). Target: menjawab dua masalah — (1) GT hanya 74 sertifikat, rawan overfit ke rule/keyword, (2) skala target ~360.000 request (36.000 mahasiswa x ~10 sertif) harus tetap murah token & robust.*

---

## 0. Ringkasan Diagnosis (dari pipeline_best.md)

| Isu | Bukti | Implikasi |
|---|---|---|
| `nama_kegiatan_sertifikasi` lemah (25.7%/52.7%) | gap exact-fuzzy kecil | genuine miss, bukan masalah formatting |
| `penyelenggara_kegiatan` gap besar (39.2%/79.7%) | gap exact-fuzzy besar | ekstraksi udah benar, matcher/normalisasi yang jelek → cheap win |
| `nomor_sertifikat` (59.6%/59.6%) | no gap | genuine miss |
| Router 13 rule @100% precision, N=74 | rule + keyword list (AIRNOLOGY/KAKIWIMA/SPECTA/BRIEF) dibuat di dataset yang sama dites | risiko overfit tinggi, belum divalidasi out-of-sample |
| Produksi MACRO 47.3% vs eksperimen terbaik 60.2% | `ENABLE_LLM_TINGKAT=false` di prod | gap 12.9pt = harga dari mematikan LLM fallback (29/74 cert) |
| Di skala 360k, 29/74 (~39%) kena LLM call | proporsional | ~140.000 LLM call kalau LLM fallback diaktifkan tanpa perubahan lain |

**Prinsip arah:** cost saving datang dari *mengurangi jumlah call* (struktural), bukan cuma dari prompt/token minimization per call yang sudah lumayan efisien (176 tok/cert).

---

## Fase 0 — Validasi Statistik Dulu (prasyarat semua fase lain)

Karena N=74, klaim titik ("83.8%", "100% precision") tanpa interval berisiko menyesatkan keputusan promosi ke produksi.

- [ ] **K-fold (5-fold) pada 13 rule router**: fit rule di 4/5 subset, uji di 1/5 sisanya, ulang bergilir. Bandingkan precision/recall per-fold vs klaim full-sample 100%.
- [ ] **Bootstrap CI** untuk semua metrik MACRO/per-field (resample 74 cert dengan replacement, 1000x, ambil 95% CI).
- [ ] **Audit protocol untuk fase-fase berikutnya**: setiap kali ada cache/KB/classifier baru, sisihkan random sample (mis. 5-10% dari hit) untuk direview manual — bukan cuma dipercaya begitu saja.
- [ ] Simpan hasil di ledger yang sama tempat NER v1/v3 di-*closed* (histori kegagalan tetap didokumentasikan, jangan dihapus).

**Output fase ini menentukan mana dari 13 rule yang "genuinely robust" vs mana yang kebetulan cocok di 74 sample — dipakai sebagai gate sebelum nambah rule baru di Fase 2.**

---

## Fase 1 — Normalisasi Organizer & Nomor Sertifikat (quick win, zero LLM cost)

Target: tutup gap 39.2%→79.7% di `penyelenggara_kegiatan` jadi exact match, tanpa nambah compute.

- [ ] Canonical alias dictionary untuk singkatan organisasi (BEM FTMM, HIMA-*, dst) — extend normalisasi akronim yang sudah ada di `organizer_v2.py` (`extract_organizer_v2`), bukan bikin modul baru.
- [ ] Normalisasi whitespace/punctuation/case sebelum exact match di matcher v2.
- [ ] Cek pola sisa mismatch di `nomor_sertifikat` (genuine miss, bukan gap) — kemungkinan butuh pola regex ke-4 di `extract_certificate_number`, bukan normalisasi.
- [ ] Re-run benchmark, bandingkan MACRO exact baru vs 60.2% baseline dengan CI dari Fase 0.

---

## Fase 2 — Rule Mining dari 29 Cert yang Jatuh ke LLM Fallback

Target: naikin router coverage di atas 45/74 tanpa nambah LLM call, sambil tetap deterministik.

- [ ] Analisis manual sinyal teks yang dipakai `llm_tingkat.py` buat decide di 29 cert unrouted.
- [ ] Cari pattern yang konsisten & general (bukan keyword spesifik event) → kandidat rule ke-14, 15, dst di `tingkat_router.py`.
- [ ] Validasi rule baru pakai protokol k-fold Fase 0 sebelum diklaim "100% precision" — jangan ulangi pola overfitting yang sama.
- [ ] Kalau ada sinyal yang *tidak* general (spesifik ke satu event), simpan sebagai kandidat entry Knowledge Base (Fase 3), bukan rule router permanen.

---

## Fase 3 — Organizer/Event Knowledge Base (KB) — solusi utama untuk isu skala

**Insight kunci:** 36.000 mahasiswa dari 4 angkatan pasti overlap besar di organizer & event yang sama (PKKMB, seminar fakultas rutin, lomba nasional tahunan). Space *unique organizer/event* jauh lebih kecil dari 360.000 request. Kalau LLM cost di-amortize per unique organizer (bukan per request), cost jangka panjang jadi bounded, bukan linear terhadap jumlah mahasiswa.

### Skema (tambahan tabel, bukan replace `models.py` yang ada)

```
organizer_tingkat_kb
- normalized_key      (organizer dinormalisasi, hasil Fase 1)
- tingkat              (hasil resolusi: router / LLM / human review)
- confidence
- source               (enum: router_rule | llm | human_review)
- hit_count            (berapa kali dipakai sejak dibuat)
- last_verified_at
- created_from_cert_id (traceability)
```

### Runtime flow (extend Stage 5, sebelum masuk router)

```
KB lookup (O(1), zero token)
  → hit & confidence tinggi     → pakai hasil KB
  → miss / confidence rendah    → Stage 5 Router (13+ rule)
       → rule hit                → pakai hasil router, WRITE ke KB
       → rule miss                → Stage 6 LLM fallback
             → LLM hasil          → WRITE ke KB (source=llm, confidence dari LLM)
                                   → tetap masuk needs_review kalau confidence < threshold
```

### Risiko & mitigasi

- **Cache salah propagate ke ribuan mahasiswa** → audit rutin: random sample dari KB hit direview manual per batch (pakai protokol Fase 0). KB entry dengan `source=llm` diaudit lebih ketat/lebih sering daripada `source=router_rule`.
- **Organizer sama, konteks beda** (mis. nama organizer identik tapi levelnya beda di tahun berbeda) → jangan key murni by nama organizer saja; pertimbangkan komposit key (organizer + tipe event/lomba) kalau false-positive collision mulai muncul di audit.
- **KB jadi single point of failure kalau salah dari awal (cold start)** → warm-up period: minggu pertama rollout skala besar, turunkan threshold auto-write ke KB (butuh 2-3 konfirmasi konsisten dulu sebelum jadi authoritative), bukan langsung trust dari 1 hit.

Ini fase yang paling langsung menjawab concern "360k request, LLM API/local server gak akan sanggup" — karena setelah warm-up, LLM call rate seharusnya turun tajam ke jumlah unique organizer/event baru per periode, bukan proporsional ke jumlah mahasiswa.

---

## Fase 4 — Fingerprint Dedup di Level Event/Dokumen

Banyak sertifikat = template event massal yang dipersonalisasi (nama beda, sisanya identik — PKKMB, seminar wajib fakultas). Ini nangkep redundancy lebih luas dari sekadar field `tingkat`.

- [ ] Fingerprint teks non-personal: hash dari (organizer + tanggal + keyword aktivitas) atau teks setelah nama mahasiswa distrip.
- [ ] Kalau fingerprint match dengan cert yang sudah pernah diproses lengkap → short-circuit seluruh field (bukan cuma tingkat), tinggal isi ulang nama/role per individu.
- [ ] Ini extend Stage 1/2 (sebelum field extraction penuh dijalankan), bukan komponen baru yang berdiri sendiri — cek titik integrasi paling murah di pipeline yang sudah ada.

---

## Fase 5 — Distillation: Classifier Ringan Pengganti LLM Long-Tail

Setelah KB (Fase 3) warm-up beberapa ratus/ribu cert dan mengumpulkan label dari LLM+human review:

- [ ] Train classifier ringan (logistic regression / GBM di text feature, atau embedding kecil) sebagai pengganti `llm_tingkat.py` untuk kasus yang KB & router belum bisa resolve.
- [ ] LLM/human tetap dipertahankan sebagai *periodic drift-check* (mis. sample kecil per bulan), bukan dihapus total — buat deteksi kalau distribusi organizer/event baru mulai bergeser (angkatan baru, event baru).
- [ ] Ini fase paling belakang — butuh volume data cukup dari Fase 3 dulu, jangan dikerjakan paralel dari awal.

---

## Fase 6 — Extend `needs_review` Threshold ke Field Lemah

Threshold `confidence < 0.80 → needs_review` sekarang cuma ada di `form_mapper.py`. Di skala 360k, safety net ini lebih penting daripada silent wrong output.

- [ ] Extend threshold serupa ke `nama_kegiatan_sertifikasi` dan `nomor_bukti_fisik_nomor_sertifikasi` (dua field paling lemah & genuine-miss).
- [ ] Ganti keyword list spesifik (AIRNOLOGY/KAKIWIMA/SPECTA/BRIEF) di `extract_activity_name` jadi pattern struktural yang lebih general kalau memungkinkan — keyword spesifik gak akan generalize ke event tahun-tahun mendatang, jadi salah satu risiko robustness terbesar jangka panjang.

---

## Fase 7 — Infra Readiness (di luar akurasi, tapi relevan ke skala)

- [ ] Peak 1000 concurrent request → OCR (RapidOCR+Tesseract) CPU-heavy, bisa jadi bottleneck lebih besar dari token cost LLM. Desain async worker queue/pool untuk OCR fallback, jangan biarkan semua request trigger OCR barengan saat peak.
- [ ] `ENABLE_OCR_NUMBER_2PASS` dan OCR fallback trigger condition perlu direview ulang dengan lensa "biaya waktu di concurrency tinggi", bukan cuma "gain akurasi per cert" seperti keputusan deploy-time sebelumnya.

---

## Estimasi Dampak (hipotesis, perlu divalidasi dengan data riil unique-organizer count)

| Skenario | LLM call kira-kira |
|---|---|
| LLM fallback aktif, tanpa KB, di 360k request | ~140.000 call (39% x 360k) |
| Dengan KB setelah warm-up, asumsi unique organizer/event jauh lebih kecil dari 36.000 mahasiswa | bounded ke jumlah unique organizer baru per periode + trickle re-verifikasi audit, bukan proporsional ke jumlah request |

Angka ini masih tebakan arah, bukan janji — perlu dicek dengan sampling data organizer riil (berapa banyak unique organizer/event yang benar-benar muncul di beberapa ratus sertifikat pertama) sebelum dijadikan justifikasi keputusan arsitektur.

---

## Urutan Eksekusi yang Disarankan

1. **Fase 0** (validasi statistik) — wajib duluan, jadi gate buat semua klaim "improvement" setelah ini.
2. **Fase 1** (normalisasi organizer) — quick win MACRO, effort kecil.
3. **Fase 3** (Knowledge Base) — solusi struktural utama untuk isu skala, mulai desain & bootstrap sekarang meski volume data masih kecil.
4. **Fase 2** (rule mining) — paralel dengan Fase 3, sumber rule baru & KB seed entries saling melengkapi.
5. **Fase 6** (extend needs_review) — murah, bisa nyusul kapan saja.
6. **Fase 4** (fingerprint dedup) — setelah Fase 3 stabil, karena butuh KB sebagai referensi "sudah pernah diproses".
7. **Fase 5** (distillation classifier) — paling belakang, butuh data volume dari Fase 3.
8. **Fase 7** (infra OCR) — bisa dikerjakan kapan saja secara independen, prioritaskan sebelum load testing skala besar.

---

## Instruksi untuk Coding Agent

> Konteks: codebase pipeline sertifikat sudah ada dan production-tested (v9). Tugas kamu adalah **mengembangkan/extend modul yang sudah ada**, bukan menulis ulang arsitektur atau membuat pipeline paralel.

**Sebelum menulis kode apa pun:**
1. Baca dulu modul existing yang relevan: `organizer_v2.py` (`extract_organizer_v2`), `tingkat_router.py` (`route_tingkat`), `llm_tingkat.py` (`infer_tingkat`), `form_mapper.py` (`map_fields_to_form`), `field_extractor.py`, `models.py`. Pahami konvensi penamaan yang sudah dipakai (ID rule seperti `ROUTER-002/003`, `ORG-001`) sebelum menambah apa pun.
2. Cek `docs/report/pipeline_data.json` — ini source of truth untuk versi/hasil/stages/router_rules/progression. Semua eksperimen baru harus tercatat di sini dengan format yang konsisten dengan entry v4–v9 yang sudah ada.

**Prinsip kerja:**
- **Extend, jangan rewrite.** Rule baru masuk sebagai entry tambahan di struktur rule yang sudah ada (bukan file rule terpisah). KB baru (Fase 3) adalah tabel tambahan di `models.py`, terhubung ke flow Stage 5 yang sudah ada — bukan service/pipeline paralel.
- **Ikuti pola flag `ENABLE_*`** yang sudah dipakai (`ENABLE_LLM_TINGKAT`, `ENABLE_OCR_NUMBER_2PASS`, `ENABLE_OCR_FALLBACK`) untuk setiap fitur baru yang bisa di-toggle — konsisten dengan cara produksi mengontrol pipeline sekarang.
- **Disiplin ledger.** Kalau sebuah eksperimen gagal (analog ke NER v1 yang "closed di ledger" karena 12.8% MACRO), tetap dicatat sebagai closed, jangan dihapus dari histori — supaya arah yang sudah dicoba dan gagal gak diulang di eksperimen berikutnya.
- **Jangan klaim metrik tanpa interval.** Setiap klaim precision/recall/MACRO baru harus disertai hasil dari protokol Fase 0 (k-fold / bootstrap CI), terutama karena N=74 kecil.
- **Format benchmark run** tetap ikuti pola `tests/benchmark_runs/run_llm_v{N}_{YYYYMMDD_HHMMSS}` yang sudah ada.
- **Promosi ke produksi** tetap lewat proses yang sudah didefinisikan di pipeline_best.md: update `docs/report/pipeline_data.json` → `uv run python scripts/generate_pipeline_doc.py` → dokumen ter-regenerate otomatis. Jangan bikin script generate-doc baru.
- **Gunakan `uv`** sebagai package manager, konsisten dengan seluruh codebase.
- Untuk Knowledge Base (Fase 3) khususnya: implementasikan write-path (router/LLM/human → KB) dan read-path (KB lookup sebelum router) sebagai *penambahan step* di flow Stage 5 yang sudah ada, dengan audit-sampling hook yang bisa di-toggle terpisah dari toggle utama (jangan campur logic audit dengan logic inference).

**Kalau ambigu soal desain (mis. key KB murni organizer vs composite organizer+tipe event):** tulis dulu 2-3 opsi dengan trade-off singkat, baru eksekusi — jangan langsung pilih satu tanpa diskusi, karena ini keputusan yang mahal untuk di-migrate ulang setelah KB mulai berisi ribuan entry.
