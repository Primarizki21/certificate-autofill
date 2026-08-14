# KB-SCALE-005 — Proyeksi akurasi & biaya produksi end-to-end

> Generasi: 2026-08-14 15:35:08 | SEED=42 | confirm 3x | 0 LLM runtime | korpus 74 (label terukur)

**Model (nilai terukur):** router exact 100% (45/45) | KB serve benar 97.2% (SCALE-001) | LLM exact 58.6% (17/29 non-routed) | token/call 176 (v9).

| N | Skew | Akurasi tanpa KB | Akurasi dgn KB | LLM calls tanpa KB | dgn KB | Token tanpa KB | dgn KB | Hemat biaya |
|---|---|---|---|---|---|---|---|---|
| 500 | 70% | 94.6% | 95.8% | 65 | 50 | 11440 | 8800 | 23% |
| 500 | 80% | 96.6% | 96.8% | 41 | 39 | 7216 | 6864 | 5% |
| 500 | 90% | 98.2% | 98.2% | 22 | 22 | 3872 | 3872 | 0% |
| 5000 | 70% | 94.5% | 99.2% | 668 | 57 | 117568 | 10032 | 91% |
| 5000 | 80% | 96.3% | 99.3% | 446 | 57 | 78496 | 10032 | 87% |
| 5000 | 90% | 98.5% | 99.5% | 184 | 57 | 32384 | 10032 | 69% |

## GATE (80/20, N=5000)

- Akurasi dgn KB (99.3%) >= tanpa KB (96.3%) → PASS
- Hemat biaya (87%) >= 50% → PASS
- **VERDICT: PASS**

## Interpretasi

- **KB tidak menurunkan akurasi**: serve KB (97.2%) > LLM fallback (58.6%) → akurasi akhir dgn KB >= tanpa KB di semua kombinasi.
- Hemat biaya = hemat calls (KB menggantikan LLM di key populer) — KB = cache yang LEBIH akurat dari LLM (key populer = jawaban terverifikasi 3x).
- Proyeksi memakai label korpus 74 (bukan sintetis); distribusi request = simulasi. Validasi akhir tetap audit.py di data riil.