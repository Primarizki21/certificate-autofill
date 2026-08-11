# KB-003 — Normalisasi key v2 (plain/stem/alias/both)

> Generasi: 2026-08-11 10:52:40 | GT v9 + matcher v2 | pipeline = run v9 + router CURRENT | 0 LLM runtime

Masalah (KB-002): exact-match memecah 1 org logis (FST DEPT, 7 cert) menjadi 2 key → hit turun. Varian normalisasi key diukur terpisah; versi key `v1-{variant}` (snapshot tak tercampur).

## Ceiling seeded (label = GT cert pertama utk key berulang freq≥2)

| Varian | Keys | Repeat (cert) | Seeds | Hit | Saved LLM | Wrong | Disagree | Collision | FST merged | Exact KB / Pipe |
|---|---|---|---|---|---|---|---|---|---|---|
| plain | 55 | 3 (9) | 3 | 9 | 0 | 0 | 0 | 0 | 0 | 9/74 (12.2%) / 62/74 (83.8%) |
| stem | 54 | 2 (9) | 2 | 9 | 0 | 0 | 0 | 0 | 1 | 9/74 (12.2%) / 62/74 (83.8%) |
| alias | 54 | 2 (9) | 2 | 9 | 0 | 0 | 0 | 0 | 1 | 9/74 (12.2%) / 62/74 (83.8%) |
| both | 54 | 2 (9) | 2 | 9 | 0 | 0 | 0 | 0 | 1 | 9/74 (12.2%) / 62/74 (83.8%) |

## Shadow 3x confirm N=20 (no-regress check)

| Varian | Hits | Saved LLM | Disagree | Wrong |
|---|---|---|---|---|
| plain | 3 | 0 | 0 | 0 |
| stem | 5 | 0 | 0 | 0 |
| alias | 5 | 0 | 0 | 0 |
| both | 5 | 0 | 0 | 0 |

## Safety — noise OCR 25% (wrong harus 0)

| Varian | Hits | Wrong | Disagree |
|---|---|---|---|
| plain | 3 | 0 | 0 |
| stem | 5 | 0 | 0 |
| alias | 5 | 0 | 0 |
| both | 5 | 0 | 0 |

## Interpretasi

- `Collision` = key sama → tingkat pipeline beda (risiko over-merge stem/both). Gate: 0.
- `FST merged` = 1 jika varian menyatukan pasangan FST jadi 1 key (stem/alias/both).
- `Wrong`/`Disagree` = 0 semua varian = normalisasi key tidak menurunkan kualitas. Keputusan varian final menunggu data riil (alias = konservatif, stem = general tapi over-merge risk).