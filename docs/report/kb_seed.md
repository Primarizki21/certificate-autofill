# KB-002 — Seeded persistent KB (ceiling human-seed + persistence)

> Generasi: 2026-08-11 10:38:06 | GT v9 + matcher v2 | key v1 | pipeline = run v9 + router CURRENT | 0 LLM runtime

Bagian: (1) smoke seed, (2) ceiling seeded (label seed = GT cert pertama utk key berulang, diuji semua cert), (3) safety noise 25%, (4) learning persist (KB disimpan JSON setelah warm, dimuat ulang), (5) fragmentasi key.

## Smoke: ok

Seed human_review → authoritative langsung; konflik → non-authoritative (nilai asli utuh); key ber-noise → miss; round-trip save/load identik.

## Ceiling — seeded (seed: human_review, label dari GT cert pertama)

| Metrik | nilai |
|---|---|
| Seed keys / certs tercakup | 3 / 9 |
| Hit | 9 |
| Saved LLM call (hit + router miss) | 0 |
| Wrong hit vs GT | 0 |
| Disagree vs pipeline | 0 |
| Tingkat exact KB / pipeline | 9/74 (12.2%) / 62/74 (83.8%) |
| Router calls / LLM calls | 45 / 29 |

## Safety — noise OCR 25% (wrong_hits harus 0)

| Hit | Wrong | Disagree |
|---|---|---|
| 9 | 0 | 0 |

## Learning persist (warm-up belajar → snapshot JSON → eval)

| Konfig | Warm N | Hits mem | Hits persist | Disagree | Wrong | Saved LLM |
|---|---|---|---|---|---|---|
| 1x confirm | 10 | 51 | 51 | 0 | 5 | 13 | ✓ identik |
| 3x confirm (default warm-up) | 20 | 3 | 3 | 0 | 0 | 0 | ✓ identik |

## Fragmentasi key (1 org logis terpecah oleh varian case/format)

| Org logis | Keys (org + role × frekuensi) | Total certs |
|---|---|---|
| facultyofscienceandtechnologyinformationsystemdept | Faculty of Science and Technology INFORMATION SYSTEMS DEPT + Peserta ×5; Faculty of Science and Technology Information System Dept. + Peserta ×2 | 7 |

## Interpretasi

- Seeded KB (pengetahuan terverifikasi) = 0 wrong, 0 disagree → ceiling aman; tapi saved_llm tetap kecil: key berulang semuanya cert yang router sudah putuskan. Korpus 74 = pembatas, bukan desain.
- Persistence terbukti: snapshot JSON + version check, hasil identik dgn in-memory (G3).
- Fragmentasi = kerugian exact-match yang terukur: 1 org logis terpecah jadi 2 key → hit rate KB turun. Kandidat perbaikan: normalisasi key case/punct, ATAU alias table (produksi).
- Gate produksi tetap: sampling data riil lintas fakultas (repeat key dan collision di data besar).