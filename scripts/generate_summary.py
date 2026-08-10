"""
Generate Rangkuman Kurasi Paper Findings — Certificate Autofill
Fokus: transisi prototype LLM ke production full-ML (no LLM call).
Input: .pdf, .jpg, .png
Output: 12 field auto-fill ke form SKP universitas
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
    run = subtitle.add_run('Strategi Transisi dari Prototype LLM ke Full-ML Production')
    run.font.size = Pt(18)
    run.font.color.rgb = RGBColor(0x44, 0x44, 0x66)

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
    run = src_para.add_run('Sumber: paper_findings.md (363 papers, 57 queries, 9 groups)')
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

    doc.add_heading('1.2 Tujuan Literature Review', level=2)
    doc.add_paragraph(
        'Literature review ini bertujuan: (1) menemukan metode terbaik untuk mengganti '
        'regex extraction dengan model ML yang lebih generalizable untuk beragam format '
        'sertifikat; (2) membangun confidence calibration yang benar-benar mencerminkan '
        'kualitas ekstraksi; (3) mengidentifikasi arsitektur pipeline yang optimal untuk '
        'deployment CPU-only di lingkungan universitas; dan (4) menyusun roadmap transisi '
        'dari prototype LLM ke full ML tanpa API call eksternal.'
    )

    doc.add_heading('1.3 Metodologi Pencarian', level=2)
    doc.add_paragraph(
        'Pencarian dilakukan dengan 57 queries (33 core, 24 exploratory) di arXiv, Google Scholar, '
        'dan Semantic Scholar. Filter: tahun >= 2021, preferensi >= 2023, sitasi > 10. '
        'Paper dikelompokkan ke 9 kelompok topik (Group A–I). Total 363 paper terkumpul, '
        'dikurasi menjadi ~80 paper yang relevan langsung. Sumber data: paper_findings.md dan '
        'paper_keywords.md di direktori ./docs/.'
    )

    doc.add_heading('1.4 Ringkasan Cakupan', level=2)
    add_table(doc,
        ['Group', 'Topik', 'Jumlah Paper Awal', 'Jumlah Terkurasi'],
        [
            ['A', 'LLM Document Extraction', '85', '10'],
            ['B', 'Hybrid Rule-Based + ML', '32', '10'],
            ['C', 'Confidence Calibration', '37', '10'],
            ['D', 'Document Image Preprocessing', '37', '10'],
            ['E', 'Evaluation Framework', '40', '10'],
            ['F', 'Feedback Loop & Active Learning', '23', '5'],
            ['G', 'Model Distillation & Deployment', '65', '10'],
            ['H', 'Layout-Aware Extraction', '21', '10'],
            ['I', 'Production-Scale Architecture', '23', '8'],
        ]
    )

    doc.add_page_break()

    # ======================== 2. RINGKASAN FINDINGS ========================
    doc.add_heading('2. Ringkasan Findings per Group', level=1)

    # ---- GROUP A: LLM Document Extraction ----
    doc.add_heading('2.1 Group A — LLM untuk Document Field Extraction', level=2)

    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Group A mengeksplorasi kemampuan LLM dalam information extraction dari dokumen. '
        'Untuk sertifikat mahasiswa, pendekatan LLM (seperti GPT-4 atau model open-source 7B) '
        'sangat efektif untuk zero-shot extraction pada format yang belum pernah dilihat. '
        'Namun, target akhir proyek ini adalah full ML tanpa LLM di production — sehingga '
        'temuan Group A digunakan bukan untuk deployment, melainkan sebagai guidance untuk '
        'distilasi dan sebagai benchmark ceiling yang ingin dicapai model kecil.'
    )

    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2309.10952] LMDX', 'LLM untuk document IE dengan layout encoding — membuktikan LLM mampu extraction dari VRD'],
            ['[2509.22906] Extract-0', 'Model 7B khusus IE, LoRA + GRPO, capai reward 0.573 — bukti model kecil specialized > general LLM besar'],
            ['[2305.14450] Empirical Study IE with LLMs', 'Benchmark komprehensif GPT family untuk IE: LLM bagus di zero-shot tapi fine-tuned model kecil menang di task spesifik'],
            ['[2304.14936] Redundancy & Biases in KIE Benchmarks', 'SROIE dan FUNSD mengandung redundancy — peringatan untuk tidak over-rely pada public benchmark'],
            ['[2308.09341] Document Automation Survey', 'Survey arsitektur DA pasca-LLM: cascade rule/ML/LLM adalah arsitektur dominan'],
            ['[2305.03253] VicunaNER', 'Zero/few-shot NER pakai Vicuna — framework bisa didistilasi ke student model'],
            ['[2502.11306] Smoothed Knowledge Distillation', 'Distilasi dari teacher LLM ke student kecil mengurangi halusinasi'],
            ['[2402.10612] Rowen: Adaptive RAG', 'RAG untuk mitigasi halusinasi — berguna saat prototyping pakai LLM'],
            ['[2509.08381] Low-Resource Fine-Tuning (1B)', 'Model 1B bisa efektif untuk structured IE — bukti small model cukup'],
            ['[2505.13535] IE from VRDs using LLM', 'Teknik organisasi dokumen ke Independent Textual Sections untuk IE dari VRD'],
        ]
    )

    doc.add_heading('Temuan Utama', level=3)
    paragraphs = [
        'LLM sangat efektif untuk zero-shot extraction tetapi tidak efisien untuk production skala 25.000 mahasiswa. [2509.22906] menunjukkan model 7B specialized (Extract-0) bisa outperform general LLM yang jauh lebih besar — menandakan spesialisasi > scale.',
        'Distilasi dari LLM ke student model (BERT-scale) bisa mempertahankan 90%+ akurasi dengan ukuran 1000x lebih kecil [2501.00031] dan biaya inference yang jauh lebih rendah.',
        'Cascade architecture (rule → small model → LLM fallback) adalah best practice di industri, di mana LLM hanya dipanggil untuk edge cases [2308.09341].',
        'Hallucination mitigation via knowledge distillation [2502.11306] atau RAG [2402.10612] diperlukan jika LLM tetap dipakai di loop — untuk full ML, masalah halusinasi tereduksi karena model kecil tidak generative.',
    ]
    for p in paragraphs:
        doc.add_paragraph(p, style='List Bullet')

    doc.add_heading('Relevansi untuk Full-ML Pipeline', level=3)
    doc.add_paragraph(
        'Temuan utama Group A: LLM bukan target deployment, melainkan teacher untuk distilasi. '
        'Model 7B specialized [2509.22906] dan 1B fine-tuned [2509.08381] adalah ceiling yang '
        'ingin dicapai oleh LayoutLMv3-base (125M) setelah distilasi dan fine-tuning. '
        'Semua rekomendasi arsitektur cascade sudah diperkuat oleh evidence dari [2308.09341].'
    )

    # ---- GROUP B: Hybrid Rule-Based + ML ----
    doc.add_heading('2.2 Group B — Hybrid Rule-Based + ML', level=2)

    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Group B membahas hybrid architecture — kapan pakai rule-based, kapan pakai ML, dan '
        'bagaimana mengkombinasikannya. Pipeline existing sudah mengadopsi pola ini secara '
        'natural (regex fast path → LayoutLM pre-training tasks → OCR fallback). Target '
        'adalah memperkuat tier ML dengan fine-tuned LayoutLMv3 untuk mengganti pure regex, '
        'sambil tetap mempertahankan rule-based form mapper yang sudah teruji.'
    )

    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2512.13031] Comprehensive Eval: Rule vs ML vs DL', 'Perbandingan sistematis 3 pendekatan: rule cocok untuk pattern stabil, ML untuk semi-struktur, DL untuk yang tidak terstruktur'],
            ['[2404.05225] LayoutLLM', 'Layout instruction tuning untuk LLM — layout information vital untuk precise document understanding'],
            ['[2306.00526] Layout-Aware Prompt for DocVQA', 'Prompting dengan layout information untuk zero-shot document QA'],
            ['[2309.05429] Improving IE on Business Documents', 'Custom pre-training tasks untuk LayoutLM: layout + text, langsung applicable ke sertifikat'],
            ['[2308.07777] GraphLayoutLM', 'Layout structure graph untuk document understanding — alternatif untuk relasi antar field'],
            ['[2305.00795] SelfDocSeg', 'Self-supervised document segmentation tanpa labeled data — mengurangi kebutuhan annotation'],
            ['[2509.08381] Low-Resource Fine-Tuning (1B)', 'Small model untuk multi-task structured IE — relevan untuk fine-tuning ke 12 field'],
            ['[2406.05348] Reliable Ad-hoc Scientific IE', 'Error analysis manual GPT-4 untuk IE — insight practical limitations LLM vs fine-tuned'],
            ['[2404.01462] OpenChemIE', 'Pipeline multi-modal IE (text+tabel+gambar) — arsitektur bisa diadaptasi untuk sertifikat'],
            ['[2305.14450] Empirical Study IE with LLMs', 'Basis perbandingan LLM vs traditional NLP — rule/traditional ML lebih cost-effective untuk many-shot scenarios'],
        ]
    )

    doc.add_heading('Temuan Utama', level=3)
    paragraphs = [
        'Rule-based unggul untuk field dengan pattern stabil [2512.13031]: nomor sertifikat, format tanggal standar. ML diperlukan untuk field dengan variasi tinggi: nama kegiatan, role/jabatan, penyelenggara.',
        'Layout information (posisi, bounding box, ukuran font) memberikan signal yang sangat kuat untuk IE [2404.05225] [2308.07777]. Sertifikat sering punya layout konsisten per template — layout-aware model bisa memanfaatkan ini.',
        'Cascade architecture (rule-tier untuk field mudah, ML-tier untuk field sulit) adalah pendekatan yang paling cost-effective [2308.09341]. Tidak perlu mengganti semua komponen sekaligus.',
    ]
    for p in paragraphs:
        doc.add_paragraph(p, style='List Bullet')

    doc.add_heading('Relevansi untuk Full-ML Pipeline', level=3)
    doc.add_paragraph(
        'Pipeline target menggunakan 2-tier cascade: Tier 1 mempertahankan regex untuk field '
        'dengan pattern stabil (nomor sertifikat, tanggal numerik), Tier 2 menggunakan '
        'LayoutLMv3-base (125M params) untuk field semantik (nama kegiatan, role, penyelenggara). '
        'Rule-based form mapper untuk mapping ke opsi dropdown dipertahankan karena sudah '
        'teruji, debuggable, dan maintainable. Jika akurasi tidak memadai, ML classifier '
        'bisa ditambahkan sebagai fallback untuk field tertentu.'
    )

    # ---- GROUP C: Confidence Calibration ----
    doc.add_heading('2.3 Group C — Confidence Calibration', level=2)

    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Salah satu kelemahan terbesar pipeline existing adalah confidence yang hardcoded — '
        'setiap regex match mendapat skor tetap (0.84 untuk organizer, 0.92 untuk role) tanpa '
        'mempertimbangkan kualitas match sebenarnya. Akibatnya, needs_review flag hanya '
        'tertrigger pada field kosong, bukan pada field dengan ekstraksi buruk. Group C '
        'mencari metode kalibrasi confidence yang rigorous dan applicable ke model non-LLM.'
    )

    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2410.01609] SynJAC', 'Kalibrasi scanned document KIE dengan synthetic data — paling relevan untuk sertifikat scan'],
            ['[2604.09529] VL-Calibration', 'Decoupled confidence calibration untuk VLM — komponen reasoning dan persepsi dikalibrasi terpisah'],
            ['[2305.14975] Just Ask for Calibration', 'Strategi eliciting calibrated confidence dari RLHF LLM — insight transferable ke fine-tuned model'],
            ['[2412.14737] Verbalized Confidence for LLMs', 'Analisis confidence score yang di-verbalize — cocok untuk confidence dari JSON output'],
            ['[2410.06615] QA-Calibration', 'Kalibrasi confidence untuk QA/extraction — relevant saat extraction diframe sebagai QA task'],
            ['[2401.13744] Conformal Prediction Sets', 'Menghasilkan candidate set saat confidence rendah — ideal untuk human-in-the-loop verification'],
            ['[2406.02354] Label-wise Aleatoric & Epistemic', 'Dekomposisi uncertainty per-field: noise OCR (aleatoric) vs model uncertainty (epistemic)'],
            ['[2305.14450] Empirical Study on IE', 'Benchmark confidence dan reliability LLM extraction — patokan ceiling untuk model kecil'],
            ['[2406.05348] Toward Reliable Scientific IE', 'Manual error analysis method untuk reliability assessment IE'],
            ['[2311.12436] ROC-Regularized Isotonic Regression', 'Teknik isotonic regression untuk kalibrasi classifier — applicable untuk LayoutLM output'],
        ]
    )

    doc.add_heading('Temuan Utama', level=3)
    paragraphs = [
        'Confidence dari model encoder (LayoutLMv3) bisa dikalibrasi dengan Platt scaling atau isotonic regression pada validation set [2311.12436]. Tidak perlu LLM untuk mendapat confidence score yang bermakna.',
        'Per-field uncertainty decomposition [2406.02354] memungkinkan sistem membedakan: apakah ketidakpastian karena noise OCR (aleatoric) atau karena model tidak familiar dengan format (epistemic). Dua tipe ini butuh penanganan berbeda.',
        'Conformal prediction [2401.13744] memberikan garansi statistik: misal "dengan 90% confidence, nilai yang benar ada dalam candidate set berisi 2-3 opsi." Ideal untuk field dengan banyak kemungkinan.',
        'SynJAC [2410.01609] menggunakan synthetic data untuk joint adaptation + kalibrasi KIE — pipeline yang paling cocok untuk sertifikat karena bisa generate synthetic cert layout.',
    ]
    for p in paragraphs:
        doc.add_paragraph(p, style='List Bullet')

    doc.add_heading('Relevansi untuk Full-ML Pipeline', level=3)
    doc.add_paragraph(
        'Ganti confidence hardcoded dengan Platt scaling pada logit output LayoutLMv3. '
        'Gunakan conformal prediction [2401.13744] untuk field dengan banyak kandidat (nama kegiatan, '
        'penyelenggara). Propagate OCR confidence per-karakter dari RapidOCR (yang saat ini dibuang) '
        'sebagai input feature tambahan ke model — memberikan signal tentang kualitas sumber teks. '
        'Threshold perlu ditentukan dari precision-recall curve, bukan angka 0.80 yang asal.'
    )

    # ---- GROUP D: Document Image Preprocessing ----
    doc.add_heading('2.4 Group D — Document Image Preprocessing', level=2)

    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Input sertifikat bisa berupa PDF (digital atau hasil scan) atau foto dari smartphone. '
        'Kualitas gambar sangat bervariasi: ada yang lurus, miring, terlipat, atau terpotong. '
        'Preprocessing yang baik adalah fondasi pipeline — tanpa OCR yang bersih, model '
        'ekstraksi sebaik apa pun akan gagal karena inputnya sudah rusak.'
    )

    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2508.06988] TADoc', 'Time-aware document dewarping untuk foto device — langsung relevan untuk upload dari HP'],
            ['[2307.12571] MataDoc', 'Margin and text aware dewarping untuk arbitrary boundary — sertifikat sering difoto tidak sempurna'],
            ['[2312.07925] Polar-Doc', 'One-stage dewarping dengan polar coordinate — lebih efisien, lebih akurat'],
            ['[2508.14557] Internal Document Redundancy', 'Memanfaatkan redundansi internal dokumen untuk OCR lebih baik — unsupervised'],
            ['[2508.21693] Line-Level OCR', 'Line-level OCR lebih robust untuk certificate dibanding word-level, karena teks sering rapat'],
            ['[2309.05503] Long-Range Transformer', 'Multi-page document understanding — untuk sertifikat multi-halaman'],
            ['[2304.12484] DocParser', 'OCR-free IE sebagai alternatif — skip OCR entirely, extraction dari image langsung'],
            ['[2505.20429] PreP-OCR', 'Pipeline restorasi + post-OCR correction untuk historical documents'],
            ['[2306.10046] Document Layout Annotation', 'Benchmark dataset untuk layout analysis — guideline annotation region di dokumen'],
            ['[2403.07553] GPT + Donut for Document Indexing', 'Donut OCR-free model — alternatif pipeline jika OCR jadi bottleneck'],
        ]
    )

    doc.add_heading('Temuan Utama', level=3)
    paragraphs = [
        'Dewarping penting untuk sertifikat hasil foto HP [2508.06988] [2307.12571] [2312.07925]. TADoc menawarkan time-aware approach yang mempertimbangkan degradasi waktu. Polar-Doc menawarkan one-stage yang lebih efisien.',
        'Line-level OCR [2508.21693] memberikan akurasi lebih baik untuk teks rapat seperti di sertifikat. Pipeline bisa mengkombinasikan word-level (RapidOCR) dan line-level (DocTR) untuk hasil optimal.',
        'Internal document redundancy [2508.14557] — teks yang berulang (header, footer, nomor halaman) bisa dimanfaatkan untuk self-supervised OCR improvement.',
        'Donut [2403.07553] menawarkan OCR-free extraction — bisa jadi alternatif jika OCR kualitas rendah. Trade-off: Donut model (200M params) lebih berat dari OCR pipeline tradisional.',
    ]
    for p in paragraphs:
        doc.add_paragraph(p, style='List Bullet')

    doc.add_heading('Relevansi untuk Full-ML Pipeline', level=3)
    doc.add_paragraph(
        'Pertahankan PyMuPDF + RapidOCR + Tesseract sebagai baseline OCR. Tambahkan dewarping '
        'sebagai preprocessing opsional (deteksi distorsi dulu, baru dewarp jika perlu). '
        'Tambahkan layout detection (RT-DETR via Docling [2509.11720]) untuk segmentasi region '
        'penting sebelum OCR — mengurangi noise dari area tidak relevan. '
        'OCR confidence per-karakter dari RapidOCR harus di-capture dan diteruskan ke model '
        'sebagai input feature (saat ini dibuang).'
    )

    # ---- GROUP E: Evaluation Framework ----
    doc.add_heading('2.5 Group E — Evaluation Framework', level=2)

    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Untuk mengevaluasi pipeline extraction, metrik yang tepat harus dipilih. '
        'Accuracy end-to-end saja tidak cukup — setiap field punya karakteristik berbeda '
        '(tanggal harus exact match, nama kegiatan bisa partial match). Group E mengkaji '
        'metrik evaluasi yang sesuai untuk document KIE beserta metodologi quality control-nya.'
    )

    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2503.05488] KIEval', 'Metrik evaluasi khusus Document KIE — mempertimbangkan aplikasi-centric evaluation'],
            ['[2305.14450] Empirical Study on IE', 'Framework evaluasi IE komprehensif — patokan evaluasi multi-model'],
            ['[2310.03668] GoLLIE', 'Annotation guidelines meningkatkan zero-shot IE — penting untuk quality control labeling'],
            ['[2504.02871] Synthesized Annotation Guidelines', 'Auto-generated guidelines untuk IE annotation — mengurangi effort manual'],
            ['[2505.17125] NEXT-EVAL', 'Framework evaluasi rule-based vs LLM extraction — applicable untuk perbandingan sebelum/sesudah ML'],
            ['[2404.01462] OpenChemIE', 'Contoh evaluation framework multi-modal IE (text, tabel, gambar)'],
            ['[2406.05348] Manual Error Analysis', 'Metodologi manual error analysis untuk IE — essential untuk memahami failure mode'],
            ['[2404.19329] End-to-end IE in Handwritten Docs', 'Contoh evaluasi end-to-end IE di real historical documents — metodologi transferable'],
        ]
    )

    doc.add_heading('Temuan Utama', level=3)
    paragraphs = [
        'KIEval [2503.05488] menekankan bahwa metrik harus aplikasi-centric: per-field F1 adalah metrik primer, karena field tertentu (tanggal) lebih kritikal daripada field lain (deskripsi).',
        'End-to-end accuracy bisa misleading [2304.14936]. Field-level evaluation memberikan gambaran lebih akurat tentang di mana pipeline gagal dan apa yang perlu diperbaiki.',
        'Annotation guidelines [2310.03668] [2504.02871] meningkatkan konsistensi labeling. GoLLIE membuktikan bahwa guidelines yang baik bahkan bisa meningkatkan zero-shot IE.',
        'NEXT-EVAL [2505.17125] menyediakan framework untuk membandingkan pendekatan sebelum dan sesudah migrasi ke ML — berguna untuk mengukur improvement.',
    ]
    for p in paragraphs:
        doc.add_paragraph(p, style='List Bullet')

    doc.add_heading('Relevansi untuk Full-ML Pipeline', level=3)
    doc.add_paragraph(
        'Gunakan per-field F1 sebagai metrik primer, dengan bobot berbeda per field (tanggal dan '
        'nomor sertifikat punya bobot lebih tinggi). Kumpulkan 100-200 sertifikat sebagai '
        'labeled test set awal. Gunakan KIEval [2503.05488] untuk evaluasi aplikasi-centric. '
        'Lakukan manual error analysis [2406.05348] secara berkala untuk mengidentifikasi '
        'failure mode baru yang belum tercover training set.'
    )

    # ---- GROUP F: Feedback Loop & Active Learning ----
    doc.add_heading('2.6 Group F — Feedback Loop & Active Learning', level=2)

    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Sertifikat mahasiswa sangat beragam — setiap penyelenggara punya format sendiri. '
        'Tidak mungkin mengumpulkan semua variasi di awal. Group F membahas bagaimana sistem '
        'bisa terus belajar dari koreksi user (feedback loop) dan memilih sertifikat mana '
        'yang paling informatif untuk dilabeli (active learning) — essential untuk '
        'continuous improvement di production.'
    )

    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2302.08893] Active Learning for Data Streams', 'Survey comprehensive AL — strategi memilih sample informatif untuk labeling'],
            ['[2308.04332] RLHF-Blender', 'Framework human-in-the-loop untuk ML systems — bisa diadaptasi untuk koreksi user di form'],
            ['[2309.05429] IE Pre-Training on Business Docs', 'Iterative improvement via pre-training tasks baru — pipeline bisa terus di-refine dengan data baru'],
            ['[2306.10046] Document Layout Annotation', 'Feedback loop dalam document annotation process — guideline untuk quality control'],
            ['[2305.00795] SelfDocSeg', 'Self-supervised learning mengurangi kebutuhan labeled data — pseudo-label dari rule-based extraction'],
        ]
    )

    doc.add_heading('Temuan Utama', level=3)
    paragraphs = [
        'Active learning [2302.08893] memungkinkan sistem memilih certificate yang paling "berguna" untuk dilabeli — yang confidence-nya rendah atau out-of-distribution. Ini meminimalkan effort labeling manual.',
        'Koreksi user di form bisa dijadikan feedback signal [2308.04332]. Bedakan antara: user tidak sengaja salah (noise) vs user mengoreksi kesalahan sistem (signal).',
        'Weak supervision [2305.00795]: output rule-based yang confidence tinggi bisa jadi pseudo-label untuk training — tanpa perlu annotator manusia.',
        'SelfDocSeg [2305.00795] membuktikan self-supervised approach mengurangi kebutuhan labeled data secara signifikan.',
    ]
    for p in paragraphs:
        doc.add_paragraph(p, style='List Bullet')

    doc.add_heading('Relevansi untuk Full-ML Pipeline', level=3)
    doc.add_paragraph(
        'Implementasi feedback loop: setiap koreksi user di form → disimpan sebagai candidate '
        'training sample. Active learning: sample dengan confidence antara 0.4-0.8 diprioritaskan '
        'untuk review manual. Weak supervision: output Tier 1 (regex) dengan confidence > 0.90 '
        'bisa digunakan sebagai pseudo-label untuk training Tier 2 (LayoutLMv3). Ini memungkinkan '
        'model terus membaik tanpa intervention manual terus-menerus.'
    )

    # ---- GROUP G: Model Distillation & Efficient Deployment ----
    doc.add_heading('2.7 Group G — Model Distillation & Efficient Deployment', level=2)

    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Constraint utama: CPU-only inference, tanpa GPU, tanpa API call ke LLM. Ini berarti '
        'model harus ringan (maks 500M params), bisa di-quantize (INT8/INT4), dan inference '
        'di bawah 1 detik per dokumen. Group G membahas distilasi dari LLM ke small model, '
        'quantization, dan cost analysis deployment.'
    )

    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2501.00031] Distilling LLMs for Clinical IE', 'Distilasi LLM ke BERT (1000x lebih kecil) untuk NER — mempertahankan 90%+ akurasi dengan ukuran 0.1%'],
            ['[2405.17533] PAE: Product Attribute Extraction', 'LLM-based attribute extraction e-commerce — transferable ke certificate field extraction'],
            ['[2311.08883] Distilling Rule-based Knowledge into LLMs', 'Rule-based knowledge distillation ke LLM — bidirectional: bisa juga dari LLM ke rule-based system'],
            ['[2504.13359] Cost-of-Pass', 'Framework ekonomi untuk evaluasi cost-effectiveness LLM — untuk keputusan kapan pakai LLM vs small model'],
            ['[2509.18101] Cost-Benefit On-Premise vs Commercial', 'Analisis biaya on-premise vs API LLM — compelling case untuk full ML on-premise'],
            ['[2602.06370] Cost-Aware Model Selection', 'Multi-objective trade-off fine-tuned encoder vs LLM prompting — small model menang untuk structured tasks'],
            ['[2311.00502] Efficient LLM Inference on CPUs', 'INT4 quantization untuk CPU inference — membuktikan LLM inference di CPU feasible dengan quantisasi'],
            ['[2505.06461] CPUs vs GPUs for On-Device LLM', 'CPU bisa outperform GPU untuk LLM inference di kondisi tertentu — validasi pendekatan CPU-only'],
            ['[2507.01806] LoRA Fine-Tuning Without GPUs', 'Fine-tuning LoRA di CPU laptop — bisa adaptasi LayoutLMv3 tanpa GPU mahal'],
            ['[2607.07052] Progressive Crystallization', 'Transisi LLM agent → deterministic rules di production — framework transisi yang sistematis'],
        ]
    )

    doc.add_heading('Temuan Utama', level=3)
    paragraphs = [
        'Distilasi LLM → BERT [2501.00031] menunjukkan model 1000x lebih kecil bisa mempertahankan 90%+ akurasi NER dengan harga inference yang jauh lebih murah. Untuk LayoutLMv3-base (125M), distilasi dari LLM-labeling bisa signifikan meningkatkan akurasi.',
        'CPU inference dengan INT4 quantization [2311.00502] membuktikan inference model transformer di CPU feasible. LayoutLMv3-base (125M) dengan INT8 bisa inference dalam 200-500ms di CPU modern.',
        'Cost analysis [2509.18101] [2602.06370] secara konsisten menunjukkan fine-tuned encoder model mengungguli LLM prompting untuk structured extraction tasks dalam hal cost-effectiveness — mendukung keputusan full ML.',
        'Progressive crystallization [2607.07052] menyediakan framework sistematis: mulai dari rule-based → tambah ML → deterministik. Cocok sebagai roadmap transisi.',
        'LoRA fine-tuning tanpa GPU [2507.01806] memungkinkan fine-tuning LayoutLMv3 di CPU — menurunkan barrier untuk iterasi model.',
    ]
    for p in paragraphs:
        doc.add_paragraph(p, style='List Bullet')

    doc.add_heading('Relevansi untuk Full-ML Pipeline', level=3)
    doc.add_paragraph(
        'Rekomendasi model: LayoutLMv3-base (125M params) sebagai core extraction engine, '
        'di-quantize ke INT8 via ONNX Runtime. Alternatif jika perlu lebih ringan: '
        'distilasi LayoutLMv3 ke BERT-based encoder (110M) [2501.00031]. '
        'Untuk fine-tuning, gunakan LoRA di CPU — tidak perlu GPU [2507.01806]. '
        'LayoutLMv3-base inference ~200-500ms per dokumen di CPU modern — cukup untuk '
        'one-at-a-time upload dari 25.000 mahasiswa selama periode deadline.'
    )

    # ---- GROUP H: Layout-Aware Extraction ----
    doc.add_heading('2.8 Group H — Layout-Aware Extraction', level=2)

    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Sertifikat adalah dokumen yang sangat bergantung pada layout: nama penerima, tanggal, '
        'tanda tangan, logo institusi — semuanya punya posisi tetap. Tanpa informasi layout, '
        'sulit membedakan field yang kontennya mirip (misal: nama peserta vs nama pemberi). '
        'Group H membahas model yang memanfaatkan layout + teks + visual secara simultan.'
    )

    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2410.21169] Document Parsing Survey', 'Survey landmark tentang structured IE: modular pipeline vs unified VLM — blueprint arsitektur'],
            ['[2509.11720] Docling Layout Analysis', 'RT-DETR real-time layout detection — langsung integrable ke pipeline existing via Docling'],
            ['[2406.06236] UnSupDLA', 'Unsupervised layout analysis — tanpa annotation manual, cocok untuk scarcity labeled certificate data'],
            ['[2501.05497] Spatial Info in Small LMs', '2D spatial coordinates + Small LMs untuk document understanding on-premise'],
            ['[2404.05225] LayoutLLM', 'Layout instruction tuning — LLM di-tune untuk memahami layout, 143 sitasi'],
            ['[2404.10848] LayoutLMv3 for Relation Extraction', 'LayoutLMv3 untuk key-value relation extraction — menghubungkan label field ke nilainya'],
            ['[2309.05429] IE on Business Docs', 'Custom pre-training tasks untuk LayoutLM — layout + text tasks untuk business docs'],
            ['[2309.05503] Long-Range Transformer', 'Multi-modal transformer untuk multi-page documents'],
            ['[2305.00795] SelfDocSeg', 'Self-supervised visual document segmentation'],
            ['[2403.07553] GPT + Donut for Document Indexing', 'OCR-free model (Donut) sebagai alternatif pipeline end-to-end'],
        ]
    )

    doc.add_heading('Temuan Utama', level=3)
    paragraphs = [
        'LayoutLMv3 [2404.10848] adalah state-of-the-art untuk KIE pada dokumen bisnis — menggabungkan text, layout (bounding box), dan visual features (page image embeddings). Untuk sertifikat, LayoutLMv3-base adalah pilihan ideal karena cukup ringan untuk CPU dan sangat efektif pada data semi-terstruktur.',
        'Layout analysis dengan RT-DETR [2509.11720] bisa mendeteksi region header, body, signature, stamp — memungkinkan preprocessing yang lebih cerdas. UnSupDLA [2406.06236] bahkan bisa melakukannya tanpa labeled data.',
        'Untuk sertifikat dari institusi yang sama, layout-nya relatif konsisten. Layout-aware model bisa memanfaatkan konsistensi ini. Namun, untuk sertifikat lintas institusi (yang layout-nya sangat berbeda), spatial features tetap membantu dengan mempelajari pola posisi field relatif.',
        'Donut [2403.07553] sebagai alternatif OCR-free — end-to-end extraction dari image. Trade-off: akurasi lebih baik di noisy input, tapi lebih berat secara komputasi.',
    ]
    for p in paragraphs:
        doc.add_paragraph(p, style='List Bullet')

    doc.add_heading('Relevansi untuk Full-ML Pipeline', level=3)
    doc.add_paragraph(
        'Core extraction engine menggunakan LayoutLMv3-base [2404.10848] yang menerima '
        'input text + bounding box + page image. Layout detection (RT-DETR) sebagai '
        'preprocessing untuk segmentasi region penting. Untuk sertifikat multi-halaman, '
        'gunakan Long-Range Transformer variant [2309.05503]. Alternatif Donut [2403.07553] '
        'jika kualitas OCR sangat rendah — dengan pertimbangan komputasi tambahan.'
    )

    # ---- GROUP I: Production-Scale Architecture ----
    doc.add_heading('2.9 Group I — Production-Scale Architecture', level=2)

    doc.add_heading('Kontekstual', level=3)
    doc.add_paragraph(
        'Proyek ini ditargetkan untuk 25.000 mahasiswa, masing-masing mengisi SKP dengan '
        'upload sertifikat satu per satu (bukan batch). Peak concurrency diproyeksikan saat '
        'deadline pengisian SKP — mungkin puluhan request simultan, bukan ribuan. Arsitektur '
        'yang dibutuhkan sederhana: single CPU server dengan queue worker sudah cukup. '
        'Group I mengkaji opsi deployment untuk skala ini.'
    )

    doc.add_heading('Paper Terpilih', level=3)
    add_table(doc,
        ['Paper', 'Key Insight'],
        [
            ['[2403.02310] Sarathi-Serve', 'Optimasi serving LLM — chunked-prefill, teknik yang bisa diadaptasi untuk batch inference'],
            ['[2302.14017] Full Stack Optimization Survey', 'Survey optimasi inference dari hardware ke software — komprehensif'],
            ['[2505.06461] CPUs Outperform GPUs', 'CPU bisa outperform GPU untuk LLM inference di device tertentu — validasi CPU-only approach'],
            ['[2507.01806] LoRA Fine-Tuning Without GPUs', 'Fine-tuning LoRA di CPU laptop — memungkinkan retraining berkala tanpa GPU'],
            ['[2412.04504] Multi-Bin Batching', 'Strategi batching untuk LLM inference — bisa diadaptasi untuk LayoutLM inference'],
            ['[2607.07052] Progressive Crystallization', 'Transisi LLM → deterministic rules — roadmap untuk produksi bertahap'],
            ['[2601.22362] Quantization & Batching', 'Trade-off presisi, batching, energy efficiency — referensi optimasi deployment'],
            ['[2502.12017] Serverless ML Inference', 'Serverless untuk batch ML inference — auto-scale untuk peak handling'],
        ]
    )

    doc.add_heading('Temuan Utama', level=3)
    paragraphs = [
        'Skala proyek ini (25.000 mahasiswa, satu-at-a-time) tidak membutuhkan arsitektur kompleks. Single CPU server + queue worker sudah mencukupi. Peak handling bisa menggunakan serverless functions [2502.12017] jika diperlukan.',
        'CPU-only deployment bukan lagi keterbatasan. [2505.06461] membuktikan CPU bisa outperform GPU untuk model kecil. LayoutLMv3-base (125M) dengan INT8 quantization bisa inference dalam 200-500ms di CPU modern.',
        'Multi-bin batching [2412.04504] bisa mengakomodasi variasi panjang input — berguna jika ada sertifikat 1 halaman vs multi-halaman.',
        'Progressive crystallization [2607.07052] sebagai roadmap: mulai dari rule-based full → tambah ML untuk field tertentu → deterministik penuh.',
    ]
    for p in paragraphs:
        doc.add_paragraph(p, style='List Bullet')

    doc.add_heading('Relevansi untuk Full-ML Pipeline', level=3)
    doc.add_paragraph(
        'Arsitektur target: single server dengan CPU modern (8+ core), queue worker berbasis '
        'PostgreSQL (existing), LayoutLMv3-base ONNX INT8. Estimasi CPU time: 250ms-500ms '
        'per dokumen. Dengan 4 worker parallel, throughput ~8-16 dokumen/detik — lebih dari '
        'cukup untuk peak usage. Jika perlu skalabilitas: containerize dengan Docker dan '
        'deploy di Kubernetes dengan HPA untuk auto-scale saat peak.'
    )

    doc.add_page_break()

    # ======================== 3. VERDICT & REKOMENDASI ========================
    doc.add_heading('3. Verdict & Rekomendasi Arsitektur', level=1)

    # 3.1 Arsitektur Pipeline
    doc.add_heading('3.1 Arsitektur Pipeline yang Direkomendasikan', level=2)
    doc.add_paragraph(
        'Pipeline target terdiri dari 4 komponen utama yang berjalan secara sequential:'
    )
    doc.add_paragraph('Input (PDF/JPG/PNG) → Preprocessing → Cascade Extraction → Confidence → Form Mapping', style='List Bullet')

    pipeline_steps = [
        ['Tahap', 'Komponen', 'Fungsi', 'Estimasi Latency'],
        ['1', 'Input Validation', 'Validasi format, checksum', '<50ms'],
        ['2', 'Preprocessing', 'Konversi ke image, dewarping (if needed), layout detection', '200-500ms'],
        ['3', 'Tier 1: Regex Fast Path', 'Ekstraksi field dengan pattern stabil (nomor, tanggal numerik)', '<50ms'],
        ['4', 'Tier 2: LayoutLMv3-base', 'Ekstraksi field semantik (nama kegiatan, role, penyelenggara)', '200-500ms'],
        ['5', 'Confidence Calibration', 'Platt scaling, conformal prediction sets', '<50ms'],
        ['6', 'Form Mapper', 'Rule-based mapping ke opsi dropdown', '<50ms'],
    ]
    add_table(doc, pipeline_steps[0], pipeline_steps[1:])
    doc.add_paragraph(
        'Total estimasi: ~500ms-1.2s per dokumen. Cocok untuk UX real-time upload.'
    )

    # 3.2 OCR & Preprocessing
    doc.add_heading('3.2 Komponen Preprocessing & OCR', level=2)
    doc.add_paragraph(
        'Rekomendasi: pertahankan PyMuPDF + RapidOCR + Tesseract sebagai baseline OCR, '
        'tambahkan dewarping dan layout detection.'
    )
    add_table(doc,
        ['Komponen', 'Pilihan', 'Trade-off'],
        [
            ['OCR Engine', 'RapidOCR + Tesseract (existing)', 'RapidOCR cepat, Tesseract akurat untuk teks kecil. Kombinasi sudah optimal.'],
            ['Dewarping', 'TADoc [2508.06988] / Polar-Doc [2312.07925]', 'Tambah 200-500ms latency, tapi akurasi OCR naik signifikan untuk foto HP. Gunakan hanya jika distortion detected.'],
            ['Layout Detection', 'RT-DETR via Docling [2509.11720]', 'Membantu segmentasi region penting. Bisa skip jika gambar sudah lurus dan bersih.'],
            ['OCR-free alternative', 'Donut [2403.07553]', 'Lebih akurat di noisy input, tapi lebih berat (200M params). Simpan sebagai fallback.'],
            ['Propagate OCR confidence', 'Capture RapidOCR per-char confidence', 'Saat ini dibuang. Perlu perubahan kecil di ocr_fallback.py.'],
        ]
    )
    doc.add_paragraph(
        'Insight dari paper: Line-level OCR [2508.21693] memberikan akurasi lebih baik untuk teks '
        'rapat di sertifikat. Internal document redundancy [2508.14557] bisa dimanfaatkan untuk '
        'self-supervised OCR improvement tanpa labeled data. PreP-OCR [2505.20429] menawarkan '
        'pipeline restorasi lengkap untuk dokumen degradasi.'
    )

    # 3.3 Core Extraction
    doc.add_heading('3.3 Komponen Core Extraction — Cascade ML', level=2)
    doc.add_paragraph(
        'Rekomendasi utama: fine-tuned LayoutLMv3-base sebagai core engine, dengan 2-tier cascade.'
    )

    doc.add_paragraph(
        'Kenapa LayoutLMv3-base:'
    )
    bullets = [
        '125M params — ringan, bisa inference CPU dengan INT8 quantization (200-500ms per dokumen)',
        'Multimodal: text + layout (bounding box) + visual (page image) [2404.10848] — ideal untuk sertifikat yang sangat bergantung pada layout',
        'State-of-the-art di KIE benchmark FUNSD, SROIE, CORD — sudah terbukti untuk dokumen semi-terstruktur mirip sertifikat [2309.05429]',
        'Bisa fine-tune dengan LoRA di CPU tanpa GPU [2507.01806]',
        'Distillation source: LLM-labeling untuk training data [2501.00031]',
    ]
    for b in bullets:
        doc.add_paragraph(b, style='List Bullet')

    doc.add_paragraph(
        'Alternatif dan rationale:'
    )
    alt_rows = [
        ['LayoutLMv3-base (125M)', 'Rekomendasi utama — balance size/akurasi', ''],
        ['Distilled BERT-NER (110M)', 'Jika perlu lebih ringan [2501.00031]', 'Hilang layout information'],
        ['Donut (200M)', 'OCR-free alternatif [2403.07553]', 'Lebih berat, tapi lebih robust di noisy input'],
        ['LLM API (GPT-4, Claude)', 'Hanya untuk prototyping', 'Mahal, tidak scalable, tidak sesuai target full ML'],
    ]
    add_table(doc, ['Model', 'Kapan Pakai', 'Kelemahan'], alt_rows)

    # 3.4 Layout Understanding
    doc.add_heading('3.4 Komponen Layout Understanding', level=2)
    doc.add_paragraph(
        'Layout understanding adalah komponen kritikal untuk sertifikat. LayoutLMv3 sudah '
        'mengintegrasikan layout information (bounding box + page image) secara native. '
        'Tambahan: layout detection (RT-DETR) untuk segmentasi region sebelum OCR -- '
        'mengurangi noise dari area tidak relevan.'
    )
    doc.add_paragraph(
        'Kapan layout penting vs tidak: untuk sertifikat dari institusi yang sama dengan '
        'layout konsisten, layout sangat penting [2404.10848]. Untuk sertifikat dari institusi '
        'berbeda, layout tetap membantu sebagai relative position features [2501.05497]. '
        'Jika hanya memproses teks dari PDF digital (bukan scan), layout kurang kritikal — '
        'tapi untuk foto dan scan, layout jadi penentu akurasi [2509.11720].'
    )

    # 3.5 Confidence & QA
    doc.add_heading('3.5 Komponen Confidence & Quality Assurance', level=2)
    doc.add_paragraph(
        'Ganti sistem confidence saat ini (hardcoded 0.80-0.92) dengan kalibrasi statistik:'
    )
    bullets = [
        'Ambil logit/probabilitas dari LayoutLMv3 output layer → Platt scaling pada validation set [2311.12436]',
        'Propagate OCR confidence per-karakter dari RapidOCR (yang saat ini dibuang) sebagai input feature tambahan',
        'Per-field uncertainty decomposition [2406.02354]: bedakan noise OCR (aleatoric) vs model tidak familiar (epistemic)',
        'Conformal prediction [2401.13744]: untuk field dengan banyak kandidat, hasilkan prediction set (2-3 candidate)',
        'Threshold bukan 0.80 hardcoded, tapi ditentukan dari precision-recall curve pada validation set',
    ]
    for b in bullets:
        doc.add_paragraph(b, style='List Bullet')

    # 3.6 Form Mapper
    doc.add_heading('3.6 Komponen Form Mapper', level=2)
    doc.add_paragraph(
        'Rekomendasi: tetap rule-based untuk production awal, dengan opsi ML fallback untuk edge cases.'
    )
    doc.add_paragraph(
        'Alasan: (1) Aturan existing sudah sophisticated — mencakup signature context detection, '
        'Airlangga-specific logic, cross-field coupling antara tingkat dan penyelenggara. '
        '(2) Rule-based maintainable dan debuggable — ketika mapping salah, bisa langsung '
        'dilacak ke aturan spesifik. (3) ML untuk 12 field dengan 6-9 opsi dropdown masing-masing '
        'butuh dataset besar yang belum tersedia. Jika akurasi rule-based terbukti tidak memadai '
        'untuk field tertentu, tambah ML classifier sebagai fallback.'
    )

    # 3.7 Deployment Strategy
    doc.add_heading('3.7 Deployment Strategy (CPU-Only, On-Premise)', level=2)
    doc.add_paragraph(
        'Target skala: ~25.000 mahasiswa, upload satu-at-satu, peak concurrency puluhan '
        'request simultan. Estimasi jumlah sertifikat: 25.000 × ~10 SKP per mahasiswa '
        '= ~250.000 total sertifikat per periode. Dengan asumsi processing per dokumen '
        '500ms-1.2s (Tier 1 + Tier 2 jika perlu):'
    )
    calc_rows = [
        ['Skenario', 'Estimasi'],
        ['Processing per dokumen (rata-rata)', '500ms-1.2s'],
        ['Worker parallel (4 core)', '4 worker parallel'],
        ['Throughput dengan 4 worker', '~4-8 dokumen/detik'],
        ['Total sertifikat per semester', '~250.000'],
        ['Total CPU time', '~35-70 jam (non-parallel) / ~9-18 jam (4 worker)'],
        ['Peak handling (1.000 request dalam 1 jam)', '~5-10 menit dengan 4 worker'],
    ]
    add_table(doc, calc_rows[0], calc_rows[1:])
    doc.add_paragraph(
        'Kesimpulan: single server CPU modern (8+ core, 32GB RAM) sudah cukup. '
        'Model LayoutLMv3-base di-export ke ONNX dan di-quantize INT8. '
        'Queue worker PostgreSQL (existing) sudah memadai — tidak perlu Redis/RabbitMQ. '
        'Jika perlu skalabilitas tambahan: Docker container + horizontal scaling sederhana.'
    )

    # 3.8 Evaluation Framework
    doc.add_heading('3.8 Evaluation Framework', level=2)
    doc.add_paragraph(
        'Metrik evaluasi yang direkomendasikan:'
    )
    eval_rows = [
        ['Metrik', 'Deskripsi', 'Level'],
        ['Per-field F1', 'F1 untuk tiap field, dengan bobot berbeda', 'Primer'],
        ['Field-level Exact Match', 'Persentase field yang exact match', 'Sekunder'],
        ['Character Error Rate (CER)', 'Untuk text field (nama kegiatan, penyelenggara)', 'Sekunder'],
        ['End-to-end document accuracy', 'Semua field benar dalam satu dokumen', 'Tersier'],
        ['KIEval score', 'Application-centric metric [2503.05488]', 'Primer'],
    ]
    add_table(doc, eval_rows[0], eval_rows[1:])
    doc.add_paragraph(
        'Dataset evaluasi: 100-200 sertifikat labeled sebagai test set. '
        'Benchmark publik: FUNSD, SROIE, CORD [2304.14936] untuk baseline. '
        'Annotation guidelines: gunakan GoLLIE framework [2310.03668] untuk quality control labeling. '
        'Evaluasi dilakukan setelah setiap fine-tuning cycle.'
    )

    # 3.9 Continuous Improvement
    doc.add_heading('3.9 Continuous Improvement (Feedback Loop)', level=2)
    doc.add_paragraph(
        'Sistem harus terus belajar dari data baru tanpa intervensi manual terus-menerus. '
        'Rekomendasi berdasarkan Group F:'
    )
    bullets = [
        'Active learning [2302.08893]: pilih sertifikat dengan confidence 0.4-0.8 untuk review manual. Skip yang <0.4 (terlalu noise) dan >0.8 (sudah yakin).',
        'Weak supervision: output Tier 1 (regex) dengan confidence >0.90 dijadikan pseudo-label [2305.00795] untuk training Tier 2 — tanpa annotator.',
        'Human-in-the-loop [2308.04332]: koreksi user di form dikumpulkan. Filter noise: hanya simpan koreksi yang konsisten (user tidak mengubah 3x berturut).',
        'Retraining cycle: fine-tuning ulang LayoutLMv3 setiap 1-2 bulan dengan data baru terkumpul. Gunakan LoRA CPU [2507.01806] untuk fine-tuning tanpa GPU.',
        'Progressive crystallization [2607.07052]: jika suatu field sudah mencapai akurasi >95% dengan ML, pertimbangkan untuk meng-crystallize ke deterministic rules.',
    ]
    for b in bullets:
        doc.add_paragraph(b, style='List Bullet')

    # 3.10 Decision Matrix
    doc.add_heading('3.10 Decision Matrix', level=2)
    doc.add_paragraph(
        'Tabel berikut merangkum pilihan untuk setiap komponen pipeline, dari kondisi saat ini '
        '(prototype) menuju target (full ML).'
    )
    decision_rows = [
        ['Komponen', 'Sekarang (Prototype)', 'Interim (3-6 bulan)', 'Target (Full ML)', 'Rekomendasi'],
        ['OCR & Preprocessing', 'PyMuPDF + RapidOCR + Tesseract, OCR confidence dibuang', '+ dewarping + layout detection + OCR confidence propagation', '+ Line-level OCR [2508.21693] + Donut fallback [2403.07553]', 'Interim sudah cukup. Donut jika OCR quality rendah.'],
        ['Core Extraction', 'Regex only (field_extractor.py)', 'Regex + LayoutLMv3-base cascade (train 100-500 samples)', 'LayoutLMv3-base fully replaces regex', 'Interim. Jangan buru-buru ganti regex — cascade lebih safe.'],
        ['Confidence', 'Hardcoded float (0.80, 0.84, dll)', 'Platt scaling pada LayoutLM logit + OCR confidence propagation', '+ Conformal prediction sets [2401.13744]', 'Interim adalah langkah besar. Conformal prediction untuk v2.'],
        ['Form Mapper', 'Rule-based (form_mapper.py)', 'Tetap rule-based + evaluasi akurasi per field', '+ ML classifier untuk field bermasalah jika perlu', 'Tetap rule-based. Jangan ML-kan yang sudah bekerja.'],
        ['Deployment', 'Background tasks / DB worker', 'ONNX INT8 + queue worker + single CPU server', '+ Auto-scale container + monitoring', 'Interim. Serverless hanya jika traffic memburuk.'],
    ]
    add_table(doc, decision_rows[0], decision_rows[1:])

    # 3.11 Kesimpulan & Roadmap
    doc.add_heading('3.11 Kesimpulan & Roadmap 3 Fase', level=2)

    doc.add_paragraph(
        'Berdasarkan seluruh bukti dari literature review, Certificate Autofill sebaiknya '
        'menggunakan pendekatan hybrid cascade: mempertahankan rule-based fast path dan '
        'form mapper yang sudah teruji, sambil secara bertahap mengganti regex extraction '
        'dengan fine-tuned LayoutLMv3-base (125M params) untuk field semantik. '
        'Confidence system perlu direformasi total — dari hardcoded float menjadi Platt scaling '
        'yang didukung propagasi OCR confidence per-karakter. Dengan target deployment '
        'CPU-only dan skala 25.000 mahasiswa, LayoutLMv3-base ONNX INT8 pada single server '
        'sudah mencukupi tanpa perlu infrastruktur GPU atau cloud LLM. Berikut roadmap '
        'implementasinya:'
    )

    phase_rows = [
        ['Fase', 'Timeline', 'Deliverables', 'Justifikasi Paper'],
        ['Fase 1: Foundation', '0-2 bulan', 'Propagate OCR confidence (rapidocr per-char); tambah layout detection RT-DETR; ganti confidence threshold (validation set, bukan 0.80); kumpulkan 200-500 sertifikat labeled.',
         '[2508.21693] line-level OCR, [2509.11720] layout detection, [2406.02354] uncertainty'],
        ['Fase 2: ML Extraction', '2-4 bulan', 'Fine-tune LayoutLMv3-base (LoRA CPU) di labeled dataset; implementasi 2-tier cascade (regex + LayoutLM); Platt scaling calibration; active learning loop.',
         '[2404.10848] LayoutLMv3, [2507.01806] LoRA CPU, [2410.01609] SynJAC, [2311.12436] isotonic regression'],
        ['Fase 3: Optimasi', '4-6 bulan', 'ONNX INT8 quantization; single-server deployment; evaluasi akurasi; jika perlu, upgrade ke Donut fallback; monitoring + retraining cycle.',
         '[2311.00502] INT4 CPU, [2505.06461] CPU vs GPU, [2607.07052] progressive crystallization'],
    ]
    add_table(doc, phase_rows[0], phase_rows[1:])

    doc.add_page_break()

    # ======================== 4. DAFTAR PUSTAKA ========================
    doc.add_heading('4. Daftar Pustaka', level=1)

    refs = [
        '[2304.12244] WizardLM: Empowering Large Pre-Trained Language Models to Follow Complex Instructions. 2023.',
        '[2305.00049] Prompt Consistency for Zero-Shot Task Generalization. 2022.',
        '[2305.00795] SelfDocSeg: A Self-Supervised Vision-Based Approach Towards Document Segmentation. 2023.',
        '[2305.03253] VicunaNER: Zero/Few-Shot Named Entity Recognition Using Vicuna. 2023.',
        '[2305.14450] An Empirical Study on Information Extraction Using Large Language Models. 2023.',
        '[2305.14975] Just Ask for Calibration: Strategies for Eliciting Calibrated Confidence Scores from Language Models. 2023.',
        '[2306.00526] Layout and Task Aware Instruction Prompt for Zero-Shot Document Image Question Answering. 2023.',
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
        '[2402.10612] Rowen: Adaptive Retrieval-Augmented Generation for Hallucination Mitigation in LLMs. 2024.',
        '[2403.02310] Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve. 2024.',
        '[2403.07553] The Future of Document Indexing: GPT and Donut Revolutionize Table of Content Processing. 2024.',
        '[2403.13369] Clinical Information Extraction for Low-Resource Languages with Few-Shot Learning. 2024.',
        '[2404.01462] OpenChemIE: An Information Extraction Toolkit for Chemistry Literature. 2024.',
        '[2404.05225] LayoutLLM: Layout Instruction Tuning with Large Language Models for Document Understanding. 2024.',
        '[2404.10848] A LayoutLMv3-Based Model for Enhanced Relation Extraction in Visually-Rich Documents. 2024.',
        '[2404.19329] End-to-End Information Extraction in Handwritten Documents: Understanding Paris Marriage Records. 2024.',
        '[2405.17533] PAE: LLM-Based Product Attribute Extraction for E-Commerce Fashion Trends. 2024.',
        '[2406.02354] Label-Wise Aleatoric and Epistemic Uncertainty Quantification. 2024.',
        '[2406.05348] Toward Reliable Ad-Hoc Scientific Information Extraction: A Case Study on Two Materials Datasets. 2024.',
        '[2406.06236] UnSupDLA: Towards Unsupervised Document Layout Analysis. 2024.',
        '[2410.01609] SynJAC: Synthetic-Data-Driven Joint-Granular Adaptation and Calibration for Domain Specific Scanned Document KIE. 2024.',
        '[2410.06615] QA-Calibration of Language Model Confidence Scores. 2024.',
        '[2410.21169] Document Parsing Unveiled: Techniques, Challenges, and Prospects for Structured Information Extraction. 2024.',
        '[2412.04504] Multi-Bin Batching for Increasing LLM Inference Throughput. 2024.',
        '[2412.14737] On Verbalized Confidence Scores for LLMs. 2024.',
        '[2501.00031] Distilling Large Language Models for Efficient Clinical Information Extraction. 2025.',
        '[2501.05497] Spatial Information Integration in Small Language Models for Document Layout Generation and Classification. 2025.',
        '[2502.11306] Smoothing Out Hallucinations: Mitigating LLM Hallucination with Smoothed Knowledge Distillation. 2025.',
        '[2502.12017] Scalable and Cost-Efficient ML Inference: Parallel Batch Processing with Serverless Functions. 2025.',
        '[2503.05488] KIEval: Evaluation Metric for Document Key Information Extraction. 2025.',
        '[2504.02871] Synthesized Annotation Guidelines Are Knowledge-Lite Boosters for Clinical Information Extraction. 2025.',
        '[2504.13359] Cost-of-Pass: An Economic Framework for Evaluating Language Models. 2025.',
        '[2505.06461] Challenging GPU Dominance: When CPUs Outperform for On-Device LLM Inference. 2025.',
        '[2505.13535] Information Extraction from Visually Rich Documents Using LLM-Based Organization. 2025.',
        '[2505.17125] NEXT-EVAL: Next Evaluation of Traditional and LLM Web Data Record Extraction. 2025.',
        '[2507.01806] LoRA Fine-Tuning Without GPUs: A CPU-Efficient Meta-Generation Framework for LLMs. 2025.',
        '[2508.06988] TADoc: Robust Time-Aware Document Image Dewarping. 2025.',
        '[2508.14557] Improving OCR Using Internal Document Redundancy. 2025.',
        '[2508.21693] Why Stop at Words? Unveiling the Bigger Picture Through Line-Level OCR. 2025.',
        '[2509.08381] Low-Resource Fine-Tuning for Multi-Task Structured Information Extraction with a Billion-Parameter Model. 2025.',
        '[2509.11720] Advanced Layout Analysis Models for Docling. 2025.',
        '[2509.18101] A Cost-Benefit Analysis of On-Premise Large Language Model Deployment. 2025.',
        '[2509.22906] Extract-0: A Specialized Language Model for Document Information Extraction. 2025.',
        '[2512.13031] Comprehensive Evaluation of Rule-Based, Machine Learning, and Deep Learning. 2025.',
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
    output_path = './docs/rangkuman_findings.docx'
    doc.save(output_path)
    print(f'Dokumen berhasil disimpan: {output_path}')
    return output_path


if __name__ == '__main__':
    build_document()
