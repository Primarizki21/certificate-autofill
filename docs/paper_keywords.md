# Paper Keywords — Certificate Autofill

> Format: satu query per baris, siap copy-paste ke Google Scholar / Semantic Scholar / arXiv.
> Setiap query punya short description kenapa perlu.
> Gunakan file ini untuk riset literatur oleh agent atau manual.

---

## Group A: LLM untuk Document Field Extraction

### A1 — Core Queries

- `large language model document information extraction benchmark`
  → Justifikasi: akurasi LLM vs rule-based untuk ekstraksi field dari dokumen terstruktur.
- `prompt engineering structured extraction JSON zero-shot`
  → Justifikasi: best practice prompt design untuk output terstruktur (JSON mode / function calling).
- `few-shot named entity recognition LLM document`
  → Justifikasi: seberapa sedikit contoh yang dibutuhkan LLM untuk NER di dokumen baru.
- `LLM document understanding evaluation FUNSD SROIE CORD`
  → Justifikasi: benchmark dataset untuk document understanding (FUNSD, SROIE, CORD).
- `large language model form understanding extraction`
  → Justifikasi: spesifik ke form extraction / key-value extraction dari dokumen.

### A2 — Exploratory Queries

- `LLM hallucination structured extraction mitigation`
  → Justifikasi: strategi mengurangi halusinasi LLM saat ekstraksi field.
- `cost comparison LLM vs traditional NLP information extraction`
  → Justifikasi: analisis biaya LLM API vs model lokal untuk production scale.
- `small language model fine-tuning document extraction`
  → Justifikasi: alternatif model kecil yang bisa di-fine-tune (Phi, Gemma, Qwen).
- `multilingual document information extraction LLM`
  → Justifikasi: handling dokumen bilingual (Indonesia + Inggris).

---

## Group B: Hybrid Rule-Based + ML

### B1 — Core Queries

- `hybrid information extraction rule-based machine learning tradeoff`
  → Justifikasi: kapan pakai rule vs ML vs LLM, dan bagaimana mengkombinasikannya.
- `rule-based vs machine learning NLP production system`
  → Justifikasi: practical comparison untuk production deployment.
- `cascade architecture information extraction pipeline`
  → Justifikasi: arsitektur multi-tier seperti yang sudah dipakai (fast path → fallback).

### B2 — Exploratory Queries

- `transformer encoder decoder NER document extraction`
  → Justifikasi: arsitektur transformer untuk NER di dokumen (non-LLM).
- `layout aware document understanding transformer`
  → Justifikasi: ekstraksi yang mempertimbangkan posisi/layout teks dalam dokumen.
- `graph neural network information extraction document`
  → Justifikasi: alternatif GNN untuk relasi antar field.

---

## Group C: Confidence Calibration

### C1 — Core Queries

- `confidence calibration information extraction NLP`
  → Justifikasi: ganti confidence palsu (hardcoded) dengan confidence statistik yang valid.
- `Platt scaling isotonic regression text classification calibration`
  → Justifikasi: metode kalibrasi probabilitas untuk classifier.
- `uncertainty quantification information extraction`
  → Justifikasi: bagaimana mengukur ketidakpastian hasil ekstraksi secara rigorous.
- `conformal prediction NLP information extraction`
  → Justifikasi: framework modern untuk confidence dengan garansi statistik.

### C2 — Exploratory Queries

- `calibrated confidence score practical production NLP`
  → Justifikasi: implementasi praktis kalibrasi di production.
- `Bayesian deep learning uncertainty document processing`
  → Justifikasi: pendekatan Bayesian untuk uncertainty.

---

## Group D: Document Image Preprocessing

### D1 — Core Queries

- `document image preprocessing OCR accuracy deskew binarization`
  → Justifikasi: teknik preprocessing yang meningkatkan akurasi OCR.
- `scan quality enhancement text extraction deep learning`
  → Justifikasi: enhancement berbasis DL untuk dokumen hasil scan.
- `RapidOCR vs Tesseract benchmark accuracy speed`
  → Justifikasi: perbandingan objektif engine OCR untuk production.

### D2 — Exploratory Queries

- `document dewarping OCR accuracy improvement`
  → Justifikasi: koreksi distorsi pada dokumen yang difoto (bukan scan flat).
- `super resolution document image OCR`
  → Justifikasi: meningkatkan resolusi teks kecil seperti tanggal di sertifikat.
- `mobile document capture OCR preprocessing`
  → Justifikasi: preprocessing untuk dokumen yang diupload dari handphone.

---

## Group E: Evaluation Framework

### E1 — Core Queries

- `information extraction evaluation metrics precision recall F1`
  → Justifikasi: framework evaluasi standard untuk IE.
- `inter annotator agreement information extraction annotation guidelines`
  → Justifikasi: quality control untuk pembuatan labeled dataset.
- `cross validation NLP model evaluation production`
  → Justifikasi: metodologi evaluasi yang rigorous untuk production model.
- `A/B testing machine learning production evaluation`
  → Justifikasi: framework A/B test untuk membandingkan rule lama vs baru.

### E2 — Exploratory Queries

- `key information extraction KIE benchmark SROIE FUNSD`
  → Justifikasi: standard benchmark untuk document KIE.
- `field level extraction accuracy vs end to end document accuracy`
  → Justifikasi: metrik yang tepat — per-field atau end-to-end?

---

## Group F: Feedback Loop & Active Learning

### F1 — Core Queries

- `active learning information extraction document`
  → Justifikasi: strategi memilih sample yang paling informatif untuk dilabeli.
- `human in the loop document processing correction feedback`
  → Justifikasi: integrasi koreksi user ke dalam pipeline learning.
- `weak supervision data programming information extraction`
  → Justifikasi: memanfaatkan rule-based extraction sebagai "weak label" untuk training.

### F2 — Exploratory Queries

- `online learning streaming data NLP production`
  → Justifikasi: model yang terus belajar dari data baru tanpa retraining penuh.
- `crowdsourcing ground truth annotation document extraction`
  → Justifikasi: strategi pengumpulan labeled data dengan crowdsourcing.
- `semi-supervised learning limited labeled data NER`
  → Justifikasi: training dengan data labeled terbatas (realistis untuk proyek ini).

---

## Group G: Model Distillation & Efficient Deployment

### G1 — Core Queries

- `model distillation BERT information extraction`
  → Justifikasi: transisi LLM → model kecil yang fine-tuned.
- `knowledge distillation large language model small model extraction`
  → Justifikasi: teknik distilasi spesifik dari LLM ke model kecil.
- `efficient transformer inference production GPU CPU`
  → Justifikasi: optimasi inference untuk production (ONNX, quantization, pruning).
- `cost efficient LLM deployment production batch processing`
  → Justifikasi: strategi deployment LLM yang hemat biaya.

### G2 — Exploratory Queries

- `ONNX runtime transformer inference optimization`
  → Justifikasi: export model ke ONNX untuk inference cepat.
- `quantization aware training NLP model`
  → Justifikasi: teknik kompresi model tanpa kehilangan akurasi signifikan.
- `model serving throughput optimization batch inference`
  → Justifikasi: optimasi throughput untuk ribuan request bersamaan.

---

## Group H: Layout-Aware Extraction

### H1 — Core Queries

- `layoutLM document understanding spatial information extraction`
  → Justifikasi: model yang mempertimbangkan layout + teks (bukan cuma teks).
- `visual document understanding transformer multimodal`
  → Justifikasi: ekstraksi dari informasi visual (logo, tanda tangan, stempel).
- `document layout analysis object detection certificate`
  → Justifikasi: deteksi region of interest (ROI) di sertifikat.

### H2 — Exploratory Queries

- `table extraction document transformer`
  → Justifikasi: ekstraksi data tabular (jika sertifikat punya tabel).
- `document structure parsing hierarchical information extraction`
  → Justifikasi: memahami struktur hierarkis dokumen.

---

## Group I: Production-Scale Architecture

### I1 — Core Queries

- `asynchronous document processing queue batch architecture`
  → Justifikasi: arsitektur untuk handle ribuan request bersamaan.
- `horizontal scaling OCR document processing Kubernetes`
  → Justifikasi: strategi scaling OCR di production.
- `caching strategy document processing pipeline`
  → Justifikasi: cache hasil extraction untuk dokumen yang sama (content-addressed).
- `fault tolerance document processing pipeline retry circuit breaker`
  → Justifikasi: resilience pattern untuk pipeline multi-tier.

### I2 — Exploratory Queries

- `observability monitoring document extraction pipeline`
  → Justifikasi: metrik dan alerting untuk production extraction pipeline.
- `cost analysis document processing pipeline cloud vs on-premise`
  → Justifikasi: analisis biaya deployment production.

---

## Cara Pakai (untuk Agent)

1. Pilih group yang relevan dengan task.
2. Copy query dari section **Core Queries**.
3. Search di Google Scholar / Semantic Scholar / arXiv.
4. Prioritaskan paper dengan citation > 10 dan tahun >= 2022.
5. Untuk tiap paper: baca abstract → kalau relevan, baca methodology section.
6. Hasil temuan dicatat di `docs/paper_findings.md` (buat file baru kalau belum ada).

## Cara Pakai (untuk Manusia)

1. Cari topik di daftar isi (Group A–I).
2. Core queries = harus dicari. Exploratory = dicari kalau core sudah ketemu.
3. Gunakan query yang bold sebagai starting point di Google Scholar.
4. Kalau hasil terlalu banyak, tambahkan filter tahun: `... 2023 2024`.
