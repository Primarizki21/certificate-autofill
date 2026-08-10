# F2 — Rule Mining dari 29 Cert LLM-Fallback

> Generasi: 2026-08-10 08:32:41 | GT v9 + matcher v2 | router = llm_router_v4 + kandidat rule | 5-fold seed 42

## Coverage

| Skenario | Routed | Precision | LLM calls (est.) |
|---|---|---|---|
| Router v9 saja | 45 | 100.0% | 29 |
| Router v9 + kandidat | 50 | 100.0% | 24 |

## Kandidat rule — full sample & 5-fold

| Rule | fires | precision | min fold prec | folds (fires, prec) | verdict |
|---|---|---|---|---|---|
| bem+hima | 2 | 100.0% | 100.0% | f1:1(100%), f3:1(100%) | LOW-N |
| bem+sem | 3 | 100.0% | 100.0% | f2:1(100%), f4:2(100%) | LOW-N |
| bem_no_univ | 2 | 100.0% | 100.0% | f0:1(100%), f3:1(100%) | LOW-N |
| dept+fak | 2 | 100.0% | 100.0% | f1:2(100%) | LOW-N |
| dept+hima+univ | 2 | 100.0% | 100.0% | f0:1(100%), f1:1(100%) | LOW-N |
| dept+sem | 5 | 100.0% | 100.0% | f0:2(100%), f2:2(100%), f4:1(100%) | stable |
| fak+univ | 3 | 100.0% | 100.0% | f0:1(100%), f3:1(100%), f4:1(100%) | LOW-N |
| hima+luar | 1 | 100.0% | 100.0% | f1:1(100%) | LOW-N |
| hima_dept | 2 | 100.0% | 100.0% | f2:1(100%), f3:1(100%) | LOW-N |
| lomba+org | 15 | 100.0% | 100.0% | f0:3(100%), f1:3(100%), f2:3(100%), f3:3(100%), f4:3(100%) | stable |
| lomba_merged+org | 3 | 100.0% | 100.0% | f0:1(100%), f1:1(100%), f4:1(100%) | LOW-N |
| sem+univ | 1 | 100.0% | 100.0% | f0:1(100%) | LOW-N |
| tingkat_nasional | 5 | 100.0% | 100.0% | f0:1(100%), f1:2(100%), f2:1(100%), f3:1(100%) | stable |
| ukm_org | 3 | 100.0% | 100.0% | f0:1(100%), f3:1(100%), f4:1(100%) | LOW-N |
| univ+luar | 1 | 100.0% | 100.0% | f3:1(100%) | LOW-N |

## Analisis 29 cert unrouted v9 (LLM vs GT)

- LLM benar: 17/29 (58.6%) — fallback 29 cert memang kasus ambigu (LLM tidak superior pada subset ini).
- Pola yang ditemukan: `UKM` di organizer → GT Universitas (3/3, konsisten); `hima_dept` → GT bercampur (Departemen vs Nasional — jangan jadi rule tanpa guard).
- Pola lain tidak konsisten: `luar` saja (Nasional/Universitas/Fakultas), `dept` saja (Nasional/Internasional), `lomba` saja (Nasional/Universitas).

## Keputusan

- **R14 `ukm_org`**: 3/3 @100% full-sample, semua fold 100% → kandidat layak (LOW-N: fire 3 — klaim robustness butuh data baru).
- **R15 `hima_dept`**: precision 60% (2 salah) → **TIDAK jadi rule** (masuk KB-kandidat, bukan rule permanen).