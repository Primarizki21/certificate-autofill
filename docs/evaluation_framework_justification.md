# Justification: Tiered Evaluation Framework

## Why Not Just Exact Match?

Exact match (string equality) is the strictest evaluation metric. It fails when the
same information is expressed differently — which happens constantly with
certificate extraction:

| Ground Truth | Pipeline Output | Exact Match |
|---|---|---|
| BEM FTMM Universitas Airlangga | Badan Eksekutif Mahasiswa Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga | ✗ |
| SPECTA | SPECTA 2024 | ✗ |
| Himatesda | HIMATESDA | ✗ |

All three are correct extractions, but exact match scores 0%.

---

## Academic Basis

### 1. Exact Match + Token F1 — Standard NLP Practice

Brenndoerfer (2026), "Exact Match and F1: Precision Metrics for NLP Evaluation":

> *"Exact Match is the strictest standard: a prediction is correct only if it
> matches the reference character-for-character. F1 offers a softer, more granular
> measure, balancing precision and recall at the token level, rewarding partial
> overlaps."*

This is the standard in SQuAD (question answering) and CoNLL-2003 (NER). **Both
metrics are always reported together.** EM alone is considered incomplete.

### 2. Relaxed Matching for Document Extraction

Yashwant et al. (2510.15727), "Invoice Information Extraction: Methods and Performance Evaluation":

> *"Exact match and relaxed match scoring to account for strict correctness versus
> partial or fuzzy matches (e.g., text normalization or OCR-induced variants)."*

This paper explicitly uses **both exact and relaxed matching** for document
extraction evaluation — directly applicable to our certificate extraction task.

### 3. Per-Field Evaluation over End-to-End Accuracy

KIEval (2503.05488):

> *"Entity-level F1 score is one of the most commonly used metrics for Document
> KIE model evaluation. The predicted pair is considered valid if an exact-match
> can be found in the ground-truth set."*

Our own findings (`rangkuman_findings_v3.docx`, Section 3.7):

> *"Group-level F1 (82.11 untuk CORD) lebih rendah dari Entity F1 (95.13) —
> artinya field individu terekstrak baik tapi asosiasi antar field terkadang salah."*

### 4. Fuzzy Matching in Production OCR Systems

extract-eval (FAIRmat-NFDI):

> *"Exact match against a gold JSON is useless — 'New York' vs 'NYC', 42 vs 42.0
> are semantically equivalent but fail string equality."*

Klippa/Doxis (production OCR):

> *"Fuzzy Word Matching can be applied. In cases where OCR fails to find an exact
> match when extracting certain data fields, Fuzzy Matching can help find the
> closest match with approximate string matching."*

### 5. Token Overlap — Standard for Partial Credit

Token-level F1 is the standard SQuAD metric, computed as:

```
Precision = shared_tokens / predicted_tokens
Recall    = shared_tokens / ground_truth_tokens
F1        = 2 * P * R / (P + R)
```

Our `token_overlap >= 0.5` is a simplified binary version of this.

---

## Our Implementation

| Tier | Metric | Source | Applies To |
|---|---|---|---|
| **Exact** | Normalized string equality | SQuAD EM, CoNLL-2003 | `tingkat`, `jenis_penyelenggara`, dates, cert numbers |
| **Contains** | Substring in either direction | extract-eval `oneof` | `nama_kegiatan_sertifikasi`, `penyelenggara_kegiatan` |
| **Token overlap** | ≥50% shared non-stop tokens | SQuAD token F1 | Abbreviation ↔ full name cases (e.g., BEM vs Badan Eksekutif Mahasiswa) |

### Why This Is Not Over-Engineering

1. **Every tier is standard in NLP evaluation** — EM + F1 is the bare minimum
2. **Downstream cost** — a field extracted as "Universitas Airlangga" vs "UNAIR" is
   equally usable in the form; punishing this with 0% hurts evaluation signal
3. **Transparent reporting** — we report both exact and fuzzy, not hiding the gap

### References

| Paper | ID | Relevance |
|---|---|---|
| KIEval | 2503.05488 | Per-field F1, group-level evaluation |
| Invoice IE Methods | 2510.15727 | Exact + relaxed match for document extraction |
| Information Redundancy | 2304.14936 | Warning: SROIE 75% overlap inflates F1 |
| extract-eval | FAIRmat-NFDI | Per-field comparators (exact/numeric/semantic) |
| Extract-0 | 2509.22906 | Semantic similarity reward for extraction |
| EM + F1 | Brenndoerfer 2026 | Token-level F1 for partial credit |
