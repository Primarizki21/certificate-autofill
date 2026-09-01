# B6 — Nomor Normalizer v6 (length-preserving DPKKA + guard Roman, N=74)

> Generasi: 2026-09-01 19:18:38 | GT v9 + matcher v2.

| Varian | exact | fuzzy |
|---|---|---|
| v4.2 (normalize_nomor_v5) | 92.3% (48/52) | 92.3% |
| **v6 (preserve + guard)** | **92.3%** (48/52) | **92.3%** |

**Gate**: exact >= 66.7% -> PASS | zero-regression -> PASS (fix 0, regress 0)

Unit test invariant: `tests/test_nomor_v6.py` (13 tests) — panjang digit
terjaga, prefix NOMOR/NUMBER didukung, "1" polos tidak di-overcorrect,
DPKKA O-run -> flag 0.78 (review).
