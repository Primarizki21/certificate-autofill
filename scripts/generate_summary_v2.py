"""
Generate Rangkuman Kurasi Paper Findings V2 — Certificate Autofill
Method Catalog Edition — Pipeline Component Centric
Fokus: method catalog format, arsitektur per komponen pipeline.
Input: .pdf, .jpg, .png
Output: auto-fill ke form SKP universitas
"""

from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from datetime import datetime


def set_cell_shading(cell, color):
    shading = cell._element.get_or_add_tcPr()
    shading_elm = shading.makeelement(qn('w:shd'), {
        qn('w:fill'): color,
        qn('w:val'): 'clear'
    })
    shading.append(shading_elm)


def create_document():
    doc = Document()

    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    pf = style.paragraph_format
    pf.space_after = Pt(6)
    pf.line_spacing = 1.15

    for level in range(1, 4):
        hs = doc.styles[f'Heading {level}']
        hs.font.name = 'Calibri'
        hs.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
        if level == 1:
            hs.font.size = Pt(16)
        elif level == 2:
            hs.font.size = Pt(14)
        else:
            hs.font.size = Pt(12)

    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)

    return doc


def add_table(doc, headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ''
        p = cell.paragraphs[0]
        run = p.add_run(header)
        run.bold = True
        run.font.size = Pt(10)
        set_cell_shading(cell, 'D9D9D9')

    for row_idx, row_data in enumerate(rows):
        for col_idx, cell_data in enumerate(row_data):
            cell = table.rows[row_idx + 1].cells[col_idx]
            cell.text = ''
            p = cell.paragraphs[0]
            run = p.add_run(str(cell_data))
            run.font.size = Pt(10)

    doc.add_paragraph()
    return table


def add_mono_paragraph(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = 'Consolas'
    run.font.size = Pt(8)
    pf = p.paragraph_format
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    return p


def build_document():
    doc = create_document()

    # ======================== HALAMAN JUDUL ========================
    for _ in range(6):
        doc.add_paragraph()

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run('Literature Review — Certificate Autofill System')
    run.font.size = Pt(24)
    run.bold = True
    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run('V2 — Method Catalog Edition')
    run.font.size = Pt(18)
    run.font.color.rgb = RGBColor(0x44, 0x44, 0x66)

    sub2 = doc.add_paragraph()
    sub2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub2.add_run('Katalog Metode per Komponen Pipeline — Referensi Cepat Tim')
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x88)

    doc.add_paragraph()

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

    src_para = doc.add_paragraph()
    src_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = src_para.add_run('Sumber: paper_findings.md (363 papers, 57 queries, 9 groups, 71 paper terkurasi)')
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    doc.add_page_break()

    # ======================== 1. PENDAHULUAN ========================
    doc.add_heading('1. Pendahuluan', level=1)

    doc.add_heading('1.1 Latar Belakang Proyek', level=2)
    doc.add_paragraph(
        'Proyek Certificate Autofill bertujuan mengotomatisasi ekstraksi field dari '
        'sertifikat mahasiswa (PDF, JPG, PNG) untuk auto-fill ke form Kartu Hasil Prestasi '
        '(KHP) universitas. Sistem ini dirancang untuk menggantikan input manual yang lambat '
        'dan error-prone, di mana mahasiswa harus mengetik ulang informasi dari sertifikat '
        'ke dalam web SKP. Input dapat berupa sertifikat kegiatan apa pun yang mendukung '
        'poin SKP — lomba, seminar, organisasi, PKKMB, dan lain-lain — dengan format yang '
        'sangat bervariasi antar penyelenggara.'
    )

    doc.add_paragraph(
        'Saat ini prototype berjalan dengan pipeline PyMuPDF, Docling, dan cascade OCR '
        '(RapidOCR + Tesseract), dilanjutkan ekstraksi berbasis regex dan rule-based form '
        'mapper. Semua nilai confidence saat ini hardcoded (0.80, 0.84, 0.86, 0.92, dst.) '
        'tanpa kalibrasi statistik. Skor confidence dari RapidOCR dibuang, tidak digunakan '
        'sebagai sinyal kualitas. Tahap berikutnya adalah transisi ke production-grade '
        'pipeline ML yang tidak bergantung pada panggilan LLM, dengan biaya komputasi '
        'rendah dan inference CPU-only.'
    )

    doc.add_heading('1.2 Tujuan Dokumen', level=2)
    doc.add_paragraph(
        'Dokumen ini berfungsi sebagai method catalog — referensi cepat untuk tim tentang '
        'model, metode, dan pendekatan terbaik untuk setiap komponen pipeline Certificate '
        'Autofill. Tidak seperti literature review konvensional yang terorganisir per kelompok '
        'paper, method catalog ini terorganisir per komponen pipeline, sehingga tim dapat '
        'langsung menemukan rekomendasi untuk komponen yang sedang dikerjakan.'
    )

    doc.add_heading('1.3 Cara Membaca Dokumen', level=2)
    doc.add_paragraph(
        'Setiap komponen pipeline (Section 3) disajikan dalam format template berikut:'
    )
    bullets_template = [
        'Task: deskripsi singkat fungsi komponen',
        'Recommended: model/metode yang direkomendasikan + alasan',
        'Proof: tabel benchmark dari paper pendukung',
        'How to implement: panduan implementasi singkat',
        'Alternatives: opsi lain dengan trade-off masing-masing',
    ]
    for b in bullets_template:
        doc.add_paragraph(b, style='List Bullet')

    doc.add_paragraph(
        'Section 2 berisi executive summary dengan roadmap. Section 4-5 berisi decision '
        'matrix dan risiko. Section 6 adalah reference appendix berisi detail per kelompok '
        'paper (Group A-I) untuk pembacaan mendalam. Section 7 berisi daftar pustaka lengkap '
        'seluruh 71 paper yang dirujuk.'
    )

    doc.add_heading('1.4 Ringkasan Paper', level=2)
    add_table(doc,
        ['Group', 'Topik', 'Jumlah Paper Awal', 'Jumlah Terkurasi'],
        [
            ['A', 'LLM Document Extraction', '85', '10'],
            ['B', 'Hybrid Rule-Based + ML', '32', '5'],
            ['C', 'Confidence Calibration', '37', '8'],
            ['D', 'Document Image Preprocessing', '37', '6'],
            ['E', 'Evaluation Framework', '40', '8'],
            ['F', 'Feedback Loop & Active Learning', '23', '2'],
            ['G', 'Model Distillation & Deployment', '65', '21'],
            ['H', 'Layout-Aware Extraction', '21', '5'],
            ['I', 'Production-Scale Architecture', '23', '7'],
        ]
    )

    doc.add_page_break()

    # ======================== 2. EXECUTIVE SUMMARY ========================
    doc.add_heading('2. Executive Summary', level=1)

    doc.add_heading('2.1 Verdict', level=2)
    doc.add_paragraph(
        'Gunakan LayoutLMv3-base (125M params) sebagai core extraction engine dengan 2-tier '
        'cascade: regex untuk field pattern stabil, LayoutLM untuk field semantik. LLM hanya '
        'untuk prototyping — distilasi ke model kecil untuk production. Confidence system '
        'direformasi total dari hardcoded float menjadi Platt scaling dari logit LayoutLM '
        'dengan conformal prediction sets untuk field ambigu. Deployment CPU-only dengan '
        'ONNX INT8 quantization pada single server (8+ core, 32GB RAM) mencukupi untuk '
        'skala 25.000 mahasiswa.'
    )

    doc.add_heading('2.2 Arsitektur Pipeline', level=2)
    doc.add_paragraph(
        'Diagram alur pipeline target (text-based):'
    )
    arch_lines = [
        '                     ┌──────────────────────────────────────────────────┐',
        '                     │              INPUT: PDF / JPG / PNG              │',
        '                     └──────────────────────┬───────────────────────────┘',
        '                                            ↓',
        '                     ┌──────────────────────────────────────────────────┐',
        '                     │        1. PREPROCESSING & LAYOUT DETECTION       │',
        '                     │  ┌──────────┐  ┌────────────┐  ┌──────────────┐ │',
        '                     │  │ PyMuPDF  │  │  TADoc     │  │  RT-DETR     │ │',
        '                     │  │(page→img)│  │(dewarping) │  │(layout seg)  │ │',
        '                     │  └──────────┘  └────────────┘  └──────────────┘ │',
        '                     └──────────────────────┬───────────────────────────┘',
        '                                            ↓',
        '                     ┌──────────────────────────────────────────────────┐',
        '                     │        2. OCR (RapidOCR + Tesseract)             │',
        '                     │   (capture per-char confidence → propagate)      │',
        '                     └──────────────────────┬───────────────────────────┘',
        '                                            ↓',
        '                     ┌──────────────────────────────────────────────────┐',
        '                     │        3. 2-TIER CASCADE EXTRACTION              │',
        '                     │  ┌─────────────────────┐  ┌───────────────────┐  │',
        '                     │  │ Tier 1: Regex       │  │ Tier 2: LayoutLM  │  │',
        '                     │  │ (nomor, tgl numerik)│  │(nama, role, org)  │  │',
        '                     │  └─────────────────────┘  └───────────────────┘  │',
        '                     └──────────────────────┬───────────────────────────┘',
        '                                            ↓',
        '                     ┌──────────────────────────────────────────────────┐',
        '                     │        4. CONFIDENCE CALIBRATION                 │',
        '                     │   Platt scaling → conformal prediction sets      │',
        '                     └──────────────────────┬───────────────────────────┘',
        '                                            ↓',
        '                     ┌──────────────────────────────────────────────────┐',
        '                     │        5. FORM MAPPER (Rule-based)               │',
        '                     │      (mapping ke 12 field dropdown options)      │',
        '                     └──────────────────────┬───────────────────────────┘',
        '                                            ↓',
        '                     ┌──────────────────────────────────────────────────┐',
        '                     │          OUTPUT: Autofill ke Form KHP            │',
        '                     └──────────────────────────────────────────────────┘',
    ]
    for line in arch_lines:
        add_mono_paragraph(doc, line)

    doc.add_paragraph(
        'Estimasi total latency: 500ms-1.2s per dokumen. Cocok untuk UX real-time upload.'
    )

    doc.add_heading('2.3 Key Decision: LLM untuk Prototyping, ML untuk Production', level=2)
    doc.add_paragraph(
        'Keputusan arsitektur paling fundamental: LLM hanya digunakan pada tahap prototyping '
        'dan labeling, bukan untuk production inference. Alasan:'
    )
    bullets_decision = [
        'Biaya: fine-tuned encoder (LayoutLMv3) ~$25 per 1M requests vs LLM API $600-2700 [2602.06370] — 24-108x lebih murah',
        'Kecepatan: distilled BERT 12x faster, 101x cheaper dari GPT-4o [2501.00031]',
        'Ketergantungan: tidak perlu API call eksternal — deployment on-premise penuh',
        'Akurasi: fine-tuned small model outperforms general LLM untuk task spesifik [2509.22906]',
        'Privasi: data mahasiswa tetap di server universitas — tidak dikirim ke cloud',
        'LLM digunakan untuk prototyping: BLOCKIE Sonnet 3.5 mencapai 92.15 FUNSD F1, 98.83 CORD F1 [2505.13535] — ceiling yang dikejar model kecil',
    ]
    for b in bullets_decision:
        doc.add_paragraph(b, style='List Bullet')

    doc.add_heading('2.4 Roadmap 3 Fase', level=2)
    phase_rows = [
        ['Fase', 'Timeline', 'Deliverables', 'Justifikasi Paper'],
        ['Fase 1: Foundation', '0-2 bulan',
         'Propagate OCR confidence (capture rapidocr per-char); layout detection RT-DETR; ganti confidence hardcoded ke validation set; kumpulkan 200-500 sertifikat labeled.',
         '[2508.21693] line-level OCR, [2509.11720] layout detection, [2406.02354] uncertainty decomposition, [2504.02871] annotation guidelines'],
        ['Fase 2: ML Extraction', '2-4 bulan',
         'Fine-tune LayoutLMv3-base (LoRA CPU); 2-tier cascade (regex + LayoutLM); Platt scaling calibration; conformal prediction sets; active learning loop.',
         '[2404.10848] LayoutLMv3, [2507.01806] LoRA CPU, [2410.01609] SynJAC, [2311.12436] isotonic regression, [2401.13744] conformal prediction'],
        ['Fase 3: Optimasi', '4-6 bulan',
         'ONNX INT8 quantization; single-server deployment; evaluasi KIEval; feedback loop; progressive crystallization untuk field stabil; monitoring + retraining cycle.',
         '[2311.00502] INT4 CPU, [2505.06461] CPU vs GPU, [2607.07052] progressive crystallization, [2503.05488] KIEval'],
    ]
    add_table(doc, phase_rows[0], phase_rows[1:])
    doc.add_paragraph(
        'Catatan: Fase 1-2 bisa berjalan overlap. Layout detection dan pengumpulan dataset '
        'bisa dimulai minggu pertama. Fine-tuning dimulai setelah 200+ sample terkumpul.'
    )

    doc.add_page_break()

    # ======================== 3. METHOD CATALOG ========================
    doc.add_heading('3. Method Catalog — by Pipeline Component', level=1)

    doc.add_paragraph(
        'Setiap sub-section berikut mengikuti format: Task → Recommended → Proof → How to '
        'Implement → Alternatives. Gunakan sebagai referensi cepat saat mengimplementasi '
        'atau mengevaluasi komponen pipeline tertentu.'
    )

    # ---------- 3.1 Core Extraction (ML Approach) ----------
    doc.add_heading('3.1 Core Extraction (ML Approach)', level=2)
    doc.add_paragraph(
        'Task: Extract structured fields (nama, tanggal, role, penyelenggara, nomor '
        'sertifikat) from certificate images/PDFs.'
    )
    doc.add_paragraph(
        'Recommended: LayoutLMv3-base (125M params) with fine-tuning. Model ini '
        'menggabungkan text + layout (bounding box) + visual (page image embeddings), '
        'sehingga ideal untuk dokumen semi-terstruktur seperti sertifikat.'
    )
    doc.add_heading('Proof', level=3)
    add_table(doc,
        ['Model', 'Params', 'FUNSD F1', 'CORD F1', 'SROIE F1', 'Source'],
        [
            ['LayoutLMv3-base', '126M', '88.81', '—', '95.11', '[2304.14936]'],
            ['LayoutLMv3-base (zero-overlap)', '126M', '89.07', '—', '87.86', '[2304.14936]'],
            ['LayoutLMv3 + EM+BBO+RSF', '357M', '90.81', '98.60', '—', '[2404.10848]'],
            ['GraphLayoutLM', '—', '93.15', '97.28', '—', '[2308.07777]'],
            ['DocParser (OCR-free)', '70M', '—', '84.5', '87.3', '[2304.12484]'],
            ['ETLCH (1B, LoRA, 100 samples)', '1B', '—', '—', '—', '[2509.08381]'],
        ]
    )
    doc.add_heading('How to implement', level=3)
    doc.add_paragraph(
        'Fine-tune LayoutLMv3-base dengan LoRA pada 200-500 labeled certificates. '
        'Entity Marker (EM) + Bounding Box Ordering (BBO) techniques dari [2404.10848] '
        'meningkatkan F1 sebesar +4-8 points tanpa extra pre-training. Gunakan HuggingFace '
        'Transformers + PEFT library untuk LoRA fine-tuning. Export ke ONNX INT8 untuk '
        'CPU inference. Untuk data training, ekstrak bounding box dari PyMuPDF atau Docling, '
        'dan gunakan LLM untuk labeling awal (LLM sebagai teacher) [2501.00031].'
    )
    doc.add_heading('Alternatives', level=3)
    add_table(doc,
        ['Model', 'Keunggulan', 'Trade-off'],
        [
            ['GraphLayoutLM [2308.07777]', 'F1 93.15/97.28 — lebih tinggi', 'Butuh custom architecture, tidak semudah LayoutLM'],
            ['DocParser [2304.12484]', '70M params, OCR-free', 'Lower CORD (84.5) dan SROIE (87.3) F1'],
            ['ETLCH [2509.08381]', '1B LoRA, beats 7B dengan 100 samples', 'Butuh GPU untuk fine-tuning, masih LLM-scale'],
        ]
    )

    # ---------- 3.2 Core Extraction (LLM for Prototyping) ----------
    doc.add_heading('3.2 Core Extraction (LLM for Prototyping)', level=2)
    doc.add_paragraph(
        'Task: Rapid prototyping dan proof-of-concept sebelum ML deployment.'
    )
    doc.add_paragraph(
        'Recommended: Use LLM API for initial prototyping, distill to ML for production. '
        'Pendekatan ini memungkinkan tim menguji pipeline end-to-end dalam hari, bukan '
        'bulan, sambil mengumpulkan labeled data untuk fine-tuning model final.'
    )
    doc.add_heading('Proof', level=3)
    add_table(doc,
        ['Model', 'Params', 'FUNSD F1', 'CORD F1', 'Source'],
        [
            ['BLOCKIE Sonnet 3.5', '—', '92.15', '98.83', '[2505.13535]'],
            ['BLOCKIE Qwen 32B', '32B', '—', '96.14', '[2505.13535]'],
            ['Extract-0 (7B)', '7.66B', '—', '—', '[2509.22906]'],
            ['GoLLIE (7B)', '7B', '—', '—', '[2310.03668]'],
            ['LMDX + Gemini Pro', '—', '—', '—', '[2309.10952]'],
        ]
    )
    doc.add_heading('How to implement', level=3)
    doc.add_paragraph(
        'Gunakan BLOCKIE pattern [2505.13535]: semantik block decomposition → few-shot '
        'extraction per block — untuk rapid prototyping. Kemudian distilasi ke LayoutLMv3 '
        'menggunakan pipeline [2501.00031]: LLM labels training data → fine-tune BERT/'
        'LayoutLM. Key insight: BLOCKIE dengan Qwen 32B mencapai 96.14 F1 pada CORD '
        '[2505.13535], membuktikan bahwa model 32B bisa mendekati kualitas API model. '
        'Untuk prototyping, gunakan API; untuk production, distilasi.'
    )
    doc.add_heading('Alternatives', level=3)
    doc.add_paragraph(
        'Extract-0 [2509.22906]: model 7B specialized untuk IE — alternatif jika ingin '
        'self-host LLM. LMDX [2309.10952]: LLM + layout encoding untuk document IE. '
        'GoLLIE [2310.03668]: annotation guidelines untuk zero-shot IE.'
    )

    # ---------- 3.3 Preprocessing & OCR ----------
    doc.add_heading('3.3 Preprocessing & OCR', level=2)
    doc.add_paragraph(
        'Task: Convert input (PDF/JPG/PNG) to clean text dengan layout information.'
    )
    doc.add_paragraph(
        'Recommended: Keep existing PyMuPDF + RapidOCR + Tesseract, tambah preprocessing '
        'stages untuk dewarping dan layout detection.'
    )
    doc.add_heading('Proof', level=3)
    add_table(doc,
        ['Method', 'Result', 'Params', 'Source'],
        [
            ['PreP-OCR (ResShift+ByT5)', '63.9-70.3% CER reduction', '—', '[2505.20429]'],
            ['TADoc (dewarping)', 'CER 0.172 (DIR300)', '7.9M', '[2508.06988]'],
            ['Polar-Doc (dewarping)', 'CER 0.246 (DocUNet)', '9.6M', '[2312.07925]'],
            ['Line-level OCR (Kraken+PARSeq)', 'CRR 85.76, 4x faster', '—', '[2508.21693]'],
        ]
    )
    doc.add_heading('How to implement', level=3)
    steps_ocr = [
        'PDF to image conversion (PyMuPDF) — existing',
        'Optional dewarping (TADoc 7.9M) — hanya jika distortion terdeteksi',
        'Layout detection (RT-DETR) — segment header/body/signature regions',
        'OCR (RapidOCR + Tesseract) — existing, tapi capture per-char confidence',
    ]
    for s in steps_ocr:
        doc.add_paragraph(s, style='List Bullet')
    doc.add_heading('Alternatives', level=3)
    add_table(doc,
        ['Alternatif', 'Trade-off'],
        [
            ['Donut [2403.07553] — OCR-free, 200M params', 'Alternatif jika OCR quality rendah — tidak perlu OCR pipeline sama sekali'],
            ['DocParser [2304.12484] — OCR-free encoder-decoder, 70M', 'Lebih ringan dari Donut, tapi akurasi lebih rendah'],
        ]
    )

    # ---------- 3.4 Layout Detection ----------
    doc.add_heading('3.4 Layout Detection', level=2)
    doc.add_paragraph(
        'Task: Identify dan segment document regions (header, body, signature, stamp).'
    )
    doc.add_paragraph(
        'Recommended: RT-DETR via Docling (heron-101 atau egret-m).'
    )
    doc.add_heading('Proof', level=3)
    add_table(doc,
        ['Model', 'mAP', 'Params', 'Latency A100', 'Latency CPU', 'Source'],
        [
            ['RT-DETR heron-101', '78% (DocLayNet)', '76.7M', '28ms', '988ms', '[2509.11720]'],
            ['RT-DETR egret-m', '68.6%', '19.5M', '24ms', '334ms', '[2509.11720]'],
            ['SelfDocSeg (unsupervised)', '74.3 (DocLayNet)', '—', '—', '—', '[2305.00795]'],
        ]
    )
    doc.add_heading('How to implement', level=3)
    doc.add_paragraph(
        'Gunakan Docling built-in layout detection. egret-m (19.5M, 334ms CPU) cukup '
        'untuk certificate layouts. heron-101 (76.7M, 988ms CPU) untuk akurasi lebih '
        'tinggi. Integrasi sudah existing via Docling di pipeline.'
    )
    doc.add_heading('Alternatives', level=3)
    doc.add_paragraph(
        'UnSupDLA [2406.06236]: unsupervised layout analysis tanpa labeled data — '
        'cocok jika tidak punya annotation untuk layout regions.'
    )

    # ---------- 3.5 Confidence Calibration ----------
    doc.add_heading('3.5 Confidence Calibration', level=2)
    doc.add_paragraph(
        'Task: Replace hardcoded confidence (0.80, 0.84, 0.92) dengan statistik '
        'calibrated scores.'
    )
    doc.add_paragraph(
        'Recommended: Platt scaling pada LayoutLM logits + conformal prediction sets.'
    )
    doc.add_heading('Proof', level=3)
    add_table(doc,
        ['Method', 'Result', 'Source'],
        [
            ['Isotonic regression', 'Zero calibration error (preserves ROC convex hull)', '[2311.12436]'],
            ['Conformal prediction sets', '+0.4-0.7 Cohen\'s d, 92-99% adoption rate', '[2401.13744]'],
            ['Verbalized confidence', 'ECE ~0.05 (GPT-4 best prompt)', '[2305.14975]'],
            ['QA-Calibration', 'ECE 0.149-0.182 (MMLU, Mistral/Gemma)', '[2410.06615]'],
        ]
    )
    doc.add_heading('How to implement', level=3)
    steps_cal = [
        'Extract logits dari LayoutLMv3 output layer',
        'Fit Platt scaling pada validation set (200+ labeled samples)',
        'Untuk needs_review flags: gunakan conformal prediction → candidate set (2-3 values)',
        'Threshold dari precision-recall curve, BUKAN hardcoded 0.80',
    ]
    for s in steps_cal:
        doc.add_paragraph(s, style='List Bullet')
    doc.add_heading('Warning', level=3)
    doc.add_paragraph(
        'SROIE memiliki 75% template leakage — validation set harus zero overlap dengan '
        'training templates [2304.14936]. Kalibrasi yang baik membutuhkan validation set '
        'yang representatif.'
    )

    # ---------- 3.6 Form Mapping ----------
    doc.add_heading('3.6 Form Mapping', level=2)
    doc.add_paragraph(
        'Task: Map extracted fields ke form dropdown options (role, tingkat, penyelenggara).'
    )
    doc.add_paragraph(
        'Recommended: Rule-based (keep existing) dengan ML fallback untuk edge cases.'
    )
    doc.add_heading('Why rule-based', level=3)
    bullets_rule = [
        'Existing rules sudah sophisticated (signature context, Airlangga detection, cross-field coupling)',
        'Debuggable dan maintainable — ketika mapping salah, bisa dilacak ke aturan spesifik',
        'ML untuk 12 fields x 6-9 dropdown options butuh dataset besar yang belum tersedia',
    ]
    for b in bullets_rule:
        doc.add_paragraph(b, style='List Bullet')
    doc.add_heading('When to add ML', level=3)
    doc.add_paragraph(
        'Jika akurasi field tertentu <85% setelah LayoutLM extraction, tambah classifier '
        'untuk field itu saja. Jika LLM digunakan untuk prototyping, BLOCKIE mencapai '
        '98.83 CORD F1 [2505.13535] yang mencakup sequence labeling mirip form mapping.'
    )

    # ---------- 3.7 Evaluation Framework ----------
    doc.add_heading('3.7 Evaluation Framework', level=2)
    doc.add_paragraph(
        'Task: Measure extraction quality per field dengan meaningful metrics.'
    )
    doc.add_paragraph(
        'Recommended: KIEval metric + per-field F1.'
    )
    doc.add_heading('Proof', level=3)
    add_table(doc,
        ['Model', 'Dataset', 'Entity F1', 'Group F1', 'Aligned', 'Source'],
        [
            ['LayoutXLM', 'SROIE', '91.77', '—', '90.32', '[2503.05488]'],
            ['LayoutLMv3', 'SROIE', '91.87', '—', '91.15', '[2503.05488]'],
            ['LayoutLMv3', 'CORD', '95.13', '82.11', '88.15', '[2503.05488]'],
            ['LayoutLMv3', 'FUNSD', '85.87', '—', '80.22', '[2503.05488]'],
            ['Donut', 'CORD', '84.93', '68.26', '79.70', '[2503.05488]'],
        ]
    )
    doc.add_paragraph(
        'Key insight: Group-level F1 (82.11 untuk CORD) lebih rendah dari Entity F1 '
        '(95.13) — artinya field individu terekstrak baik tapi asosiasi antar field '
        'terkadang salah. Untuk certificate autofill, correct field association (mana '
        'nama yang cocok dengan tanggal mana) lebih penting dari akurasi field individu.'
    )
    doc.add_heading('How to implement', level=3)
    steps_eval = [
        'Per-field F1 sebagai primary metric (weighted by field importance)',
        'KIEval untuk end-to-end evaluation (entity + group + correction cost)',
        '100-200 labeled certificates sebagai test set',
        'WARNING: SROIE test set 75% template overlap → F1 inflated ~10.5 points [2304.14936]. Always evaluate on zero-overlap split.',
    ]
    for s in steps_eval:
        doc.add_paragraph(s, style='List Bullet')

    # ---------- 3.8 Deployment ----------
    doc.add_heading('3.8 Deployment (CPU-Only, On-Premise)', level=2)
    doc.add_paragraph(
        'Task: Run full pipeline on CPU tanpa GPU atau LLM API.'
    )
    doc.add_paragraph(
        'Recommended: LayoutLMv3-base ONNX INT8, single CPU server.'
    )
    doc.add_heading('Proof', level=3)
    add_table(doc,
        ['Finding', 'Result', 'Source'],
        [
            ['INT4 quantization accuracy loss', '<1% from FP32', '[2311.00502]'],
            ['CPU outperform GPU (sub-1B)', 'Yes at F16/Q4', '[2505.06461]'],
            ['LoRA CPU: bridges gap to GPU', '>50% of gap closed', '[2507.01806]'],
            ['Fine-tuned encoder vs LLM cost', '~$25 vs ~$600-2700 per 1M requests', '[2602.06370]'],
            ['Distilled BERT speed/cost', '12x faster, 101x cheaper than GPT-4o', '[2501.00031]'],
        ]
    )
    doc.add_heading('How to implement', level=3)
    steps_deploy = [
        'Export LayoutLMv3 ke ONNX',
        'Quantize ke INT8 via ONNX Runtime',
        'Single CPU server (8+ core, 32GB RAM)',
        '4 worker parallel → ~8-16 docs/second throughput',
        'Untuk 250k total certificates: ~9-18 hours total CPU time',
    ]
    for s in steps_deploy:
        doc.add_paragraph(s, style='List Bullet')

    # ---------- 3.9 Continuous Improvement ----------
    doc.add_heading('3.9 Continuous Improvement', level=2)
    doc.add_paragraph(
        'Task: Keep the model improving tanpa manual intervention.'
    )
    doc.add_paragraph(
        'Recommended: Active learning + weak supervision + feedback loop.'
    )
    doc.add_heading('How to implement', level=3)
    steps_ci = [
        'Active learning [2302.08893]: sample certificates dengan confidence 0.4-0.8 untuk review',
        'Weak supervision: regex output dengan confidence >0.90 → pseudo-label untuk LayoutLM training [2305.00795]',
        'Human-in-the-loop [2308.04332]: user corrections → filter noise → save sebagai training data',
        'Retraining cycle: fine-tune setiap 1-2 bulan dengan LoRA CPU [2507.01806]',
        'Progressive crystallization [2607.07052]: jika ML accuracy >95%, crystallize ke deterministic rules',
    ]
    for s in steps_ci:
        doc.add_paragraph(s, style='List Bullet')

    # ---------- 3.10 Data & Annotation ----------
    doc.add_heading('3.10 Data & Annotation', level=2)
    doc.add_paragraph(
        'Task: Generate labeled training data efficiently.'
    )
    doc.add_paragraph(
        'Recommended: LLM-synthesized guidelines + synthetic certificate generation.'
    )
    doc.add_heading('Proof', level=3)
    add_table(doc,
        ['Method', 'Result', 'Source'],
        [
            ['Synthesized guidelines (NER F1 boost)', '+25.86% (i2b2 EVENT)', '[2504.02871]'],
            ['SynJAC (synthetic domain adaptation)', '92.62 printed, 89.11 handwritten', '[2410.01609]'],
            ['PAE (PDF attribute extraction)', '92.5% F1 avg, 12 datasets', '[2405.17533]'],
        ]
    )
    doc.add_heading('How to implement', level=3)
    steps_data = [
        'Gunakan LLM (GPT-4) untuk generate annotation guidelines dari certificate samples [2504.02871]',
        'Gunakan SynJAC pattern [2410.01609] untuk generate synthetic certificate layouts',
        'Mulai dengan 200-500 labeled certificates untuk initial fine-tuning',
        'Expand via active learning seiring sistem berjalan',
    ]
    for s in steps_data:
        doc.add_paragraph(s, style='List Bullet')

    doc.add_page_break()

    # ======================== 4. DECISION MATRIX ========================
    doc.add_heading('4. Decision Matrix', level=1)
    doc.add_paragraph(
        'Tabel berikut merangkum pilihan untuk setiap komponen pipeline, dari kondisi saat '
        'ini (prototype) menuju target (full ML), diperkaya dengan referensi paper spesifik.'
    )

    matrix_rows = [
        ['Komponen', 'Sekarang (Prototype)', 'Interim (3-6 bulan)', 'Target (Full ML)', 'Referensi'],
        ['OCR & Preprocessing', 'PyMuPDF + RapidOCR + Tesseract, OCR confidence dibuang',
         '+ dewarping TADoc + layout detection RT-DETR + OCR confidence propagation',
         '+ Line-level OCR [2508.21693] + PreP-OCR restoration [2505.20429] + Donut fallback [2403.07553]',
         '[2508.06988] [2509.11720] [2505.20429]'],
        ['Core Extraction', 'Regex only (field_extractor.py)',
         'Regex + LayoutLMv3-base cascade (train 200-500 samples via LoRA CPU)',
         'LayoutLMv3-base fully replaces regex + GraphLayoutLM jika perlu F1 >93',
         '[2404.10848] [2507.01806] [2308.07777]'],
        ['Confidence', 'Hardcoded float (0.80, 0.84, dll)',
         'Platt scaling pada LayoutLM logit + OCR confidence propagation + isotonic regression',
         '+ Conformal prediction sets [2401.13744] + uncertainty decomposition [2406.02354]',
         '[2311.12436] [2401.13744] [2406.02354]'],
        ['Form Mapper', 'Rule-based (form_mapper.py)',
         'Tetap rule-based + evaluasi akurasi per field + threshold dari PR curve',
         '+ ML classifier untuk field bermasalah jika perlu (field-specific)',
         '[2505.13535]'],
        ['Deployment', 'Background tasks / DB worker',
         'ONNX INT8 + queue worker + single CPU server (8+ core, 32GB)',
         '+ Auto-scale container + monitoring + serverless untuk peak [2502.12017]',
         '[2311.00502] [2505.06461] [2502.12017]'],
        ['Data & Annotation', 'Manual labeling (belum ada sistem)',
         'LLM-synthesized guidelines + 200-500 samples labeled',
         'Synthetic cert generation [2410.01609] + active learning loop [2302.08893] + weak supervision',
         '[2504.02871] [2410.01609] [2302.08893]'],
        ['Continuous Improvement', 'Belum ada feedback loop',
         'Capture user corrections sebagai candidate training samples',
         'Active learning + weak supervision + progressive crystallization [2607.07052] + retraining cycle',
         '[2308.04332] [2607.07052] [2302.08893]'],
    ]
    add_table(doc, matrix_rows[0], matrix_rows[1:])

    doc.add_page_break()

    # ======================== 5. RISK & LIMITATIONS ========================
    doc.add_heading('5. Risk & Limitations', level=1)

    doc.add_heading('5.1 Benchmark Inflation', level=2)
    doc.add_paragraph(
        'SROIE dataset memiliki 75% template overlap antara training dan test set. '
        'Akibatnya, F1 yang dilaporkan (95.11 untuk LayoutLMv3) bisa turun ~10.5 points '
        'saat dievaluasi pada zero-overlap split [2304.14936]. Hal yang sama berlaku '
        'untuk FUNSD (16% overlap, dampak lebih kecil). Implikasi: semua benchmark '
        'dari public dataset harus diinterpretasikan dengan hati-hati — performa di '
        'sertifikat nyata mungkin lebih rendah dari angka publikasi.'
    )

    doc.add_heading('5.2 Error Cascading', level=2)
    doc.add_paragraph(
        'Kesalahan di preprocessing merambat ke semua tahap berikutnya: layout error → '
        'OCR error → extraction error. Sebagai contoh, jika dewarping gagal (CER 0.172 '
        'untuk TADoc [2508.06988]), maka OCR akan menghasilkan teks yang salah, yang '
        'pada gilirannya membuat LayoutLM tidak bisa mengekstrak field dengan benar. '
        'Mitigasi: gunakan confidence propagation di setiap tahap, dan hentikan pipeline '
        'lebih awal jika confidence preprocessing terlalu rendah.'
    )

    doc.add_heading('5.3 Template Overfitting', level=2)
    doc.add_paragraph(
        'Model cenderung overfit ke template sertifikat yang terlihat di training. Jika '
        'hanya dilatih pada sertifikat dari 5 institusi, model akan gagal pada sertifikat '
        'dari institusi ke-6 dengan layout yang sangat berbeda. Mitigasi: gunakan beragam '
        'sumber training data, augmentasi layout (synthetic data [2410.01609]), dan '
        'pertahankan regex sebagai fallback untuk field dengan pattern stabil.'
    )

    doc.add_heading('5.4 FUNSD Overlap', level=2)
    doc.add_paragraph(
        'FUNSD memiliki 16% overlap — lebih kecil dari SROIE, tapi tetap berdampak pada '
        'reliabilitas benchmark. Untuk multimodal models seperti LayoutLMv3, dampaknya '
        'minimal karena visual features memberikan sinyal tambahan [2304.14936].'
    )

    doc.add_page_break()

    # ======================== 6. DETAIL PER GROUP A-I ========================
    doc.add_heading('6. Detail per Group A-I (Reference Appendix)', level=1)
    doc.add_paragraph(
        'Section ini menyediakan detail mendalam per kelompok paper, setara dengan '
        'literature review konvensional. Gunakan sebagai referensi saat perlu memahami '
        'konteks penuh di balik rekomendasi method catalog.'
    )

    # ---- 6.1 Group A: LLM Document Extraction ----
    doc.add_heading('6.1 Group A — LLM untuk Document Field Extraction', level=2)
    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Group A mengeksplorasi kemampuan LLM dalam information extraction dari dokumen. '
        'Untuk sertifikat mahasiswa, pendekatan LLM sangat efektif untuk zero-shot extraction '
        'pada format yang belum pernah dilihat. Namun, target akhir proyek ini adalah full ML '
        'tanpa LLM di production — sehingga temuan Group A digunakan sebagai guidance untuk '
        'distilasi dan benchmark ceiling yang ingin dicapai model kecil.'
    )
    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2305.03253] VicunaNER', 'Zero/few-shot NER pakai Vicuna — framework bisa didistilasi ke student model'],
            ['[2308.09341] Document Automation Survey', 'Survey arsitektur DA pasca-LLM: cascade rule/ML/LLM adalah arsitektur dominan'],
            ['[2309.10952] LMDX', 'LLM untuk document IE dengan layout encoding — bukti LLM mampu extraction dari VRD'],
            ['[2509.22906] Extract-0', 'Model 7B khusus IE, LoRA + GRPO — model kecil specialized bisa outperform general LLM besar'],
            ['[2402.10612] Rowen: Adaptive RAG', 'RAG untuk mitigasi halusinasi — berguna saat prototyping pakai LLM'],
            ['[2403.13369] Clinical IE for Low-Resource', 'Few-shot learning untuk IE di resource-scarce setting — relevan untuk data terbatas'],
            ['[2502.11306] Smoothed Knowledge Distillation', 'Distilasi dari teacher LLM ke student kecil mengurangi halusinasi'],
            ['[2505.13535] IE from VRDs using LLM', 'BLOCKIE: semantic block decomposition — 98.83 CORD F1 dengan Sonnet 3.5'],
            ['[2508.14314] Zero-knowledge LLM Hallucination Detection', 'Cross-model consistency untuk deteksi halusinasi — relevant untuk quality assurance'],
            ['[2509.08381] Low-Resource Fine-Tuning (1B)', 'Model 1B efektif untuk structured IE — bukti small model cukup dengan LoRA'],
        ]
    )
    doc.add_heading('Temuan Utama', level=3)
    bullets_a = [
        'LLM sangat efektif untuk zero-shot extraction tapi tidak efisien untuk production. [2509.22906]: Extract-0 (7B) outperform general LLM — spesialisasi > scale.',
        'Distilasi LLM → student model (BERT-scale) pertahankan 90%+ akurasi dengan ukuran 1000x lebih kecil [2501.00031].',
        'Cascade architecture (rule → small model → LLM fallback) adalah best practice industri [2308.09341].',
        'BLOCKIE [2505.13535] buktikan 32B model bisa capai 96.14 CORD F1 — ceiling untuk model kecil.',
    ]
    for b in bullets_a:
        doc.add_paragraph(b, style='List Bullet')
    doc.add_heading('Relevansi', level=3)
    doc.add_paragraph(
        'LLM bukan target deployment, melainkan teacher untuk distilasi. Model 7B specialized '
        '[2509.22906] dan 1B fine-tuned [2509.08381] adalah ceiling yang ingin dicapai oleh '
        'LayoutLMv3-base (125M) setelah distilasi dan fine-tuning.'
    )

    # ---- 6.2 Group B: Hybrid Rule-Based + ML ----
    doc.add_heading('6.2 Group B — Hybrid Rule-Based + ML', level=2)
    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Group B membahas hybrid architecture — kapan pakai rule-based, kapan pakai ML, dan '
        'bagaimana mengkombinasikannya. Pipeline existing sudah mengadopsi pola ini secara '
        'natural (regex fast path → LayoutLM pre-training → OCR fallback). Target adalah '
        'memperkuat tier ML dengan fine-tuned LayoutLMv3 untuk mengganti pure regex, sambil '
        'tetap mempertahankan rule-based form mapper yang sudah teruji.'
    )
    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2308.07777] GraphLayoutLM', 'Layout structure graph untuk document understanding — alternatif untuk relasi antar field, F1 93.15/97.28'],
            ['[2306.00526] Layout-Aware Prompt for DocVQA', 'Prompting dengan layout information untuk zero-shot document QA'],
            ['[2404.05225] LayoutLLM', 'Layout instruction tuning untuk LLM — layout information vital untuk precise document understanding'],
            ['[2509.08381] Low-Resource Fine-Tuning (1B)', 'Model 1B efektif untuk multi-task structured IE — fine-tuning ke 12 field spesifik sertifikat'],
            ['[2512.13031] Comprehensive Eval: Rule vs ML vs DL', 'Perbandingan sistematis 3 pendekatan: rule untuk pattern stabil, ML untuk semi-struktur, DL untuk tidak terstruktur'],
        ]
    )
    doc.add_heading('Temuan Utama', level=3)
    bullets_b = [
        'Rule-based unggul untuk field dengan pattern stabil [2512.13031]: nomor sertifikat, format tanggal standar.',
        'Layout information (posisi, bounding box) memberi signal sangat kuat untuk IE [2404.05225][2308.07777].',
        'Cascade architecture (rule-tier untuk field mudah, ML-tier untuk field sulit) adalah pendekatan paling cost-effective [2308.09341].',
    ]
    for b in bullets_b:
        doc.add_paragraph(b, style='List Bullet')
    doc.add_heading('Relevansi', level=3)
    doc.add_paragraph(
        'Pipeline target menggunakan 2-tier cascade: Tier 1 regex untuk field pattern stabil, '
        'Tier 2 LayoutLMv3-base untuk field semantik. Rule-based form mapper dipertahankan '
        'karena sudah teruji, debuggable, dan maintainable.'
    )

    # ---- 6.3 Group C: Confidence Calibration ----
    doc.add_heading('6.3 Group C — Confidence Calibration', level=2)
    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Salah satu kelemahan terbesar pipeline existing adalah confidence yang hardcoded — '
        'setiap regex match mendapat skor tetap (0.84 untuk organizer, 0.92 untuk role) tanpa '
        'mempertimbangkan kualitas match sebenarnya. Group C mencari metode kalibrasi confidence '
        'yang rigorous dan applicable ke model non-LLM.'
    )
    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2311.12436] ROC-Regularized Isotonic Regression', 'Teknik isotonic regression untuk kalibrasi classifier — applicable untuk LayoutLM output'],
            ['[2401.13744] Conformal Prediction Sets', 'Hasilkan candidate set saat confidence rendah — ideal untuk human-in-the-loop verification, +0.4-0.7 Cohen\'s d'],
            ['[2406.02354] Label-wise Aleatoric & Epistemic', 'Dekomposisi uncertainty per-field: noise OCR (aleatoric) vs model uncertainty (epistemic)'],
            ['[2410.01609] SynJAC', 'Kalibrasi scanned document KIE dengan synthetic data — paling relevan untuk sertifikat scan'],
            ['[2604.09529] VL-Calibration', 'Decoupled confidence calibration untuk VLM — komponen reasoning dan persepsi dikalibrasi terpisah'],
            ['[2305.14975] Just Ask for Calibration', 'Strategi eliciting calibrated confidence dari RLHF LLM — insight transferable ke fine-tuned model'],
            ['[2410.06615] QA-Calibration', 'Kalibrasi confidence untuk QA/extraction — ECE 0.149-0.182 pada MMLU'],
            ['[2412.14737] Verbalized Confidence for LLMs', 'Analisis confidence score yang di-verbalize — cocok untuk confidence dari JSON output'],
        ]
    )
    doc.add_heading('Temuan Utama', level=3)
    bullets_c = [
        'Confidence dari model encoder dikalibrasi dengan Platt scaling atau isotonic regression [2311.12436].',
        'Per-field uncertainty decomposition [2406.02354] bedakan noise OCR (aleatoric) vs model tidak familiar (epistemic).',
        'Conformal prediction [2401.13744]: "dengan 90% confidence, nilai benar ada dalam candidate set 2-3 opsi."',
        'SynJAC [2410.01609] menggunakan synthetic data untuk joint adaptation + kalibrasi KIE.',
    ]
    for b in bullets_c:
        doc.add_paragraph(b, style='List Bullet')
    doc.add_heading('Relevansi', level=3)
    doc.add_paragraph(
        'Ganti confidence hardcoded dengan Platt scaling pada logit LayoutLMv3. Conformal '
        'prediction [2401.13744] untuk field dengan banyak kandidat. Propagate OCR confidence '
        'per-karakter dari RapidOCR sebagai input feature ke model. Threshold dari precision-'
        'recall curve, bukan angka 0.80 asal.'
    )

    # ---- 6.4 Group D: Document Image Preprocessing ----
    doc.add_heading('6.4 Group D — Document Image Preprocessing', level=2)
    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Input sertifikat bisa berupa PDF (digital atau scan) atau foto dari smartphone. '
        'Kualitas gambar sangat bervariasi. Preprocessing yang baik adalah fondasi pipeline '
        '— tanpa OCR yang bersih, model ekstraksi sebaik apa pun akan gagal karena inputnya '
        'sudah rusak.'
    )
    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2505.20429] PreP-OCR', 'Pipeline restorasi + post-OCR correction, 63.9-70.3% CER reduction pada historical documents'],
            ['[2307.12571] MataDoc', 'Margin and text aware document dewarping untuk arbitrary boundary — sertifikat sering difoto tidak sempurna'],
            ['[2312.07925] Polar-Doc', 'One-stage dewarping dengan polar coordinate — CER 0.246 (DocUNet), 9.6M params, lebih efisien'],
            ['[2508.06988] TADoc', 'Time-aware document dewarping — CER 0.172 (DIR300), 7.9M params, untuk foto device'],
            ['[2508.14557] Internal Document Redundancy', 'Memanfaatkan redundansi internal dokumen untuk OCR lebih baik — unsupervised'],
            ['[2508.21693] Line-Level OCR', 'Line-level OCR lebih robust untuk certificate dibanding word-level — CRR 85.76, 4x faster'],
        ]
    )
    doc.add_heading('Temuan Utama', level=3)
    bullets_d = [
        'Dewarping penting untuk sertifikat hasil foto HP [2508.06988][2307.12571][2312.07925].',
        'Line-level OCR [2508.21693] memberikan akurasi lebih baik untuk teks rapat seperti di sertifikat.',
        'PreP-OCR [2505.20429]: integrasi image restoration + post-OCR correction, turunkan CER 63.9-70.3%.',
    ]
    for b in bullets_d:
        doc.add_paragraph(b, style='List Bullet')
    doc.add_heading('Relevansi', level=3)
    doc.add_paragraph(
        'Pertahankan PyMuPDF + RapidOCR + Tesseract baseline. Tambah dewarping opsional '
        '(deteksi distorsi dulu). Layout detection (RT-DETR) untuk segmentasi region. '
        'Capture OCR confidence per-karakter sebagai input feature.'
    )

    # ---- 6.5 Group E: Evaluation Framework ----
    doc.add_heading('6.5 Group E — Evaluation Framework', level=2)
    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Untuk mengevaluasi pipeline extraction, metrik yang tepat harus dipilih. '
        'Accuracy end-to-end saja tidak cukup — setiap field punya karakteristik berbeda. '
        'Group E mengkaji metrik evaluasi untuk document KIE beserta metodologi quality control.'
    )
    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2310.03668] GoLLIE', 'Annotation guidelines meningkatkan zero-shot IE — penting untuk quality control labeling'],
            ['[2502.16377] Instruction-Tuning for Event Extraction', 'Effect annotation guidelines saat instruction-tuning LLM — cross-schema generalization improves'],
            ['[2503.05488] KIEval', 'Metrik evaluasi khusus Document KIE — Entity F1 95.13 vs Group F1 82.11 untuk CORD'],
            ['[2504.02871] Synthesized Annotation Guidelines', 'Auto-generated guidelines untuk IE annotation — +25.86% F1 boost, mengurangi effort manual'],
            ['[2505.17125] NEXT-EVAL', 'Framework evaluasi rule-based vs LLM extraction — applicable untuk perbandingan sebelum/sesudah ML'],
            ['[2510.12835] Repurposing Annotation Guidelines', 'Guidelines repurposing untuk LLM annotators — scalable annotation pipeline'],
            ['[2404.01462] OpenChemIE', 'Contoh evaluation framework multi-modal IE (text, tabel, gambar) — arsitektur adaptable'],
            ['[2404.19329] End-to-end IE in Handwritten Docs', 'Contoh evaluasi end-to-end IE di real documents — metodologi transferable'],
        ]
    )
    doc.add_heading('Temuan Utama', level=3)
    bullets_e = [
        'KIEval [2503.05488]: per-field F1 sebagai metrik primer, Group F1 penting untuk evaluasi asosiasi field.',
        'End-to-end accuracy bisa misleading [2304.14936]. Field-level evaluation lebih akurat.',
        'Annotation guidelines [2310.03668][2504.02871] meningkatkan konsistensi labeling.',
        'Group F1 (82.11) < Entity F1 (95.13) — field association problem perlu perhatian khusus.',
    ]
    for b in bullets_e:
        doc.add_paragraph(b, style='List Bullet')
    doc.add_heading('Relevansi', level=3)
    doc.add_paragraph(
        'Gunakan per-field F1 sebagai metrik primer, weighted by importance. Kumpulkan 100-200 '
        'sertifikat labeled test set. Gunakan KIEval [2503.05488] untuk evaluasi aplikasi-centric.'
    )

    # ---- 6.6 Group F: Feedback Loop & Active Learning ----
    doc.add_heading('6.6 Group F — Feedback Loop & Active Learning', level=2)
    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Sertifikat mahasiswa sangat beragam — setiap penyelenggara punya format sendiri. '
        'Group F membahas bagaimana sistem bisa terus belajar dari koreksi user dan memilih '
        'sertifikat mana yang paling informatif untuk dilabeli.'
    )
    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2308.04332] RLHF-Blender', 'Framework human-in-the-loop untuk ML systems — bisa diadaptasi untuk koreksi user di form'],
            ['[2302.08893] Active Learning for Data Streams', 'Survey comprehensive AL — strategi memilih sample informatif untuk labeling dari data stream'],
        ]
    )
    doc.add_heading('Temuan Utama', level=3)
    bullets_f = [
        'Active learning [2302.08893]: pilih certificate dengan confidence rendah atau out-of-distribution — minimalkan effort labeling.',
        'Koreksi user di form bisa jadi feedback signal [2308.04332]. Bedakan noise vs signal.',
        'Weak supervision [2305.00795]: output rule-based dengan confidence tinggi jadi pseudo-label.',
    ]
    for b in bullets_f:
        doc.add_paragraph(b, style='List Bullet')
    doc.add_heading('Relevansi', level=3)
    doc.add_paragraph(
        'Implementasi feedback loop: setiap koreksi user → candidate training sample. '
        'Active learning: sample dengan confidence 0.4-0.8 diprioritaskan review. '
        'Weak supervision: regex output dengan confidence >0.90 jadi pseudo-label.'
    )

    # ---- 6.7 Group G: Model Distillation & Efficient Deployment ----
    doc.add_heading('6.7 Group G — Model Distillation & Efficient Deployment', level=2)
    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Constraint utama: CPU-only inference, tanpa GPU, tanpa API call ke LLM. Model '
        'harus ringan (maks 500M params), bisa di-quantize (INT8/INT4), dan inference di '
        'bawah 1 detik per dokumen. Group G membahas distilasi, quantization, dan cost analysis.'
    )
    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2305.14450] Empirical Study IE with LLMs', 'Benchmark komprehensif GPT family untuk IE — LLM bagus zero-shot tapi fine-tuned menang task spesifik'],
            ['[2311.00502] Efficient LLM Inference on CPUs', 'INT4 quantization untuk CPU inference — accurate loss <1% dari FP32'],
            ['[2311.08883] Distilling Rule-based into LLMs', 'Rule-based knowledge distillation — bidirectional: dari LLM ke rule-based juga mungkin'],
            ['[2402.10517] Any-Precision LLM', 'Low-cost deployment multiple LLM sizes — overlay quantization untuk efisiensi memori'],
            ['[2405.12311] SpotKube', 'Cost-optimal microservices deployment — framework untuk auto-scaling deployment'],
            ['[2405.17533] PAE: Product Attribute Extraction', 'LLM-based attribute extraction e-commerce — transferable ke certificate field extraction'],
            ['[2406.05348] Toward Reliable Scientific IE', 'Manual error analysis method untuk reliability assessment IE — praktik validasi hasil ekstraksi'],
            ['[2411.16313] CATP-LLM', 'Cost-aware tool planning LLM — framework optimasi biaya/fungsi untuk tool selection'],
            ['[2412.18934] Dovetail', 'CPU/GPU heterogeneous speculative decoding — inference hybrid, CPU untuk verifikasi paralel'],
            ['[2501.00031] Distilling LLMs for Clinical IE', 'Distilasi LLM ke BERT (1000x lebih kecil) — pertahankan 90%+ akurasi NER dengan ukuran 0.1%'],
            ['[2502.12017] Serverless ML Inference', 'Serverless untuk batch ML inference — auto-scale untuk peak handling'],
            ['[2504.13359] Cost-of-Pass', 'Framework ekonomi cost-effectiveness LLM — structured tasks fine-tuned encoder lebih murah'],
            ['[2505.06461] CPUs Outperform GPUs', 'CPU dapat outperform GPU untuk LLM inference sub-1B di F16/Q4 — validasi CPU-only'],
            ['[2507.01806] LoRA Fine-Tuning Without GPUs', 'Fine-tuning LoRA di CPU laptop — bisa adaptasi LayoutLMv3 tanpa GPU mahal'],
            ['[2509.18101] Cost-Benefit On-Premise vs Commercial', 'Analisis biaya on-premise vs API LLM — compelling case untuk full ML on-premise'],
            ['[2601.22362] Quantization & Batching', 'Trade-off presisi, batching, energy efficiency — referensi optimasi deployment'],
            ['[2602.06370] Cost-Aware Model Selection', 'Multi-objective trade-off fine-tuned encoder vs LLM prompting — small model menang structured tasks'],
            ['[2607.07052] Progressive Crystallization', 'Transisi LLM agent → deterministic rules — framework sistematis, mulai rule → ML → deterministik'],
            ['[2302.14017] Full Stack Optimization Survey', 'Survey optimasi inference dari hardware ke software — komprehensif untuk deployment planning'],
            ['[2403.02310] Sarathi-Serve', 'Optimasi serving LLM — chunked-prefill, teknik adaptasi untuk batch LayoutLM inference'],
            ['[2412.04504] Multi-Bin Batching', 'Strategi batching untuk LLM inference — akomodasi variasi panjang input sertifikat'],
        ]
    )
    doc.add_heading('Temuan Utama', level=3)
    bullets_g = [
        'Distilasi LLM → BERT [2501.00031]: 1000x lebih kecil, 90%+ akurasi NER. LayoutLMv3-base ONNX INT8 inference 200-500ms.',
        'CPU inference INT4 [2311.00502] feasible untuk transformer. LayoutLMv3-base INT8 di CPU modern.',
        'Cost analysis [2509.18101][2602.06370]: fine-tuned encoder 24-108x lebih murah dari LLM untuk structured tasks.',
        'Progressive crystallization [2607.07052]: roadmap sistematis dari rule → ML → deterministik.',
        'LoRA fine-tuning tanpa GPU [2507.01806] — fine-tuning LayoutLMv3 di CPU.',
    ]
    for b in bullets_g:
        doc.add_paragraph(b, style='List Bullet')
    doc.add_heading('Relevansi', level=3)
    doc.add_paragraph(
        'Core engine: LayoutLMv3-base ONNX INT8. Alternatif lebih ringan: distilled BERT '
        '[2501.00031]. Fine-tuning via LoRA CPU [2507.01806]. Inference ~200-500ms per '
        'dokumen — cukup untuk one-at-a-time upload dari 25.000 mahasiswa.'
    )

    # ---- 6.8 Group H: Layout-Aware Extraction ----
    doc.add_heading('6.8 Group H — Layout-Aware Extraction', level=2)
    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Sertifikat sangat bergantung pada layout: nama penerima, tanggal, tanda tangan, logo '
        'institusi — semuanya punya posisi tetap. Tanpa layout information, sulit membedakan '
        'field yang kontennya mirip. Group H membahas model yang memanfaatkan layout + teks + '
        'visual secara simultan.'
    )
    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2406.06236] UnSupDLA', 'Unsupervised layout analysis — tanpa annotation manual, cocok untuk scarcity labeled certificate data'],
            ['[2501.05497] Spatial Info in Small LMs', '2D spatial coordinates + Small LMs untuk document understanding on-premise — bukti layout signal efektif bahkan di model kecil'],
            ['[2509.11720] Docling Layout Analysis', 'RT-DETR real-time layout detection — 78% mAP DocLayNet, langsung integrable via Docling'],
            ['[2304.14936] Redundancy & Biases in KIE Benchmarks', 'Analisis bias SROIE (75% overlap) dan FUNSD (16% overlap) — peringatan interpretasi benchmark'],
            ['[2410.21169] Document Parsing Survey', 'Survey landmark structured IE: modular pipeline vs unified VLM — blueprint arsitektur komprehensif'],
        ]
    )
    doc.add_heading('Temuan Utama', level=3)
    bullets_h = [
        'LayoutLMv3 [2404.10848] state-of-the-art KIE — multimodal (text + bounding box + page image). Cocok untuk semi-terstruktur seperti sertifikat.',
        'Layout analysis RT-DETR [2509.11720] mendeteksi region header, body, signature — preprocessing cerdas.',
        'Sertifikat dari institusi sama → layout konsisten. Lintas institusi → layout sangat bervariasi, relative position features tetap membantu [2501.05497].',
    ]
    for b in bullets_h:
        doc.add_paragraph(b, style='List Bullet')
    doc.add_heading('Relevansi', level=3)
    doc.add_paragraph(
        'Core extraction: LayoutLMv3-base [2404.10848]. Layout detection RT-DETR [2509.11720] '
        'sebagai preprocessing. Untuk multi-halaman: Long-Range Transformer variant [2309.05503]. '
        'Donut [2403.07553] alternatif jika OCR quality rendah.'
    )

    # ---- 6.9 Group I: Production-Scale Architecture ----
    doc.add_heading('6.9 Group I — Production-Scale Architecture', level=2)
    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Proyek ini ditargetkan untuk 25.000 mahasiswa, masing-masing mengisi SKP dengan '
        'upload sertifikat satu per satu (bukan batch). Peak concurrency saat deadline SKP '
        '— mungkin puluhan request simultan. Arsitektur yang dibutuhkan: single CPU server '
        'dengan queue worker sudah cukup.'
    )
    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2309.05429] IE on Business Docs', 'Custom pre-training tasks untuk LayoutLM — layout + text tasks untuk business docs, iterasi improvement'],
            ['[2403.07553] GPT + Donut for Document Indexing', 'Donut OCR-free model — alternatif pipeline end-to-end jika OCR jadi bottleneck, 200M params'],
            ['[2304.12484] DocParser', 'OCR-free IE sebagai alternatif — skip OCR entirely, extraction dari image langsung, 70M params'],
            ['[2305.00795] SelfDocSeg', 'Self-supervised document segmentation — pseudo-label untuk training data, tanpa labeled segmentation'],
            ['[2306.10046] Document Layout Annotation', 'Benchmark dataset untuk layout analysis — guideline annotation region di dokumen'],
            ['[2309.05503] Long-Range Transformer', 'Multi-modal transformer untuk multi-page documents — alternatif untuk sertifikat multi-halaman'],
            ['[2404.10848] LayoutLMv3 Enhanced RE', 'LayoutLMv3 untuk key-value relation extraction — menghubungkan label field ke nilainya, F1 98.60 CORD'],
        ]
    )
    doc.add_heading('Temuan Utama', level=3)
    bullets_i = [
        'Skala 25.000 mahasiswa tidak butuh arsitektur kompleks. Single CPU server + queue worker cukup.',
        'CPU-only deployment feasible [2505.06461]. LayoutLMv3-base INT8 inference 200-500ms di CPU modern.',
        'Multi-bin batching [2412.04504] akomodasi variasi panjang input — sertifikat 1 halaman vs multi-halaman.',
        'Progressive crystallization [2607.07052]: rule → ML → deterministik, roadmap produksi bertahap.',
    ]
    for b in bullets_i:
        doc.add_paragraph(b, style='List Bullet')
    doc.add_heading('Relevansi', level=3)
    doc.add_paragraph(
        'Arsitektur target: single server CPU 8+ core, queue worker PostgreSQL existing, '
        'LayoutLMv3-base ONNX INT8. 250ms-500ms per dokumen. 4 worker parallel → ~8-16 '
        'docs/detik. Jika perlu skalabilitas: Docker + horizontal scaling.'
    )

    doc.add_page_break()

    # ======================== 7. DAFTAR PUSTAKA ========================
    doc.add_heading('7. Daftar Pustaka', level=1)

    refs = [
        '[2302.08893] Active learning for data streams: a survey. 2023.',
        '[2302.14017] Full Stack Optimization of Transformer Inference: a Survey. 2023.',
        '[2304.12484] DocParser: End-to-End OCR-Free Information Extraction from Visually Rich Documents. 2023.',
        '[2304.14936] Investigating Redundancy and Biases in Key Information Extraction Benchmarks. 2023.',
        '[2305.00795] SelfDocSeg: A Self-Supervised Vision-Based Approach Towards Document Segmentation. 2023.',
        '[2305.03253] VicunaNER: Zero/Few-Shot Named Entity Recognition Using Vicuna. 2023.',
        '[2305.14450] An Empirical Study on Information Extraction Using Large Language Models. 2023.',
        '[2305.14975] Just Ask for Calibration: Strategies for Eliciting Calibrated Confidence Scores from Language Models. 2023.',
        '[2306.00526] Layout and Task Aware Instruction Prompt for Zero-Shot Document Image Question Answering. 2023.',
        '[2306.10046] Document Layout Annotation: A Comprehensive Benchmark. 2023.',
        '[2307.12571] MataDoc: Margin and Text Aware Document Dewarping for Arbitrary Boundary. 2023.',
        '[2308.04332] RLHF-Blender: A Configurable Interactive Interface for Learning from Diverse Human Feedback. 2023.',
        '[2308.07777] Enhancing Visually-Rich Document Understanding via Layout Structure Modeling. 2023.',
        '[2308.09341] Document Automation Architectures: Updated Survey in Light of Large Language Models. 2023.',
        '[2309.05429] Improving Information Extraction on Business Documents with Specific Pre-Training Tasks. 2023.',
        '[2309.05503] Long-Range Transformer Architectures for Document Understanding. 2023.',
        '[2309.10952] LMDX: Language Model-Based Document Information Extraction and Localization. 2023.',
        '[2310.03668] GoLLIE: Annotation Guidelines Improve Zero-Shot Information-Extraction. 2023.',
        '[2311.00502] Efficient LLM Inference on CPUs. 2023.',
        '[2311.08883] Distilling Rule-Based Knowledge into Large Language Models. 2023.',
        '[2311.12436] Classifier Calibration with ROC-Regularized Isotonic Regression. 2023.',
        '[2312.07925] Polar-Doc: One-Stage Document Dewarping with Multi-Scope Constraints Under Polar Representation. 2023.',
        '[2401.13744] Conformal Prediction Sets Improve Human Decision Making. 2024.',
        '[2402.10517] Any-Precision LLM: Low-Cost Deployment of Multiple, Different-Sized LLMs. 2024.',
        '[2402.10612] Rowen: Adaptive Retrieval-Augmented Generation for Hallucination Mitigation in LLMs. 2024.',
        '[2403.02310] Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve. 2024.',
        '[2403.07553] The Future of Document Indexing: GPT and Donut Revolutionize Table of Content Processing. 2024.',
        '[2403.13369] Clinical Information Extraction for Low-Resource Languages with Few-Shot Learning. 2024.',
        '[2404.01462] OpenChemIE: An Information Extraction Toolkit for Chemistry Literature. 2024.',
        '[2404.05225] LayoutLLM: Layout Instruction Tuning with Large Language Models for Document Understanding. 2024.',
        '[2404.10848] A LayoutLMv3-Based Model for Enhanced Relation Extraction in Visually-Rich Documents. 2024.',
        '[2404.19329] End-to-End Information Extraction in Handwritten Documents: Understanding Paris Marriage Records. 2024.',
        '[2405.12311] SpotKube: Cost-Optimal Microservices Deployment with Cluster Autoscaling and Spot Pricing. 2024.',
        '[2405.17533] PAE: LLM-Based Product Attribute Extraction for E-Commerce Fashion Trends. 2024.',
        '[2406.02354] Label-Wise Aleatoric and Epistemic Uncertainty Quantification. 2024.',
        '[2406.05348] Toward Reliable Ad-Hoc Scientific Information Extraction: A Case Study on Two Materials Datasets. 2024.',
        '[2406.06236] UnSupDLA: Towards Unsupervised Document Layout Analysis. 2024.',
        '[2410.01609] SynJAC: Synthetic-Data-Driven Joint-Granular Adaptation and Calibration for Domain Specific Scanned Document KIE. 2024.',
        '[2410.06615] QA-Calibration of Language Model Confidence Scores. 2024.',
        '[2410.21169] Document Parsing Unveiled: Techniques, Challenges, and Prospects for Structured Information Extraction. 2024.',
        '[2411.16313] CATP-LLM: Empowering Large Language Models for Cost-Aware Tool Planning. 2024.',
        '[2412.04504] Multi-Bin Batching for Increasing LLM Inference Throughput. 2024.',
        '[2412.14737] On Verbalized Confidence Scores for LLMs. 2024.',
        '[2412.18934] Dovetail: A CPU/GPU Heterogeneous Speculative Decoding for LLM Inference. 2024.',
        '[2501.00031] Distilling Large Language Models for Efficient Clinical Information Extraction. 2025.',
        '[2501.05497] Spatial Information Integration in Small Language Models for Document Layout Generation and Classification. 2025.',
        '[2502.11306] Smoothing Out Hallucinations: Mitigating LLM Hallucination with Smoothed Knowledge Distillation. 2025.',
        '[2502.12017] Scalable and Cost-Efficient ML Inference: Parallel Batch Processing with Serverless Functions. 2025.',
        '[2502.16377] Instruction-Tuning LLMs for Event Extraction with Annotation Guidelines. 2025.',
        '[2503.05488] KIEval: Evaluation Metric for Document Key Information Extraction. 2025.',
        '[2504.02871] Synthesized Annotation Guidelines Are Knowledge-Lite Boosters for Clinical Information Extraction. 2025.',
        '[2504.13359] Cost-of-Pass: An Economic Framework for Evaluating Language Models. 2025.',
        '[2505.06461] Challenging GPU Dominance: When CPUs Outperform for On-Device LLM Inference. 2025.',
        '[2505.13535] Information Extraction from Visually Rich Documents Using LLM-Based Organization. 2025.',
        '[2505.17125] NEXT-EVAL: Next Evaluation of Traditional and LLM Web Data Record Extraction. 2025.',
        '[2505.20429] PreP-OCR: A Complete Pipeline for Document Image Restoration and Enhanced OCR Accuracy. 2025.',
        '[2507.01806] LoRA Fine-Tuning Without GPUs: A CPU-Efficient Meta-Generation Framework for LLMs. 2025.',
        '[2508.06988] TADoc: Robust Time-Aware Document Image Dewarping. 2025.',
        '[2508.14314] Zero-knowledge LLM hallucination detection and mitigation through fine-grained cross-model consistency. 2025.',
        '[2508.14557] Improving OCR Using Internal Document Redundancy. 2025.',
        '[2508.21693] Why Stop at Words? Unveiling the Bigger Picture Through Line-Level OCR. 2025.',
        '[2509.08381] Low-Resource Fine-Tuning for Multi-Task Structured Information Extraction with a Billion-Parameter Model. 2025.',
        '[2509.11720] Advanced Layout Analysis Models for Docling. 2025.',
        '[2509.18101] A Cost-Benefit Analysis of On-Premise Large Language Model Deployment. 2025.',
        '[2509.22906] Extract-0: A Specialized Language Model for Document Information Extraction. 2025.',
        '[2510.12835] Repurposing Annotation Guidelines to Instruct LLM Annotators: A Case Study. 2025.',
        '[2512.13031] Comprehensive Evaluation of Rule-Based, Machine Learning, and Deep Learning Approaches for Document Understanding. 2025.',
        '[2601.22362] Understanding Efficiency: Quantization, Batching, and Serving Strategies in LLM Energy Use. 2026.',
        '[2602.06370] Cost-Aware Model Selection for Text Classification: Multi-Objective Trade-Offs. 2026.',
        '[2604.09529] VL-Calibration: Decoupled Confidence Calibration for Large Vision-Language Models. 2026.',
        '[2607.07052] Progressive Crystallization: Turning Agent Exploration into Deterministic, Lower-Cost Workflows. 2026.',
    ]

    for ref in refs:
        p = doc.add_paragraph(ref)
        p.paragraph_format.space_after = Pt(2)
        for run in p.runs:
            run.font.size = Pt(10)

    # === SIMPAN ===
    output_path = './docs/rangkuman_findings_v2.docx'
    doc.save(output_path)
    print(f'Dokumen berhasil disimpan: {output_path}')
    return output_path


if __name__ == '__main__':
    build_document()
