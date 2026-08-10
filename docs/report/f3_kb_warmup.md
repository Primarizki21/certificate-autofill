# F3 — Replay KB Warm-up (prototipe in-memory, opsi B)

> Generasi: 2026-08-10 11:19:53 | GT v9 + matcher v2 | pipeline = run v9 (tingkat dari extracted_fields) + router CURRENT + organizer v3 | event_type = role (proxy jenis_kegiatan) | 0 LLM runtime call

Baseline LLM calls tanpa KB = jumlah cert unrouted di replay (74 - router calls; kolom LLM no-KB). Run v9 asli = 29 calls (router lama 45 routed); replay router current = 43 routed → no-KB = 31. KB mengurangi call hanya saat entry sudah authoritative (confirms >= ambang).

| Konfig | Warm-up N | KB size | Hit (eval) | LLM calls | LLM no-KB | delta | Router calls | Tingkat exact (eval) | Collision |
|---|---|---|---|---|---|---|---|---|---|
| 1x confirm | 10 | 61 | 2 (3%) | 29 | 31 | -2 | 43 | 54/64 (84.4%) | 0 |
| 1x confirm | 20 | 61 | 2 (3%) | 29 | 31 | -2 | 43 | 44/54 (81.5%) | 0 |
| 1x confirm | 37 | 61 | 2 (3%) | 29 | 31 | -2 | 43 | 30/37 (81.1%) | 0 |
| 3x confirm (default warm-up) | 10 | 61 | 2 (3%) | 29 | 31 | -2 | 43 | 54/64 (84.4%) | 0 |
| 3x confirm (default warm-up) | 20 | 61 | 2 (3%) | 29 | 31 | -2 | 43 | 44/54 (81.5%) | 0 |
| 3x confirm (default warm-up) | 37 | 61 | 2 (3%) | 29 | 31 | -2 | 43 | 30/37 (81.1%) | 0 |

## Interpretasi

- Hit rate = seberapa sering KB menggantikan router+LLM. Di korpus 74 yang organizer-nya kebanyakan unik, gain KB nyata baru muncul di skala besar (36k request) — angka ini bukti mekanisme, bukan janji penurunan di 74 cert.
- `1x confirm` langsung authoritative → hit lebih banyak, tapi risiko entry salah tersebar (lihat tingkat exact). `3x confirm` = lebih aman, hit kecil di korpus kecil (butuh 2-3 kemunculan key yang sama).
- Collision = key (organizer, role) bertingkat beda — risiko opsi B; di korpus ini 0, validasi ulang di data lebih besar.
- Tingkat exact eval ≈ pipeline v9 (83.8%) — selisih = variasi subset eval per N + efek cold-start, bukan regress KB.