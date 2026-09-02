# ORG-TESS-V8-001 — Empirical Validation

> Dataset frozen: `Ground_Truth_Sertifikat_v9.csv`; evaluator: matcher v2; seed: 42; bootstrap: 1000x.
> Scope: staging-only Tesseract organizer candidate. Production backend unchanged.

## Gate Summary

| Corpus | Baseline exact | v8 exact | Gate | Scan framework no-regression | Date/number no-regression |
|---|---:|---:|---|---|---|
| pure | 34/74 | 39/74 | FAIL (≥45) | PASS | PASS |
| primary | 40/74 | 44/74 | FAIL (≥50) | PASS | PASS |

## 1. Stratified 5-Fold CV

Folds are stratified by scan versus embedded corpus and assigned deterministically. Rules are fixed; no fold is used to refit the extractor.

### pure

| Fold | N | Baseline exact | v8 exact |
|---:|---:|---:|---:|
| 1 | 15 | 6 | 4 |
| 2 | 15 | 6 | 8 |
| 3 | 15 | 5 | 7 |
| 4 | 15 | 10 | 11 |
| 5 | 14 | 7 | 9 |

| Rule/source | N | Exact | Precision | Min-fold precision | Low-N (<5) |
|---|---:|---:|---:|---:|---|
| `organizer_v2` | 18 | 6 | 33.33% | 0.00% | NO |
| `organizer_v8:phrase` | 18 | 14 | 77.78% | 33.33% | NO |
| `organizer_v8:signer` | 35 | 18 | 51.43% | 33.33% | NO |
| `organizer_v8:signer_join` | 1 | 1 | 100.00% | 100.00% | YES |
| `regex_organizer` | 2 | 0 | 0.00% | 0.00% | YES |

### primary

| Fold | N | Baseline exact | v8 exact |
|---:|---:|---:|---:|
| 1 | 15 | 8 | 7 |
| 2 | 15 | 7 | 10 |
| 3 | 15 | 8 | 8 |
| 4 | 15 | 9 | 9 |
| 5 | 14 | 8 | 10 |

| Rule/source | N | Exact | Precision | Min-fold precision | Low-N (<5) |
|---|---:|---:|---:|---:|---|
| `organizer_v2` | 12 | 6 | 50.00% | 0.00% | NO |
| `organizer_v7` | 20 | 15 | 75.00% | 60.00% | NO |
| `organizer_v8:phrase` | 12 | 10 | 83.33% | 50.00% | NO |
| `organizer_v8:signer` | 23 | 12 | 52.17% | 33.33% | NO |
| `organizer_v8:signer_join` | 1 | 1 | 100.00% | 100.00% | YES |
| `regex_organizer` | 6 | 0 | 0.00% | 0.00% | NO |

## 2. Bootstrap Confidence Interval

| Corpus | Exact mean | 95% CI | Delta mean vs baseline | Delta 95% CI |
|---|---:|---:|---:|---:|
| pure | 52.70% | [41.89%, 63.51%] | 6.76% | [-6.76%, 18.92%] |
| primary | 59.46% | [48.65%, 70.27%] | 5.41% | [-5.41%, 16.22%] |

## 3. OOD Stress Test

Entity mutation replaces Airlangga/UNAIR with Surabaya/UNS. OCR noise uses deterministic 5↔S, 8↔B, 0↔O, 1↔I substitutions.

### pure

| Probe | N | Exact | Accuracy |
|---|---:|---:|---:|
| Entity mutation | 74 | 27 | 36.49% |
| OCR noise 10% | 74 | 19 | 25.68% |
| OCR noise 25% | 74 | 14 | 18.92% |
| OCR noise 50% | 74 | 9 | 12.16% |

### primary

| Probe | N | Exact | Accuracy |
|---|---:|---:|---:|
| Entity mutation | 74 | 30 | 40.54% |
| OCR noise 10% | 74 | 18 | 24.32% |
| OCR noise 25% | 74 | 13 | 17.57% |
| OCR noise 50% | 74 | 9 | 12.16% |

## 4. Structural Semantic Anchor Audit

- Event-title literals in extractor source: **0** (none).
- Required anchors: `{'indonesian_organizer_phrase': True, 'english_organizer_phrase': True, 'signer_role_anchor': True, 'date_anchor': True, 'number_guard': True}`.
- Verdict: **PASS**; rules use structural phrase, signer-role, date, and number guards.

## 5. Calibrated Confidence & Safety Net

- **pure**: 35 organizer mismatches; protocol threshold 0.85 flags 56/74 with recall 88.57%; runtime threshold 0.80 flags 4/74 with recall 5.71%.
- **primary**: 30 organizer mismatches; protocol threshold 0.85 flags 42/74 with recall 76.67%; runtime threshold 0.80 flags 5/74 with recall 13.33%.

## Verdict

- Pure gate: **FAIL** (target ≥45/74).
- Primary gate: **FAIL** (target ≥50/74).
- Four-layer evidence is recorded above; failed gates remain staging knowledge and are not promoted to production.
