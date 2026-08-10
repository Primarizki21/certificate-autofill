# Instruksi Lengkap: Generate Rangkuman Kurasi Paper Findings (.docx → .pdf)

> **File ini adalah instruksi yang harus dieksekusi oleh coding agent.**
> Ikuti step-by-step tanpa skip. Gunakan skill `humanizer` dan `ai slop` (stop-slop) saat menulis konten dokumen.

---

## 0. Konteks Proyek

Proyek **Certificate Autofill** adalah sistem untuk mengekstrak field (nama, tanggal, institusi, dll.) dari gambar sertifikat/dokumen menggunakan pipeline OCR + NLP/LLM. Literature review telah dilakukan dengan 57 queries di 9 kelompok topik, menghasilkan 200+ paper di file `paper_findings.md`. Tugas kali ini: **kurasi dan rangkum** findings tersebut menjadi dokumen `.docx` yang padat dan informatif, lalu konversi ke `.pdf`.

**Bahasa**: Campuran Indonesia-Inggris (istilah teknis tetap Inggris).
**Target audience**: Dokumentasi internal tim (bukan akademis formal).

---

## 1. Setup Environment

### 1.1 Pastikan `uv` (Astral) Terinstall

```bash
# Cek apakah uv sudah ada
uv --version

# Jika belum, install:
# Windows (PowerShell):
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

> **WAJIB**: Gunakan `uv` untuk SEMUA dependency management. Jangan pakai pip langsung.

### 1.2 Inisialisasi Project & Install Dependencies

```bash
# Init project (skip jika pyproject.toml sudah ada)
if [ ! -f "pyproject.toml" ]; then uv init --name cert-autofill-summary; fi

# Buat virtual environment
if [ ! -d ".venv" ]; then uv venv; fi

# Install dependency
uv add python-docx
```

### Dependencies

| Package | Minimum Version | Kegunaan |
|---------|----------------|----------|
| `python-docx` | ≥1.1.0 | Membuat & memanipulasi file `.docx` |

> Tidak perlu dependency lain. Konversi PDF dilakukan oleh LibreOffice CLI.

---

## 2. Sumber Data

Baca semua file .md di folder `./docs/`:

1. **`./docs/paper_findings.md`** — 1640 baris, berisi 200+ paper dengan abstract. Terstruktur dalam 9 groups (A–I), masing-masing punya Core Queries (X1) dan Exploratory Queries (X2).

2. **`./docs/paper_keywords.md`** — 228 baris, berisi daftar keyword/query dan justifikasinya per group.

---

## 3. Kurasi Paper — Paper Terpilih per Group

**Aturan kurasi**:
- Maks **10 paper per group** (bukan per keyword — satu group bisa punya banyak keyword)
- Pilih berdasarkan **relevansi langsung** ke Certificate Autofill
- **BUANG** paper yang jelas tidak relevan (quantum computing, cancer research, autonomous driving, meme detection, Urdu/Bangla text tanpa konteks transferable, protein analysis, latice mathematics, hopping robots, stochastic PDE, dll.)
- Jika ragu, cek abstract-nya: apakah findings-nya bisa diterapkan ke document/certificate extraction?

Berikut paper yang sudah dikurasi. **Gunakan daftar ini sebagai acuan utama**, tapi kamu boleh menambah/mengurangi berdasarkan pembacaan abstract yang lebih mendalam, selama tetap dalam batas 10 per group.

### Group A — LLM untuk Document Field Extraction

| No | ArXiv ID | Judul Singkat | Tahun | Alasan Dipilih |
|----|----------|---------------|-------|----------------|
| 1 | 2309.10952 | LMDX: Language Model-based Document IE and Localization | 2023 | Langsung tentang LLM untuk document information extraction, mengatasi keterbatasan layout encoding |
| 2 | 2509.22906 | Extract-0: Specialized LM for Document IE | 2025 | Model 7B khusus document IE, menggunakan LoRA + GRPO, benchmark 1000 dokumen |
| 3 | 2305.14450 | An Empirical Study on IE using LLMs | 2023 | Benchmark komprehensif kemampuan IE dari GPT family, perbandingan LLM vs task-specific |
| 4 | 2304.14936 | Information Redundancy and Biases in Public Document IE Benchmarks | 2023 | Analisis kelemahan benchmark KIE (SROIE, FUNSD), penting untuk memahami limitasi evaluasi |
| 5 | 2309.05429 | Improving IE on Business Documents with Specific Pre-Training | 2023 | LayoutLM dengan pre-training task baru untuk business documents, transferable ke sertifikat |
| 6 | 2308.09341 | Document Automation Architectures: Updated Survey | 2023 | Survey komprehensif arsitektur document automation termasuk LLM |
| 7 | 2305.03253 | VicunaNER: Zero/Few-shot NER using Vicuna | 2023 | Framework zero/few-shot NER dengan open-source LLM, bisa dipakai tanpa fine-tuning banyak |
| 8 | 2403.13369 | Clinical IE for Low-resource with Few-shot Learning | 2024 | Few-shot IE untuk low-resource language, relevan untuk konteks Indonesia |
| 9 | 2505.17125 | NEXT-EVAL: Evaluation of Traditional and LLM Web Data Extraction | 2025 | Framework evaluasi perbandingan rule-based vs LLM extraction |
| 10 | 2304.12484 | DocParser: End-to-end OCR-free IE from Visually Rich Documents | 2023 | Pendekatan OCR-free untuk document IE, alternatif arsitektur |

**Catatan A-Exploratory** (tambahan yang patut disebut dalam rangkuman):

| No | ArXiv ID | Judul Singkat | Tahun | Alasan Dipilih |
|----|----------|---------------|-------|----------------|
| 1 | 2502.11306 | Smoothing Out Hallucinations via Knowledge Distillation | 2025 | Mitigasi halusinasi LLM untuk extraction |
| 2 | 2402.10612 | Rowen: Adaptive RAG for Hallucination Mitigation | 2024 | RAG untuk mengurangi halusinasi saat extraction |
| 3 | 2509.08381 | Low-Resource Fine-Tuning for Multi-Task Structured IE (1B params) | 2025 | Model 1B untuk structured IE, bukti small model bisa efektif |
| 4 | 2505.13535 | IE from VRDs using LLM-based Organization | 2025 | LLM untuk visually rich documents, langsung relevan |
| 5 | 2508.14314 | Zero-knowledge LLM Hallucination Detection | 2025 | Cross-model consistency untuk deteksi halusinasi tanpa knowledge base |

---

### Group B — Hybrid Rule-Based + ML

| No | ArXiv ID | Judul Singkat | Tahun | Alasan Dipilih |
|----|----------|---------------|-------|----------------|
| 1 | 2305.14450 | An Empirical Study on IE using LLMs | 2023 | Perbandingan LLM vs traditional NLP untuk IE — basis memilih kapan pakai mana |
| 2 | 2512.13031 | Comprehensive Eval of Rule-Based, ML, and Deep Learning | 2025 | Perbandingan langsung 3 pendekatan: rule-based, ML tradisional, deep learning |
| 3 | 2509.08381 | Low-Resource Fine-Tuning for Multi-Task Structured IE | 2025 | Bukti model kecil (1B) bisa efektif untuk structured IE |
| 4 | 2406.05348 | Toward Reliable Ad-hoc Scientific IE | 2024 | GPT-4 untuk IE dengan analisis error manual, insight practical limitations |
| 5 | 2404.01462 | OpenChemIE: IE Toolkit for Chemistry Literature | 2024 | Contoh pipeline multi-modal IE (teks + tabel + gambar) |
| 6 | 2404.05225 | LayoutLLM: Layout Instruction Tuning for Document Understanding | 2024 | Layout-aware LLM instruction tuning, 143 sitasi |
| 7 | 2306.00526 | Layout and Task Aware Prompt for Zero-shot DocVQA | 2023 | Prompting yang mempertimbangkan layout, 36 sitasi |
| 8 | 2309.05429 | Improving IE on Business Documents | 2023 | Pre-training task untuk business document IE (LayoutLM) |
| 9 | 2308.07777 | Enhancing VRD Understanding via Layout Structure Modeling | 2023 | Model layout structure untuk document understanding |
| 10 | 2305.00795 | SelfDocSeg: Self-Supervised Document Segmentation | 2023 | Self-supervised approach untuk document segmentation tanpa labeled data |

---

### Group C — Confidence Calibration

| No | ArXiv ID | Judul Singkat | Tahun | Alasan Dipilih |
|----|----------|---------------|-------|----------------|
| 1 | 2410.01609 | SynJAC: Synthetic-data-driven Joint Adaptation and Calibration for Document KIE | 2024 | Langsung tentang kalibrasi confidence pada scanned document KIE menggunakan synthetic data — PALING RELEVAN untuk certificate autofill |
| 2 | 2604.09529 | VL-Calibration: Decoupled Confidence Calibration for VLMs | 2026 | Kalibrasi confidence untuk Vision-Language Models yang membaca gambar dokumen — langsung applicable jika pakai GPT-4V/Qwen-VL |
| 3 | 2305.14975 | Just Ask for Calibration: Eliciting Calibrated Confidence from RLHF LLMs | 2023 | Cara mendapatkan skor confidence terkalibrasi dari LLM instruction-tuned — essential untuk menandai field yang perlu review manual |
| 4 | 2412.14737 | On Verbalized Confidence Scores for LLMs | 2024 | Analisis skor confidence yang di-verbalize LLM dalam JSON output — langsung relevan untuk prompt extraction |
| 5 | 2410.06615 | QA-Calibration of LM Confidence Scores | 2024 | Kalibrasi confidence untuk generative QA/extraction — applicable saat framing extraction sebagai QA ("Apa tanggal sertifikat?") |
| 6 | 2401.13744 | Conformal Prediction Sets Improve Human Decision Making | 2024 | Conformal prediction untuk human-in-the-loop — saat field uncertain, berikan candidate set ke user untuk verifikasi |
| 7 | 2406.02354 | Label-wise Aleatoric and Epistemic Uncertainty Quantification | 2024 | Dekomposisi uncertainty per-field: noisy OCR (aleatoric) vs model uncertainty (epistemic) |
| 8 | 2305.14450 | An Empirical Study on IE using LLMs | 2023 | Benchmark confidence dan reliability dari LLM extraction |
| 9 | 2406.05348 | Toward Reliable Ad-hoc Scientific IE | 2024 | Manual error analysis untuk reliability assessment LLM extraction |
| 10 | 2311.12436 | Classifier Calibration with ROC-Regularized Isotonic Regression | 2023 | Teknik isotonic regression untuk kalibrasi classifier — useful untuk field validation modules |

---

### Group D — Document Image Preprocessing

| No | ArXiv ID | Judul Singkat | Tahun | Alasan Dipilih |
|----|----------|---------------|-------|----------------|
| 1 | 2508.06988 | TADoc: Robust Time-Aware Document Image Dewarping | 2025 | Dewarping dokumen untuk foto dari device — langsung relevan untuk upload sertifikat |
| 2 | 2307.12571 | MataDoc: Margin and Text Aware Document Dewarping | 2023 | Dewarping dengan arbitrary boundary — sertifikat sering difoto tidak sempurna |
| 3 | 2312.07925 | Polar-Doc: One-Stage Document Dewarping | 2023 | Approach efisien untuk dewarping dokumen |
| 4 | 2508.14557 | Improving OCR using Internal Document Redundancy | 2025 | Memanfaatkan redundansi internal dokumen untuk OCR lebih baik |
| 5 | 2309.05503 | Long-Range Transformer for Document Understanding | 2023 | Multi-page document understanding dengan Transformer |
| 6 | 2304.12484 | DocParser: End-to-end OCR-free IE from VRDs | 2023 | Alternatif tanpa OCR untuk document IE |
| 7 | 2306.10046 | Document Layout Annotation: Database and Benchmark | 2023 | Benchmark untuk document layout analysis |
| 8 | 2403.07553 | GPT and Donut for Table of Content Processing | 2024 | Donut (OCR-free) + GPT untuk document indexing |
| 9 | 2508.21693 | Why Stop at Words? Line-Level OCR | 2025 | Line-level OCR sebagai improvement dari word-level |
| 10 | 2309.05429 | Improving IE on Business Documents | 2023 | Pre-training untuk business document dengan preprocessing context |

---

### Group E — Evaluation Framework

| No | ArXiv ID | Judul Singkat | Tahun | Alasan Dipilih |
|----|----------|---------------|-------|----------------|
| 1 | 2305.14450 | An Empirical Study on IE using LLMs | 2023 | Framework evaluasi IE komprehensif |
| 2 | 2503.05488 | KIEval: Evaluation Metric for Document KIE | 2025 | Metrik evaluasi khusus untuk Document KIE — sangat relevan |
| 3 | 2310.03668 | GoLLIE: Annotation Guidelines improve Zero-Shot IE | 2023 | Annotation guidelines untuk IE, quality control |
| 4 | 2504.02871 | Synthesized Annotation Guidelines for Clinical IE | 2025 | Auto-generated guidelines untuk IE annotation |
| 5 | 2510.12835 | Repurposing Annotation Guidelines to Instruct LLM Annotators | 2025 | Transformasi guidelines untuk LLM-based annotation |
| 6 | 2502.16377 | Instruction-Tuning LLMs for Event Extraction with Annotation Guidelines | 2025 | Annotation guidelines untuk instruction tuning |
| 7 | 2505.17125 | NEXT-EVAL: Evaluation Framework for Web Data Extraction | 2025 | Framework evaluasi rule-based vs LLM extraction |
| 8 | 2404.01462 | OpenChemIE: IE Toolkit | 2024 | Contoh evaluation framework untuk multi-modal IE |
| 9 | 2406.05348 | Toward Reliable Ad-hoc Scientific IE | 2024 | Manual error analysis methodology untuk IE |
| 10 | 2404.19329 | End-to-end IE in Handwritten Documents (Paris Marriage Records) | 2024 | End-to-end IE evaluation di real historical documents |

---

### Group F — Feedback Loop & Active Learning

| No | ArXiv ID | Judul Singkat | Tahun | Alasan Dipilih |
|----|----------|---------------|-------|----------------|
| 1 | 2302.08893 | Active Learning for Data Streams: A Survey | 2023 | Survey comprehensive active learning, 109 sitasi |
| 2 | 2308.04332 | RLHF-Blender: Interactive Interface for Learning from Diverse Human Feedback | 2023 | Framework human-in-the-loop untuk ML systems |
| 3 | 2309.05429 | Improving IE on Business Documents | 2023 | Iterative improvement melalui pre-training tasks baru |
| 4 | 2306.10046 | Document Layout Annotation | 2023 | Feedback loop dalam document annotation process |
| 5 | 2305.00795 | SelfDocSeg: Self-Supervised Document Segmentation | 2023 | Self-supervised learning mengurangi kebutuhan labeled data |

> **Catatan**: Group F memiliki paper relevan yang lebih sedikit. Cek section F di `paper_findings.md` — jika ada paper tentang weak supervision / data programming / online learning yang relevan, tambahkan hingga maks 10.

---

### Group G — Model Distillation & Efficient Deployment

| No | ArXiv ID | Judul Singkat | Tahun | Alasan Dipilih |
|----|----------|---------------|-------|----------------|
| 1 | 2501.00031 | Distilling LLMs for Efficient Clinical IE | 2025 | Distilasi LLM ke BERT (1000x lebih kecil) untuk NER — langsung applicable |
| 2 | 2405.17533 | PAE: LLM-based Product Attribute Extraction | 2024 | LLM untuk attribute extraction di e-commerce, transferable ke certificate fields |
| 3 | 2311.08883 | Distilling Rule-based Knowledge into LLMs | 2023 | Menggabungkan rule-based knowledge ke LLM — hybrid approach |
| 4 | 2504.13359 | Cost-of-Pass: Economic Framework for Evaluating LMs | 2025 | Framework ekonomi untuk evaluasi cost-effectiveness LLM |
| 5 | 2509.18101 | Cost-Benefit Analysis On-Premise vs Commercial LLM | 2025 | Analisis biaya on-premise vs API — langsung relevan untuk keputusan deployment |
| 6 | 2602.06370 | Cost-Aware Model Selection for Text Classification | 2026 | Multi-objective trade-off fine-tuned encoder vs LLM prompting |
| 7 | 2411.16313 | CATP-LLM: Cost-Aware Tool Planning | 2024 | LLM yang mempertimbangkan biaya eksekusi tool |
| 8 | 2402.10517 | Any-Precision LLM: Low-Cost Multi-Size Deployment | 2024 | Deploy multiple LLM dengan berbagai presisi dari satu model |
| 9 | 2311.00502 | Efficient LLM Inference on CPUs | 2023 | INT4 quantization untuk inference di CPU — penting untuk deployment hemat |
| 10 | 2607.07052 | Progressive Crystallization: Agent → Deterministic Workflows | 2026 | Transisi dari LLM exploration ke deterministic rules di production |

---

### Group H — Layout-Aware Extraction

| No | ArXiv ID | Judul Singkat | Tahun | Alasan Dipilih |
|----|----------|---------------|-------|----------------|
| 1 | 2410.21169 | Document Parsing Unveiled: Techniques, Challenges, Prospects | 2024 | Survey landmark tentang structured IE dan document parsing — blueprint arsitektur untuk certificate autofill |
| 2 | 2509.11720 | Advanced Layout Analysis Models for Docling | 2025 | RT-DETR real-time layout detection untuk header, seal, signature, body text — langsung applicable |
| 3 | 2406.06236 | UnSupDLA: Unsupervised Document Layout Analysis | 2024 | Layout analysis tanpa annotation manual — mengatasi scarcity labeled certificate data |
| 4 | 2501.05497 | Spatial Information Integration in Small Language Models | 2025 | 2D spatial coordinates + Small LMs untuk document understanding on-premise |
| 5 | 2404.05225 | LayoutLLM: Layout Instruction Tuning for Document Understanding | 2024 | LLM yang di-tune untuk memahami layout, 143 sitasi |
| 6 | 2404.10848 | LayoutLMv3-Based Model for Relation Extraction in VRDs | 2024 | LayoutLMv3 untuk key-value relation extraction — menghubungkan label field ke nilainya |
| 7 | 2309.05429 | Improving IE on Business Documents with Pre-Training | 2023 | Custom pre-training tasks untuk LayoutLM pada business documents |
| 8 | 2309.05503 | Long-Range Transformer for Document Understanding | 2023 | Multi-modal (layout+text) transformer untuk multi-page documents |
| 9 | 2305.00795 | SelfDocSeg: Self-Supervised Document Segmentation | 2023 | Self-supervised visual segmentation mengurangi kebutuhan labeled data |
| 10 | 2403.07553 | GPT and Donut for Document Indexing | 2024 | OCR-free model (Donut) + LLM (GPT) untuk end-to-end document extraction |

---

### Group I — Production-Scale Architecture

| No | ArXiv ID | Judul Singkat | Tahun | Alasan Dipilih |
|----|----------|---------------|-------|----------------|
| 1 | 2403.02310 | Sarathi-Serve: Taming Throughput-Latency Tradeoff | 2024 | Optimasi serving LLM production-grade, 638 sitasi — teknik chunked-prefill |
| 2 | 2302.14017 | Full Stack Optimization of Transformer Inference: Survey | 2023 | Survey komprehensif optimasi inference dari hardware sampai software |
| 3 | 2505.06461 | Challenging GPU Dominance: CPUs for On-Device LLM | 2025 | Bukti empiris CPU bisa outperform GPU di device tertentu — penting untuk deployment hemat |
| 4 | 2412.18934 | Dovetail: CPU/GPU Heterogeneous Speculative Decoding | 2024 | Hybrid CPU/GPU inference untuk consumer-grade devices |
| 5 | 2507.01806 | LoRA Fine-Tuning Without GPUs | 2025 | Fine-tuning LoRA di CPU laptop — sangat relevan untuk resource-constrained teams |
| 6 | 2412.04504 | Multi-Bin Batching for LLM Inference Throughput | 2024 | Strategi batching untuk menangani banyak request bersamaan |
| 7 | 2607.07052 | Progressive Crystallization: Agent → Deterministic Workflows | 2026 | Transisi dari LLM agent ke deterministic rules di production — mengurangi biaya jangka panjang |
| 8 | 2601.22362 | Understanding Efficiency: Quantization, Batching, Serving | 2026 | Analisis trade-off presisi, batching, dan energy efficiency untuk production LLM |
| 9 | 2502.12017 | Scalable ML Inference with Serverless Functions | 2025 | Arsitektur serverless untuk batch ML inference — scaling otomatis |
| 10 | 2405.12311 | SpotKube: Cost-Optimal Microservices with Spot Pricing | 2024 | Optimasi biaya deployment microservices dengan spot instances — relevant untuk cloud deployment |

---

## 4. Struktur Dokumen `.docx`

Buat file: **`./docs/rangkuman_findings.docx`**

### Formatting Rules

- **Font body**: Calibri 11pt
- **Font heading 1**: Calibri 16pt Bold
- **Font heading 2**: Calibri 14pt Bold
- **Font heading 3**: Calibri 12pt Bold
- **Line spacing**: 1.15
- **Margin**: 2.54 cm (default Word)
- **Tabel**: Style `Table Grid`, header row bold dengan background abu-abu muda
- **Referensi paper**: Format `[ArXiv ID]` sebagai inline reference

### Document Outline

```
HALAMAN JUDUL
─────────────
  Judul: "Rangkuman Kurasi Literature Review — Certificate Autofill System"
  Subtitle: "Dokumentasi Internal Tim"
  Tanggal: [auto-generated, format: DD Bulan YYYY]
  Sumber data: paper_findings.md (200+ papers, 57 queries, 9 groups)

═══════════════════════════════════════════
PAGE BREAK
═══════════════════════════════════════════

DAFTAR ISI
──────────
  (Auto-generated dari heading styles)

═══════════════════════════════════════════
PAGE BREAK
═══════════════════════════════════════════

1. PENDAHULUAN
──────────────
  1.1 Latar Belakang Proyek Certificate Autofill
      - Deskripsi singkat proyek: sistem autofill field dari sertifikat
      - Masalah yang diselesaikan: ekstraksi manual lambat dan error-prone
  
  1.2 Tujuan Literature Review
      - Mencari metode terbaik untuk setiap komponen pipeline
      - Membandingkan pendekatan: LLM vs rule-based vs hybrid
  
  1.3 Metodologi Pencarian
      - 57 search queries (33 core, 24 exploratory)
      - Filter: tahun >= 2021 (preferensi >= 2023), sitasi > 10
      - Sumber: arXiv, Google Scholar, Semantic Scholar
      - 9 kelompok topik (Group A–I)
      - Catatan: File sumber (paper_findings.md & paper_keywords.md) berada di direktori ./docs/
  
  1.4 Ringkasan Cakupan
      Tabel overview 9 groups:
      | Group | Topik | Jumlah Paper Awal | Jumlah Terkurasi |
      |-------|-------|-------------------|-----------------|
      | A | LLM Document Extraction | 85 | [hitung] |
      | B | Hybrid Rule+ML | 32 | [hitung] |
      | ... | ... | ... | ... |

═══════════════════════════════════════════

2. RINGKASAN FINDINGS PER GROUP
───────────────────────────────
  
  Untuk SETIAP group (A sampai I), buat section berikut:

  2.X [Nama Group]
  
    2.X.1 Konteks & Relevansi
          Paragraf 2-3 kalimat: mengapa aspek ini penting untuk 
          Certificate Autofill. Tulis dengan skill humanizer dan ai slop.
    
    2.X.2 Paper Terpilih
          Tabel ringkas dari kurasi (Section 3 dokumen ini):
          | No | Paper | Tahun | Temuan Kunci |
          |----|-------|-------|-------------|
    
    2.X.3 Temuan Utama
          Bullet points 3-7 temuan kunci dari paper terkurasi.
          Setiap temuan harus:
          - Spesifik (bukan generik)
          - Disertai referensi paper [ArXiv ID]
          - Langsung bisa ditindaklanjuti untuk Certificate Autofill
    
    2.X.4 Implikasi untuk Certificate Autofill
          Paragraf 2-4 kalimat: apa artinya temuan ini untuk proyek.
          Gunakan skill humanizer dan ai slop.

═══════════════════════════════════════════
PAGE BREAK
═══════════════════════════════════════════

3. VERDICT & REKOMENDASI AKHIR
──────────────────────────────
  
  ** INI ADALAH BAGIAN TERPENTING **
  
  Format: Breakdown per-aspek, setiap aspek punya:
  - Rekomendasi metode
  - Justifikasi dari paper (dengan referensi)
  - Trade-off (kelebihan vs kekurangan)
  - Saran implementasi praktis

  3.1 Metode OCR & Preprocessing
      Berdasarkan Group D findings:
      - Rekomendasi engine OCR
      - Preprocessing pipeline (dewarping, binarization, enhancement)
      - Trade-off akurasi vs kecepatan
  
  3.2 Metode Extraction (Core Engine)
      Berdasarkan Group A & B findings:
      - Rekomendasi pendekatan utama (LLM / rule-based / hybrid)
      - Model spesifik yang disarankan
      - Prompt engineering strategy
      - Handling few-shot vs zero-shot
  
  3.3 Arsitektur Pipeline
      Berdasarkan Group B & I findings:
      - Rekomendasi arsitektur (single-tier vs multi-tier/cascade)
      - Flow: input → preprocessing → extraction → validation → output
      - Async processing strategy
  
  3.4 Layout Understanding
      Berdasarkan Group H findings:
      - Apakah perlu layout-aware extraction
      - Model/teknik yang disarankan
      - Kapan layout penting vs tidak
  
  3.5 Confidence & Quality Assurance
      Berdasarkan Group C findings:
      - Metode kalibrasi confidence score
      - Threshold strategy
      - Fallback mechanism
  
  3.6 Deployment & Optimization
      Berdasarkan Group G findings:
      - Model size recommendation
      - Quantization / distillation strategy
      - On-premise vs API trade-off
      - Cost analysis
  
  3.7 Evaluation Framework
      Berdasarkan Group E findings:
      - Metrik yang direkomendasikan (per-field F1? end-to-end accuracy?)
      - Benchmark dataset yang relevan
      - Annotation quality control
  
  3.8 Continuous Learning
      Berdasarkan Group F findings:
      - Active learning strategy
      - Feedback loop dari user corrections
      - Data augmentation
  
  3.9 Kesimpulan Keseluruhan
      Paragraf 3-5 kalimat: berdasarkan SELURUH bukti dari literature 
      review, proyek Certificate Autofill sebaiknya menggunakan 
      pendekatan [X] karena [Y]. Ini adalah rekomendasi final yang 
      menyintesis semua aspek di atas menjadi satu strategi koheren.
      
      Gunakan skill humanizer dan ai slop untuk bagian ini.

═══════════════════════════════════════════
PAGE BREAK
═══════════════════════════════════════════

4. DAFTAR PUSTAKA
─────────────────
  Format per entry:
  [ArXiv ID] Judul Paper. Tahun. https://arxiv.org/abs/[ID]
  
  Hanya paper yang DIKUTIP di dokumen. Urutkan berdasarkan ArXiv ID.
```

---

## 5. Instruksi Skill — Humanizer & AI Slop

### Kapan Memanggilnya

Panggil skill **humanizer** dan **ai slop (stop-slop)** untuk SETIAP bagian konten naratif:
- Section 1 (Pendahuluan)
- Section 2.X.1 (Konteks & Relevansi) — setiap group
- Section 2.X.3 (Temuan Utama) — setiap group
- Section 2.X.4 (Implikasi) — setiap group
- Section 3 (Verdict & Rekomendasi) — SEMUA sub-section
- Section 3.9 (Kesimpulan Keseluruhan)

### Cara Memanggilnya

Setelah menulis draft konten untuk setiap section:
1. **Panggil skill `humanizer`** — proses teks agar terlihat ditulis manusia
2. **Panggil skill `ai slop` (stop-slop)** — bersihkan pola-pola khas tulisan AI
3. Gunakan hasil akhir untuk dimasukkan ke dokumen `.docx`

> **PENTING**: Jangan skip langkah ini. Setiap paragraf naratif HARUS melewati kedua skill.

---

## 6. Script Python — Template

Buat file: **`./scripts/generate_summary.py`**

Berikut skeleton yang harus diikuti:

```python
"""
Generate Rangkuman Kurasi Paper Findings — Certificate Autofill
Menggunakan python-docx untuk membuat file .docx

Jalankan dengan: uv run python generate_summary.py
"""

from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from datetime import datetime
import locale


def create_document():
    doc = Document()
    
    # === SETUP STYLES ===
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    
    paragraph_format = style.paragraph_format
    paragraph_format.space_after = Pt(6)
    # line_spacing = 1.15
    paragraph_format.line_spacing = 1.15
    
    # Setup heading styles
    for level in range(1, 4):
        heading_style = doc.styles[f'Heading {level}']
        heading_style.font.name = 'Calibri'
        heading_style.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
        if level == 1:
            heading_style.font.size = Pt(16)
        elif level == 2:
            heading_style.font.size = Pt(14)
        else:
            heading_style.font.size = Pt(12)
    
    # Setup margins
    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)
    
    return doc


def add_title_page(doc):
    """Halaman judul"""
    # Spacing sebelum judul
    for _ in range(6):
        doc.add_paragraph()
    
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run('Rangkuman Kurasi Literature Review')
    run.font.size = Pt(24)
    run.bold = True
    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
    
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run('Certificate Autofill System')
    run.font.size = Pt(18)
    run.font.color.rgb = RGBColor(0x44, 0x44, 0x66)
    
    doc.add_paragraph()  # spacer
    
    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = info.add_run('Dokumentasi Internal Tim')
    run.font.size = Pt(14)
    run.italic = True
    
    doc.add_paragraph()
    
    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tanggal = datetime.now().strftime('%d %B %Y')
    run = date_para.add_run(tanggal)
    run.font.size = Pt(12)
    
    source_para = doc.add_paragraph()
    source_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = source_para.add_run('Sumber: paper_findings.md (200+ papers, 57 queries, 9 groups)')
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
    
    doc.add_page_break()


def add_table(doc, headers, rows):
    """Helper: buat tabel dengan formatting"""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    
    # Header row
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(10)
    
    # Data rows
    for row_idx, row_data in enumerate(rows):
        for col_idx, cell_data in enumerate(row_data):
            cell = table.rows[row_idx + 1].cells[col_idx]
            cell.text = str(cell_data)
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(10)
    
    doc.add_paragraph()  # spacer
    return table


def build_document():
    doc = create_document()
    add_title_page(doc)
    
    # === 1. PENDAHULUAN ===
    doc.add_heading('1. Pendahuluan', level=1)
    
    # 1.1 Latar Belakang
    doc.add_heading('1.1 Latar Belakang Proyek Certificate Autofill', level=2)
    doc.add_paragraph(
        # KONTEN DIPROSES DENGAN HUMANIZER & AI SLOP
        "..."  # Tulis konten di sini
    )
    
    # ... dan seterusnya untuk semua section ...
    
    # === SIMPAN ===
    output_path = './docs/rangkuman_findings.docx'
    doc.save(output_path)
    print(f'Dokumen berhasil disimpan: {output_path}')
    return output_path


if __name__ == '__main__':
    build_document()
```

> **PENTING**: Skeleton di atas adalah TEMPLATE. Kamu harus mengisi semua konten berdasarkan:
> 1. Kurasi paper dari Section 3 dokumen ini
> 2. Abstract paper dari `paper_findings.md`
> 3. Proses setiap konten naratif dengan skill humanizer & ai slop

---

## 7. Konversi ke PDF

Setelah `.docx` selesai dibuat:

```bash
# Konversi:
soffice --headless --convert-to pdf --outdir ./docs ./docs/rangkuman_findings.docx

# Atau jika soffice tidak di PATH:
/usr/bin/soffice --headless --convert-to pdf --outdir ./docs ./docs/rangkuman_findings.docx
```

Verifikasi: file `./docs/rangkuman_findings.pdf` harus ada dan bisa dibuka.

---

## 8. Checklist Final

Sebelum selesai, verifikasi semua item berikut:

- [ ] `uv` digunakan untuk setup environment (bukan pip)
- [ ] `python-docx` terinstall via `uv add`
- [ ] Semua 9 groups (A–I) tercakup dalam rangkuman
- [ ] Setiap group memiliki 1–10 paper terkurasi yang relevan
- [ ] Paper tidak relevan sudah dibuang
- [ ] Setiap konten naratif diproses dengan skill **humanizer**
- [ ] Setiap konten naratif diproses dengan skill **ai slop (stop-slop)**
- [ ] Verdict/saran akhir (Section 3) mencakup 9 sub-section:
  - [ ] 3.1 Metode OCR & Preprocessing
  - [ ] 3.2 Metode Extraction (Core Engine)
  - [ ] 3.3 Arsitektur Pipeline
  - [ ] 3.4 Layout Understanding
  - [ ] 3.5 Confidence & Quality Assurance
  - [ ] 3.6 Deployment & Optimization
  - [ ] 3.7 Evaluation Framework
  - [ ] 3.8 Continuous Learning
  - [ ] 3.9 Kesimpulan Keseluruhan
- [ ] Daftar pustaka lengkap (hanya paper yang dikutip)
- [ ] File `.docx` berhasil dibuat di `./docs/rangkuman_findings.docx`
- [ ] File `.pdf` berhasil dikonversi di `./docs/rangkuman_findings.pdf`
- [ ] Bahasa: campuran Indonesia-Inggris (istilah teknis Inggris)
- [ ] Format dokumen: Calibri, heading hierarchy benar, tabel rapi

---

## 9. Output Files

| File | Path | Keterangan |
|------|------|-----------|
| Instruksi ini | `instruksi_generate_rangkuman.md` | Instruksi untuk coding agent |
| Script Python | `./scripts/generate_summary.py` | Script generator .docx |
| Dokumen utama | `./docs/rangkuman_findings.docx` | Master edit |
| Dokumen PDF | `./docs/rangkuman_findings.pdf` | Konversi dari .docx |
