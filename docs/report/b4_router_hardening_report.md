# B4 — Router Hardening & Stratified 5-Fold CV (N=74, 0 LLM)

> Generasi: 2026-09-01 18:57:08 | GT v9 | rule FIXED (tidak di-fit) |
fold = 5-fold stratified seed 42 | matcher: v2.

**Coverage v7: 64/74 routed** (gate >= 63) -> PASS

| Rule | Fire | Wrong | Min-Fold Precision | LOW-N |
|---|---|---|---|---|
| aphsa_fkm | 1 | 0 | 100% | ya |
| bem_nasional_act | 1 | 0 | 100% | ya |
| kim_unair | 0 | 0 | - | ya |
| dpkka_unair | 0 | 0 | - | ya |
| intl_explicit | 1 | 0 | 100% | ya |
| literasi_psikologi | 1 | 0 | 100% | ya |
| ub_external_event | 1 | 0 | 100% | ya |
| direktur_kemahasiswaan_unair | 1 | 0 | 100% | ya |

**Gate min-fold precision 100%: PASS**

Detail per-fold:

- aphsa_fkm: fold0=0 (-), fold1=0 (-), fold2=1 (OK), fold3=0 (-), fold4=0 (-)
- bem_nasional_act: fold0=1 (OK), fold1=0 (-), fold2=0 (-), fold3=0 (-), fold4=0 (-)
- kim_unair: fold0=0 (-), fold1=0 (-), fold2=0 (-), fold3=0 (-), fold4=0 (-)
- dpkka_unair: fold0=0 (-), fold1=0 (-), fold2=0 (-), fold3=0 (-), fold4=0 (-)
- intl_explicit: fold0=1 (OK), fold1=0 (-), fold2=0 (-), fold3=0 (-), fold4=0 (-)
- literasi_psikologi: fold0=0 (-), fold1=0 (-), fold2=0 (-), fold3=1 (OK), fold4=0 (-)
- ub_external_event: fold0=0 (-), fold1=0 (-), fold2=0 (-), fold3=1 (OK), fold4=0 (-)
- direktur_kemahasiswaan_unair: fold0=0 (-), fold1=0 (-), fold2=0 (-), fold3=0 (-), fold4=1 (OK)

Catatan: rule tidak pernah di-fit dari data — presisi per fold mengukur
stabilitas; cert yang salah di semua fold = aturan tidak generalized.
