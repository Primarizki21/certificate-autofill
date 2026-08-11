# KB-004 — Audit korpus utk KB tingkat (tanpa GT)

> Generasi: 2026-08-11 10:53:08 | variant plain | pipeline = router + fallback offline (0 LLM) | proyeksi 3x confirm, warm 20

- Cert: 74 | organizer unik (v3): 52 | key unik: 55 | key berulang: 3 (9 cert)

## Key berulang (kandidat KB)

| Organizer | Role | Frekuensi |
|---|---|---|
| Faculty of Science and Technology INFORMATION SYSTEMS DEPT | Peserta | 5 |
| Faculty of Science and Technology Information System Dept. | Peserta | 2 |
| Program Studi S1 Teknologi Sains Data Universitas Airlangga | Panitia | 2 |

## Collision (key sama → tingkat pipeline beda)

Jumlah: 0

## Fragmentasi org logis (>1 key utk 1 org)

| Org logis | Keys | Certs |
|---|---|---|
| facultyofscienceandtechnologyinformationsystemdept | 2 | 7 |

## Proyeksi KB (3x confirm, warm N pertama)

| Routed (router) | LLM fallback tanpa KB | KB hits (eval) | Saved LLM |
|---|---|---|---|
| 45 | 29 | 3 | 0 |

## Interpretasi

- `repeated_keys`/`repeated_certs` = potensi gain KB (LLM call saved). Kecil = korpus belum membuktikan KB hemat (korpus 74: 3/9).
- `collisions` > 0 = key yang TIDAK boleh authoritative tanpa review manusia (tambah rule/alias atau flag).
- `fragmentation` = kerugian exact-match; normalisasi key (KB-003) atau alias table.
- Angka ini = gate data riil: sebelum produksi, ulangi audit di korpus lintas fakultas.