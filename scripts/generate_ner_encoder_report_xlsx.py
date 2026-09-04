#!/usr/bin/env python3
"""Script untuk menghasilkan workbook Excel komparasi lengkap:
- Evaluasi komparasi pipeline & encoder NER (mDeBERTa, XLM-RoBERTa, IndoBERT, GLiNER v2.1, GLiNER2.5, Gemini, Composite v4.x)
- Spesifikasi & konfigurasi teknis fine-tuning encoder
- Statistik 5-fold cross validation & Bootstrap 1000x CI
- Uji ketahanan Out-of-Distribution (OOD)
- Analisis arsitektur Two-Stage Tesseract-to-Gemini vs Direct Multimodal
"""

import os
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

REPO_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_DIR / "docs" / "report"
OUTPUT_PATH = OUTPUT_DIR / "komparasi_ner_encoder_dan_pipeline.xlsx"

def build_excel_report():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Hapus sheet default

    # Palet Warna Profesional (Classic Navy & Slate)
    NAVY_DARK = "1B365D"      # Header utama
    NAVY_MEDIUM = "2E5B88"    # Subheader / Section header
    ICE_BLUE = "E8EEF5"       # Zebra row / Highlight
    LIGHT_GRAY = "F8FAFC"     # Zebra row
    ACCENT_GREEN = "D1E7DD"   # PASS / Win
    ACCENT_RED = "F8D7DA"     # Drop / Noise / Fail
    ACCENT_WARN = "FFF3CD"    # Warning / Experimental
    BORDER_GRAY = "CBD5E1"    # Garis sel

    font_title = Font(name="Arial", size=14, bold=True, color="FFFFFF")
    font_subtitle = Font(name="Arial", size=10, italic=True, color="FFFFFF")
    font_section = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    font_header = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    font_sub_header = Font(name="Arial", size=10, bold=True, color="1B365D")
    font_data = Font(name="Arial", size=9, color="000000")
    font_data_bold = Font(name="Arial", size=9, bold=True, color="000000")
    font_formula = Font(name="Arial", size=9, bold=True, color="000000")

    fill_title = PatternFill("solid", fgColor=NAVY_DARK)
    fill_section = PatternFill("solid", fgColor=NAVY_MEDIUM)
    fill_ice = PatternFill("solid", fgColor=ICE_BLUE)
    fill_gray = PatternFill("solid", fgColor=LIGHT_GRAY)
    fill_win = PatternFill("solid", fgColor=ACCENT_GREEN)
    fill_drop = PatternFill("solid", fgColor=ACCENT_RED)
    fill_warn = PatternFill("solid", fgColor=ACCENT_WARN)

    thin_border = Border(
        left=Side(style="thin", color=BORDER_GRAY),
        right=Side(style="thin", color=BORDER_GRAY),
        top=Side(style="thin", color=BORDER_GRAY),
        bottom=Side(style="thin", color=BORDER_GRAY),
    )
    header_border = Border(
        left=Side(style="thin", color="FFFFFF"),
        right=Side(style="thin", color="FFFFFF"),
        top=Side(style="medium", color=NAVY_DARK),
        bottom=Side(style="medium", color=NAVY_DARK),
    )

    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    # =========================================================================
    # SHEET 1: Ringkasan Komparasi
    # =========================================================================
    ws1 = wb.create_sheet(title="Ringkasan Komparasi")
    ws1.views.sheetView[0].showGridLines = True

    # Title Block
    ws1.merge_cells("A1:N1")
    ws1["A1"] = "KOMPARASI KINERJA PIPELINE & ENCODER NER SERTIFIKAT (74 DOKUMEN, GT V9)"
    ws1["A1"].font = font_title
    ws1["A1"].fill = fill_title
    ws1["A1"].alignment = align_center
    ws1.row_dimensions[1].height = 26

    ws1.merge_cells("A2:N2")
    ws1["A2"] = "Evaluasi Frozen Baseline Matcher v2 (Framework 5-Field: 310 Sel & All-Cells 6-Field: 444 Sel) | Tanggal Evaluasi: 2026-09-04"
    ws1["A2"].font = font_subtitle
    ws1["A2"].fill = fill_title
    ws1["A2"].alignment = align_center
    ws1.row_dimensions[2].height = 18

    # Table 1: Komparasi Utama
    headers_t1 = [
        "Metode / Model", "Kategori Arsitektur", "MACRO Exact", "MACRO Fuzzy",
        "95% CI Exact", "Nama Kegiatan", "Nomor Sertifikat", "Penyelenggara",
        "Tgl Mulai", "Tgl Selesai", "Tingkat (All-Cells)", "Waktu Proses (74 Cert)", "VRAM / Biaya", "Status Produksi / Evaluasi"
    ]
    ws1.row_dimensions[4].height = 28
    for col_idx, text in enumerate(headers_t1, start=1):
        cell = ws1.cell(row=4, column=col_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

    rows_t1 = [
        ["IndoBERT Pre-trained (indobert-ner-gold)", "Token Classification (Zero-Shot)", 0.1280, 0.2880, "[9.50%, 16.20%]", 0.1640, 0.0000, 0.1100, 0.2730, 0.0730, "N/A", "5.1 detik (0.07s/c)", "~2.5 GB", "Baseline Pre-trained (Off-the-shelf)"],
        ["IndoBERT Fine-Tuned Gagal (indobert-base-p1)", "Full Fine-Tuning (59 Sampel)", 0.0150, 0.0820, "N/A", 0.0270, 0.0000, 0.0140, 0.0360, 0.0000, "N/A", "~240 detik (5 ep)", "~3.5 GB", "Gagal (Catastrophic Forgetting)"],
        ["GLiNER2.5 Base (arXiv:2507.18546)", "Zero-Shot Boundary Extractor", 0.2871, 0.3871, "[23.64%, 34.39%]", 0.3108, 0.0385, 0.2027, 0.4545, 0.4364, "N/A", "3.9 detik (0.052s/c)", "~1.8 GB", "Zero-Shot Boundary (PASS)"],
        ["GLiNER2.5 Base Fine-Tuned", "Full Fine-Tuning Boundary", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "69.0 detik (Fold 1)", "~4.6 GB", "Gagal (FloatingPointError micro-batch)"],
        ["mDeBERTa-v3-base (86M)", "5-Fold CV Token Classif.", 0.3484, 0.5129, "[28.95%, 40.92%]", 0.2568, 0.5577, 0.2568, 0.3273, 0.4182, "N/A", "734 detik (~12.2m)", "4.08 GB", "Eksplorasi (PASS)"],
        ["GLiNER v2.1 Multilingual (urchade)", "Zero-Shot Span Bi-Encoder", 0.3548, 0.4645, "[30.10%, 41.31%]", 0.1622, 0.1346, 0.3649, 0.5818, 0.5818, "N/A", "5.7 detik (0.077s/c)", "~2.4 GB", "Zero-Shot Multi (PASS)"],
        ["XLM-RoBERTa-large (560M)", "5-Fold CV Token Classif.", 0.4355, 0.5548, "[37.17%, 50.00%]", 0.3514, 0.5962, 0.3784, 0.4545, 0.4545, "N/A", "794 detik (~13.2m)", "7.09 GB (Adafactor)", "Eksplorasi (PASS)"],
        ["IndoBERT-ner-gold Fine-Tuned (334M)", "5-Fold CV Token Classif.", 0.4452, 0.5710, "[38.59%, 50.82%]", 0.4324, 0.5769, 0.3649, 0.4909, 0.4000, "N/A", "700.1 detik (~11.7m)", "4.65 GB", "BEST TOKEN CLASSIFIER (PASS)"],
        ["GLiNER v2.1 Fine-Tuned (300M)", "5-Fold OOF Span Bi-Encoder", 0.5452, 0.6323, "[47.78%, 60.76%]", 0.5270, 0.5577, 0.5000, 0.5273, 0.6364, "N/A", "649.7 detik (~10.8m)", "3.76 GB", "Eksplorasi (OOF Selesai, OOD Fail)"],
        ["Direct Gemini 3.1 Flash Lite", "Two-Stage Tesseract-to-LLM", 0.6324, 0.7378, "[58.78%, 68.92%]", 0.6216, 0.5946, 0.5946, 0.6757, 0.6757, 0.6622, "100.6 detik (1.36s/c)", "Rp703 (~Rp9.50/c)", "PRODUKSI AKTIF (Opt A)"],
        ["Composite v4.x (Pure OCR)", "Pure 100% Tesseract OCR + Rules", 0.7710, 0.8516, "[72.10%, 81.80%]", 0.7600, 0.8947, 0.3600, 0.9000, 0.9000, 0.6847, "0 detik (Offline)", "0 GB (CPU Local)", "Baseline Pure OCR"],
        ["Combined v4.2 (Hybrid)", "Hybrid Layer + 3 Pillars & Crop", 0.8742, 0.9000, "[83.50%, 91.20%]", 0.7970, 0.9230, 0.6620, 0.9090, 0.9090, 0.7682, "0 detik (Offline)", "0 GB (CPU Local)", "Fallback Produksi"],
    ]

    for r_idx, row_data in enumerate(rows_t1, start=5):
        ws1.row_dimensions[r_idx].height = 20
        fill_current = fill_ice if r_idx % 2 == 1 else fill_gray
        if "PRODUKSI AKTIF" in str(row_data[-1]):
            fill_current = fill_win
        elif "Gagal" in str(row_data[-1]):
            fill_current = fill_drop
        elif "OOD Fail" in str(row_data[-1]):
            fill_current = fill_warn

        for c_idx, val in enumerate(row_data, start=1):
            cell = ws1.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_data_bold if c_idx in [1, 3, 4] else font_data
            cell.fill = fill_current
            cell.border = thin_border

            # Number format
            if isinstance(val, float):
                cell.number_format = "0.0%"
                cell.alignment = align_right
            elif c_idx in [1, 2, 5, 12, 13, 14]:
                cell.alignment = align_left if c_idx in [1, 2, 14] else align_center
            else:
                cell.alignment = align_center

    # Summary Stats row using formulas
    row_avg = 17
    ws1.row_dimensions[row_avg].height = 22
    ws1.cell(row=row_avg, column=1, value="Rata-rata Model Teruji").font = font_header
    ws1.cell(row=row_avg, column=1).fill = fill_title
    ws1.cell(row=row_avg, column=1).alignment = align_left
    ws1.cell(row=row_avg, column=1).border = thin_border

    ws1.cell(row=row_avg, column=2, value="Rata-rata Metrik").font = font_header
    ws1.cell(row=row_avg, column=2).fill = fill_title
    ws1.cell(row=row_avg, column=2).alignment = align_center
    ws1.cell(row=row_avg, column=2).border = thin_border

    for c in [3, 4]:
        col_letter = get_column_letter(c)
        cell = ws1.cell(row=row_avg, column=c, value=f"=AVERAGE({col_letter}5:{col_letter}16)")
        cell.font = font_header
        cell.fill = fill_title
        cell.alignment = align_right
        cell.border = thin_border
        cell.number_format = "0.0%"

    for c in range(5, 15):
        cell = ws1.cell(row=row_avg, column=c, value="")
        cell.fill = fill_title
        cell.border = thin_border

    # Section 2: Peningkatan Relatif vs Baseline NER v1
    ws1.cell(row=19, column=1, value="ANALISIS DELTA PERFORMANSI VS BASELINE PRE-TRAINED NER V1 (INDOBERT)").font = font_sub_header
    headers_t2 = ["Model Komparasi", "Baseline Exact", "Model Exact", "Peningkatan Mutlak (pp)", "Peningkatan Relatif (%)", "Kesimpulan Arsitektural"]
    ws1.row_dimensions[20].height = 24
    for c_idx, text in enumerate(headers_t2, start=1):
        cell = ws1.cell(row=20, column=c_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

    delta_rows = [
        ["IndoBERT Fine-Tuned Gagal (Phase v2)", 5, 6, "Anjlok -11.3pp akibat catastrophic forgetting pada 59 sampel dan ketiadaan weighted loss."],
        ["GLiNER2.5 Base (arXiv:2507.18546)", 5, 7, "Zero-shot boundary extractor melompat +15.91pp; nama kegiatan exact mencapai 31.1%."],
        ["mDeBERTa-v3-base (86M)", 5, 9, "Peningkatan substansial (+22.04pp) pada recall entitas non-O via FP32 & soft-capping."],
        ["GLiNER v2.1 Multilingual (urchade)", 5, 10, "Zero-shot multilingual melompat +22.68pp; tanggal 58.2% tapi noise OCR ekstrem drop tajam."],
        ["XLM-RoBERTa-large (560M)", 5, 11, "Model 560M melompat +30.75pp; representasi BPE multilingual sangat kuat."],
        ["IndoBERT-ner-gold Fine-Tuned (334M)", 5, 12, "BEST TOKEN CLASSIFIER (+31.72pp vs pre-trained, +0.97pp vs XLM-RoBERTa-large, kegiatan 43.2%)."],
        ["GLiNER v2.1 Fine-Tuned (300M)", 5, 13, "BEST ENCODER OVERALL (+41.72pp vs baseline, exact 54.52%), namun OOD robustness gate FAIL (-6.36pp mutasi)."],
        ["Direct Gemini 3.1 Flash Lite", 5, 14, "LLM murni melampaui seluruh encoder lokal tanpa memerlukan fine-tuning."],
        ["Composite v4.x (Pure OCR Rules)", 5, 15, "Rule deterministik offline tetap paling unggul pada domain penanggalan & nomor."],
        ["Combined v4.2 (Hybrid Pipeline)", 5, 16, "Pipeline komposit offline terbaik, unggul +74.62pp dibanding baseline NER v1."],
    ]

    for idx, (label, base_r, model_r, notes) in enumerate(delta_rows, start=21):
        ws1.row_dimensions[idx].height = 20
        c1 = ws1.cell(row=idx, column=1, value=label)
        c2 = ws1.cell(row=idx, column=2, value=f"=C{base_r}")
        c3 = ws1.cell(row=idx, column=3, value=f"=C{model_r}")
        c4 = ws1.cell(row=idx, column=4, value=f"=C{idx}-B{idx}")
        c5 = ws1.cell(row=idx, column=5, value=f"=(C{idx}-B{idx})/B{idx}")
        c6 = ws1.cell(row=idx, column=6, value=notes)

        for c in [c1, c2, c3, c4, c5, c6]:
            c.border = thin_border
            c.fill = fill_ice if idx % 2 == 1 else fill_gray

        c1.alignment = align_left; c1.font = font_data_bold
        c2.alignment = align_right; c2.number_format = "0.0%"; c2.font = font_data
        c3.alignment = align_right; c3.number_format = "0.0%"; c3.font = font_data
        c4.alignment = align_right; c4.number_format = "+0.0%pp;-0.0%pp;0.0%pp"; c4.font = font_formula
        c5.alignment = align_right; c5.number_format = "+0.0%;-0.0%;0.0%"; c5.font = font_formula
        c6.alignment = align_left; c6.font = font_data

    # =========================================================================
    # SHEET 2: Konfigurasi Fine-Tuning
    # =========================================================================
    ws2 = wb.create_sheet(title="Konfigurasi Fine-Tuning")
    ws2.views.sheetView[0].showGridLines = True

    ws2.merge_cells("A1:G1")
    ws2["A1"] = "SPESIFIKASI TEKNIS & KONFIGURASI HYPERPARAMETER ENCODER (NER-ENCODER-001 & NER-GLINER-002)"
    ws2["A1"].font = font_title
    ws2["A1"].fill = fill_title
    ws2["A1"].alignment = align_center
    ws2.row_dimensions[1].height = 26

    ws2.merge_cells("A2:G2")
    ws2["A2"] = "Perbandingan Parameter Pelatihan & Stabilisasi Numerik untuk IndoBERT, mDeBERTa, XLM-RoBERTa, GLiNER v2.1, dan GLiNER2.5"
    ws2["A2"].font = font_subtitle
    ws2["A2"].fill = fill_title
    ws2["A2"].alignment = align_center
    ws2.row_dimensions[2].height = 18

    headers_t3 = [
        "Parameter / Spesifikasi",
        "treamyracle/indobert-ner-gold",
        "microsoft/mdeberta-v3-base",
        "facebookai/xlm-roberta-large",
        "urchade/gliner_multi-v2.1",
        "fastino/gliner2.5-base-v1",
        "Rasional & Detail Desain Arsitektural"
    ]
    ws2.row_dimensions[4].height = 26
    for c_idx, text in enumerate(headers_t3, start=1):
        cell = ws2.cell(row=4, column=c_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

    configs = [
        ["Model Checkpoint", "treamyracle/indobert-ner-gold", "microsoft/mdeberta-v3-base", "facebookai/xlm-roberta-large", "urchade/gliner_multi-v2.1", "fastino/gliner2.5-base-v1", "Bobot resmi dari Hugging Face Hub."],
        ["Jumlah Parameter", "334 Juta Parameter", "86 Juta Parameter", "560 Juta Parameter", "~300 Juta Parameter", "193.5 Juta Parameter", "GLiNER v2.1 memakai backbone mDeBERTa-v3-base + projection; GLiNER2.5 memakai boundary extractor."],
        ["Arsitektur Dasar", "BERT-large (Token Clf)", "DeBERTa-v2 (Disentangled)", "RoBERTa (Multilingual)", "Span Bi-Encoder (GLiNER)", "Boundary Extractor (GLiNER2)", "Token classification vs open-vocabulary span/boundary extraction."],
        ["Tokenizer & Vocab", "BertTokenizerFast (32k)", "DeBERTaV2TokenizerFast (250k)", "XLMRobertaTokenizerFast (250k)", "DeBERTaV2TokenizerFast (250k)", "DeBERTaV2TokenizerFast (250k)", "IndoBERT monolingual Indonesia vs model-model multilingual lainnya."],
        ["Skema Validasi", "5-Fold Stratified CV", "5-Fold Stratified CV", "5-Fold Stratified CV", "5-Fold Stratified CV", "5-Fold Stratified CV", "Identik 100%: stratified berdasarkan kelengkapan field 74 dokumen."],
        ["Loss Function", "Weighted Cross Entropy", "Weighted Cross Entropy", "Weighted Cross Entropy", "Focal Span Loss (native)", "Boundary Proposal Loss", "Penyeimbang ketimpangan kelas entitas vs background token/span."],
        ["Optimizer", "Adafactor (scale=False)", "Adafactor (scale=False)", "Adafactor (scale=False)", "Adafactor (scale=False)", "AdamW (native 2-group)", "GLiNER2.5 mengunci trainer pada AdamW dua kelompok."],
        ["Learning Rate", "2.0e-5", "2.0e-5", "2.0e-5", "2.0e-5", "2.0e-5", "Learning rate standar fine-tuning transformer."],
        ["Weight Decay", "0.01", "0.01", "0.01", "0.01", "0.01", "Regularisasi L2 standar untuk mencegah overfitting."],
        ["Batch Size (Per Device)", "1", "1", "1", "1", "1", "Menghindari lonjakan memori aktivasi token pada GPU 8GB."],
        ["Gradient Accumulation", "8 langkah", "8 langkah", "8 langkah", "8 langkah", "8 langkah", "Effective Batch Size = 8."],
        ["Effective Batch Size", "8 dokumen", "8 dokumen", "8 dokumen", "8 dokumen", "8 dokumen", "Ukuran batch efektif yang stabil untuk optimasi gradien."],
        ["Total Epoch", "10 Epoch", "10 Epoch", "10 Epoch", "10 Epoch", "10 Epoch", "10 epoch per fold."],
        ["Presisi Bobot (Master)", "torch.float32", "torch.float32", "torch.float32", "torch.float32", "torch.float32", "Stabilitas master weight FP32."],
        ["Presisi Autocast", "bfloat16 (autocast)", "bfloat16 (autocast)", "bfloat16 (autocast)", "bfloat16 (autocast)", "bfloat16 (autocast)", "Didukung native oleh arsitektur GPU RTX 5050."],
        ["Gradient Checkpointing", "Aktif", "Aktif", "Aktif", "Aktif", "Aktif", "Memangkas VRAM aktivasi ~60%."],
        ["Max Sequence Length", "512 Token", "512 Token", "512 Token", "512 Token (max_width=64)", "512 Token", "Batas konteks maksimum."],
        ["Sliding Window Stride", "64 Token", "64 Token", "64 Token", "64 Token", "64 Token", "Overlap jendela sliding agar token tidak terpotong."],
        ["Hasil Sanity Overfit", "96.0% (24/25 token)", "100.0% (25/25 token)", "100.0% (25/25 token)", "75.0% (6/8 span, FAIL gate)", "N/A (Skipped)", "GLiNER v2.1 gagal gate sanity (6/8 span); GLiNER2.5 diskip."],
        ["Total Waktu Latih (5 Fold)", "700.1 detik (~11.7m)", "734 detik (~12.2m)", "794 detik (~13.2m)", "649.7 detik (~10.8m)", "69.0 detik (Fold 1 abort)", "GLiNER v2.1 tercepat per fold; GLiNER2.5 gagal di epoch 4 fold 1."],
        ["Puncak Konsumsi VRAM", "4.65 GB", "4.08 GB", "7.09 GB", "3.76 GB", "4.65 GB", "GLiNER v2.1 paling hemat VRAM (3.76 GB) berkat span bi-encoder."],
        ["Status Eksekusi OOF", "PASS (100% Selesai)", "PASS (100% Selesai)", "PASS (100% Selesai)", "OOF Selesai (OOD Fail)", "FAIL (FloatingPointError)", "GLiNER v2.1 menyelesaikan 5 fold OOF; GLiNER2.5 divergen di micro-batch."]
    ]

    for r_idx, row_data in enumerate(configs, start=5):
        ws2.row_dimensions[r_idx].height = 20
        fill_curr = fill_ice if r_idx % 2 == 1 else fill_gray
        for c_idx, val in enumerate(row_data, start=1):
            cell = ws2.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_data_bold if c_idx == 1 else font_data
            cell.fill = fill_curr
            cell.border = thin_border
            cell.alignment = align_left if c_idx in [1, 7] else align_center

    # Section 2 di Sheet 2: Analisis Mendalam Kegagalan Fine-Tune
    ws2.cell(row=30, column=1, value="2. Analisis Mendalam: Evaluasi Kegagalan Fine-Tuning (IndoBERT Phase v2 & GLiNER2.5)").font = font_sub_header
    headers_t4 = [
        "Dimensi Arsitektural / Faktor",
        "IndoBERT Fine-Tuned (Phase v2)",
        "GLiNER2.5 Base Fine-Tuned (NER-GLINER-002)",
        "Akar Masalah Numerik / Pelatihan",
        "Pelajaran Rekayasa & Solusi Mitigasi"
    ]
    ws2.row_dimensions[31].height = 24
    for c_idx, text in enumerate(headers_t4, start=1):
        cell = ws2.cell(row=31, column=c_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

    failure_analysis = [
        [
            "Checkpoint & Loss Function",
            "indobenchmark/indobert-base-p1 dengan Cross-Entropy polos tanpa pembobotan.",
            "fastino/gliner2.5-base-v1 dengan boundary/proposal loss native ExtractorTrainer.",
            "IndoBERT: 92% token 'O' menenggelamkan gradien entitas; GLiNER2.5: proposal logit menghasilkan loss non-finite (NaN/Inf) pada 8 micro-batch.",
            "IndoBERT butuh pre-trained NER gold + weighted loss; GLiNER2.5 butuh clipping logit proposal atau gradient scaling lebih ketat."
        ],
        [
            "Stabilitas Numerik & Optimizer",
            "AdamW standar tanpa gradient clipping atau memory checkpointing.",
            "AdamW native 2-group dengan strict_training=True melempar FloatingPointError.",
            "Micro-batch loss non-finite otomatis zeroed oleh trainer, memicu pengecekan delayed counter dan menghentikan proses.",
            "GLiNER v2.1 dengan Adafactor terbukti jauh lebih stabil secara numerik dibanding AdamW native GLiNER2.5 pada dataset kecil."
        ],
        [
            "Generalisasi Out-of-Distribution",
            "Model collapse: F1=0.015, memprediksi seluruh token sebagai 'O'.",
            "Belum mencapai tahap OOD karena pelatihan terhenti di Fold 1.",
            "Catastrophic forgetting pada 59 sampel latih akibat parameter dibuka 100% tanpa regularisasi memadai.",
            "GLiNER v2.1 OOF selesai (54.52%), namun drop -6.36pp mutasi membuktikan fine-tuning domain spesifik mengikis ketahanan zero-shot."
        ],
        [
            "Rekomendasi Deployment Produksi",
            "Ditinggalkan permanen (closed di ledger).",
            "Ditinggalkan untuk fine-tuning; zero-shot tetap dapat dipakai bila diperlukan.",
            "Kedua model fine-tuning gagal memenuhi standar keandalan produksi 100% bebas intervensi.",
            "Arsitektur Two-Stage Tesseract-to-Gemini (Option A) tetap menjadi opsi produksi terbaik (63.24% exact, deterministik, stabil)."
        ]
    ]

    for r_idx, r_data in enumerate(failure_analysis, start=32):
        ws2.row_dimensions[r_idx].height = 36
        fill_curr = fill_ice if r_idx % 2 == 1 else fill_gray
        for c_idx, val in enumerate(r_data, start=1):
            cell = ws2.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_data_bold if c_idx == 1 else font_data
            cell.fill = fill_curr
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

    # =========================================================================
    # SHEET 3: Detail Per-Fold & Statistik
    # =========================================================================
    ws3 = wb.create_sheet(title="Detail Per-Fold & Statistik")
    ws3.views.sheetView[0].showGridLines = True

    ws3.merge_cells("A1:K1")
    ws3["A1"] = "DISTRIBUSI METRIK PER-FOLD & RESAMPLING BOOTSTRAP 1000X"
    ws3["A1"].font = font_title
    ws3["A1"].fill = fill_title
    ws3["A1"].alignment = align_center
    ws3.row_dimensions[1].height = 26

    headers_folds = ["Fold", "Train Docs", "Val Docs", "Durasi (s)", "Nama Kegiatan", "Nomor", "Penyelenggara", "Tgl Mulai", "Tgl Selesai", "MACRO Exact", "MACRO Fuzzy"]

    # Table 1: mDeBERTa
    ws3.cell(row=3, column=1, value="1. Evaluasi Per-Fold: microsoft/mdeberta-v3-base (86M)").font = font_sub_header
    ws3.row_dimensions[4].height = 24
    for c_idx, text in enumerate(headers_folds, start=1):
        cell = ws3.cell(row=4, column=c_idx, value=text)
        cell.font = font_header; cell.fill = fill_section; cell.alignment = align_center; cell.border = header_border

    mdeberta_folds = [
        [1, 51, 23, 136.8, 0.1739, 0.5294, 0.1739, 0.2632, 0.4211, 0.2927, 0.5366],
        [2, 59, 15, 142.1, 0.3333, 0.6000, 0.3333, 0.3636, 0.4545, 0.4032, 0.5161],
        [3, 59, 15, 139.5, 0.2667, 0.5556, 0.2667, 0.3000, 0.4000, 0.3448, 0.5000],
        [4, 59, 15, 145.3, 0.3333, 0.5556, 0.3333, 0.4000, 0.4000, 0.3966, 0.5000],
        [5, 69, 6, 170.5, 0.1667, 0.5714, 0.1667, 0.3000, 0.4000, 0.3077, 0.5128],
    ]

    for r_idx, r_data in enumerate(mdeberta_folds, start=5):
        ws3.row_dimensions[r_idx].height = 20
        fill_curr = fill_ice if r_idx % 2 == 1 else fill_gray
        for c_idx, val in enumerate(r_data, start=1):
            cell = ws3.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_data; cell.fill = fill_curr; cell.border = thin_border
            if isinstance(val, float) and c_idx >= 5:
                cell.number_format = "0.0%"; cell.alignment = align_right
            elif c_idx == 4:
                cell.number_format = "0.0"; cell.alignment = align_right
            else:
                cell.alignment = align_center

    row_avg_m = 10
    ws3.row_dimensions[row_avg_m].height = 22
    ws3.cell(row=row_avg_m, column=1, value="Rata-rata OOF").font = font_header
    ws3.cell(row=row_avg_m, column=1).fill = fill_title; ws3.cell(row=row_avg_m, column=1).border = thin_border
    ws3.cell(row=row_avg_m, column=2, value="=SUM(B5:B9)/5").font = font_header; ws3.cell(row=row_avg_m, column=2).fill = fill_title; ws3.cell(row=row_avg_m, column=2).alignment = align_center; ws3.cell(row=row_avg_m, column=2).number_format = "0"
    ws3.cell(row=row_avg_m, column=3, value="=SUM(C5:C9)").font = font_header; ws3.cell(row=row_avg_m, column=3).fill = fill_title; ws3.cell(row=row_avg_m, column=3).alignment = align_center; ws3.cell(row=row_avg_m, column=3).number_format = "0"
    ws3.cell(row=row_avg_m, column=4, value="=SUM(D5:D9)").font = font_header; ws3.cell(row=row_avg_m, column=4).fill = fill_title; ws3.cell(row=row_avg_m, column=4).alignment = align_right; ws3.cell(row=row_avg_m, column=4).number_format = "0.0s"
    for col in range(5, 12):
        col_letter = get_column_letter(col)
        cell = ws3.cell(row=row_avg_m, column=col, value=f"=AVERAGE({col_letter}5:{col_letter}9)")
        cell.font = font_header; cell.fill = fill_title; cell.alignment = align_right; cell.border = thin_border; cell.number_format = "0.0%"

    # Table 2: XLM-RoBERTa
    ws3.cell(row=12, column=1, value="2. Evaluasi Per-Fold: facebookai/xlm-roberta-large (560M)").font = font_sub_header
    ws3.row_dimensions[13].height = 24
    for c_idx, text in enumerate(headers_folds, start=1):
        cell = ws3.cell(row=13, column=c_idx, value=text)
        cell.font = font_header; cell.fill = fill_section; cell.alignment = align_center; cell.border = header_border

    xlmr_folds = [
        [1, 51, 23, 129.9, 0.2609, 0.5882, 0.3043, 0.4737, 0.5789, 0.4268, 0.5610],
        [2, 59, 15, 161.4, 0.4000, 0.6000, 0.4667, 0.4545, 0.4545, 0.4677, 0.5484],
        [3, 59, 15, 164.2, 0.4000, 0.6667, 0.4000, 0.5000, 0.4000, 0.4655, 0.5690],
        [4, 59, 15, 165.8, 0.4000, 0.5556, 0.4000, 0.4000, 0.4000, 0.4310, 0.5345],
        [5, 69, 6, 173.3, 0.3333, 0.5714, 0.3333, 0.4000, 0.4000, 0.3846, 0.5385],
    ]

    for r_idx, r_data in enumerate(xlmr_folds, start=14):
        ws3.row_dimensions[r_idx].height = 20
        fill_curr = fill_ice if r_idx % 2 == 1 else fill_gray
        for c_idx, val in enumerate(r_data, start=1):
            cell = ws3.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_data; cell.fill = fill_curr; cell.border = thin_border
            if isinstance(val, float) and c_idx >= 5:
                cell.number_format = "0.0%"; cell.alignment = align_right
            elif c_idx == 4:
                cell.number_format = "0.0"; cell.alignment = align_right
            else:
                cell.alignment = align_center

    row_avg_x = 19
    ws3.row_dimensions[row_avg_x].height = 22
    ws3.cell(row=row_avg_x, column=1, value="Rata-rata OOF").font = font_header
    ws3.cell(row=row_avg_x, column=1).fill = fill_title; ws3.cell(row=row_avg_x, column=1).border = thin_border
    ws3.cell(row=row_avg_x, column=2, value="=SUM(B14:B18)/5").font = font_header; ws3.cell(row=row_avg_x, column=2).fill = fill_title; ws3.cell(row=row_avg_x, column=2).alignment = align_center; ws3.cell(row=row_avg_x, column=2).number_format = "0"
    ws3.cell(row=row_avg_x, column=3, value="=SUM(C14:C18)").font = font_header; ws3.cell(row=row_avg_x, column=3).fill = fill_title; ws3.cell(row=row_avg_x, column=3).alignment = align_center; ws3.cell(row=row_avg_x, column=3).number_format = "0"
    ws3.cell(row=row_avg_x, column=4, value="=SUM(D14:D18)").font = font_header; ws3.cell(row=row_avg_x, column=4).fill = fill_title; ws3.cell(row=row_avg_x, column=4).alignment = align_right; ws3.cell(row=row_avg_x, column=4).number_format = "0.0s"
    for col in range(5, 12):
        col_letter = get_column_letter(col)
        cell = ws3.cell(row=row_avg_x, column=col, value=f"=AVERAGE({col_letter}14:{col_letter}18)")
        cell.font = font_header; cell.fill = fill_title; cell.alignment = align_right; cell.border = thin_border; cell.number_format = "0.0%"

    # Table 3: IndoBERT-ner-gold (334M)
    ws3.cell(row=21, column=1, value="3. Evaluasi Per-Fold: treamyracle/indobert-ner-gold (334M)").font = font_sub_header
    ws3.row_dimensions[22].height = 24
    for c_idx, text in enumerate(headers_folds, start=1):
        cell = ws3.cell(row=22, column=c_idx, value=text)
        cell.font = font_header; cell.fill = fill_section; cell.alignment = align_center; cell.border = header_border

    indobert_folds = [
        [1, 51, 23, 114.0, 0.4348, 0.5294, 0.3043, 0.4737, 0.4737, 0.4356, 0.5545],
        [2, 53, 21, 118.5, 0.5238, 0.5000, 0.4286, 0.5000, 0.3571, 0.4643, 0.5714],
        [3, 59, 15, 134.2, 0.2000, 0.8000, 0.2000, 0.4167, 0.2500, 0.3438, 0.5156],
        [4, 64, 10, 140.3, 0.5000, 0.4286, 0.5000, 0.8000, 0.6000, 0.5405, 0.6757],
        [5, 69, 5, 161.2, 0.6000, 0.7500, 0.6000, 0.4000, 0.4000, 0.5417, 0.6250],
    ]

    for r_idx, r_data in enumerate(indobert_folds, start=23):
        ws3.row_dimensions[r_idx].height = 20
        fill_curr = fill_ice if r_idx % 2 == 1 else fill_gray
        for c_idx, val in enumerate(r_data, start=1):
            cell = ws3.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_data; cell.fill = fill_curr; cell.border = thin_border
            if isinstance(val, float) and c_idx >= 5:
                cell.number_format = "0.0%"; cell.alignment = align_right
            elif c_idx == 4:
                cell.number_format = "0.0"; cell.alignment = align_right
            else:
                cell.alignment = align_center

    row_avg_i = 28
    ws3.row_dimensions[row_avg_i].height = 22
    ws3.cell(row=row_avg_i, column=1, value="Rata-rata OOF").font = font_header
    ws3.cell(row=row_avg_i, column=1).fill = fill_title; ws3.cell(row=row_avg_i, column=1).border = thin_border
    ws3.cell(row=row_avg_i, column=2, value="=SUM(B23:B27)/5").font = font_header; ws3.cell(row=row_avg_i, column=2).fill = fill_title; ws3.cell(row=row_avg_i, column=2).alignment = align_center; ws3.cell(row=row_avg_i, column=2).number_format = "0"
    ws3.cell(row=row_avg_i, column=3, value="=SUM(C23:C27)").font = font_header; ws3.cell(row=row_avg_i, column=3).fill = fill_title; ws3.cell(row=row_avg_i, column=3).alignment = align_center; ws3.cell(row=row_avg_i, column=3).number_format = "0"
    ws3.cell(row=row_avg_i, column=4, value="=SUM(D23:D27)").font = font_header; ws3.cell(row=row_avg_i, column=4).fill = fill_title; ws3.cell(row=row_avg_i, column=4).alignment = align_right; ws3.cell(row=row_avg_i, column=4).number_format = "0.0s"
    for col in range(5, 12):
        col_letter = get_column_letter(col)
        cell = ws3.cell(row=row_avg_i, column=col, value=f"=AVERAGE({col_letter}23:{col_letter}27)")
        cell.font = font_header; cell.fill = fill_title; cell.alignment = align_right; cell.border = thin_border; cell.number_format = "0.0%"

    # Table 4: GLiNER v2.1 Multilingual (300M)
    ws3.cell(row=30, column=1, value="4. Evaluasi Per-Fold: urchade/gliner_multi-v2.1 (300M) — BEST ENCODER OVERALL").font = font_sub_header
    ws3.row_dimensions[31].height = 24
    for c_idx, text in enumerate(headers_folds, start=1):
        cell = ws3.cell(row=31, column=c_idx, value=text)
        cell.font = font_header; cell.fill = fill_section; cell.alignment = align_center; cell.border = header_border

    gliner_folds = [
        [1, 51, 23, 133.2, 0.5217, 0.6471, 0.5652, 0.4737, 0.6316, 0.5644, 0.6436],
        [2, 53, 21, 136.1, 0.5714, 0.4286, 0.4762, 0.5714, 0.6429, 0.5357, 0.6429],
        [3, 59, 15, 137.9, 0.5333, 0.6000, 0.4000, 0.5000, 0.6667, 0.5312, 0.6250],
        [4, 64, 10, 142.9, 0.4000, 0.7143, 0.4000, 0.8000, 0.8000, 0.5676, 0.6757],
        [5, 69, 5, 151.1, 0.6000, 0.2500, 0.8000, 0.4000, 0.4000, 0.5000, 0.5000],
    ]

    for r_idx, r_data in enumerate(gliner_folds, start=32):
        ws3.row_dimensions[r_idx].height = 20
        fill_curr = fill_ice if r_idx % 2 == 1 else fill_gray
        for c_idx, val in enumerate(r_data, start=1):
            cell = ws3.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_data; cell.fill = fill_curr; cell.border = thin_border
            if isinstance(val, float) and c_idx >= 5:
                cell.number_format = "0.0%"; cell.alignment = align_right
            elif c_idx == 4:
                cell.number_format = "0.0"; cell.alignment = align_right
            else:
                cell.alignment = align_center

    row_avg_g = 37
    ws3.row_dimensions[row_avg_g].height = 22
    ws3.cell(row=row_avg_g, column=1, value="Rata-rata OOF").font = font_header
    ws3.cell(row=row_avg_g, column=1).fill = fill_title; ws3.cell(row=row_avg_g, column=1).border = thin_border
    ws3.cell(row=row_avg_g, column=2, value="=SUM(B32:B36)/5").font = font_header; ws3.cell(row=row_avg_g, column=2).fill = fill_title; ws3.cell(row=row_avg_g, column=2).alignment = align_center; ws3.cell(row=row_avg_g, column=2).number_format = "0"
    ws3.cell(row=row_avg_g, column=3, value="=SUM(C32:C36)").font = font_header; ws3.cell(row=row_avg_g, column=3).fill = fill_title; ws3.cell(row=row_avg_g, column=3).alignment = align_center; ws3.cell(row=row_avg_g, column=3).number_format = "0"
    ws3.cell(row=row_avg_g, column=4, value="=SUM(D32:D36)").font = font_header; ws3.cell(row=row_avg_g, column=4).fill = fill_title; ws3.cell(row=row_avg_g, column=4).alignment = align_right; ws3.cell(row=row_avg_g, column=4).number_format = "0.0s"
    for col in range(5, 12):
        col_letter = get_column_letter(col)
        cell = ws3.cell(row=row_avg_g, column=col, value=f"=AVERAGE({col_letter}32:{col_letter}36)")
        cell.font = font_header; cell.fill = fill_title; cell.alignment = align_right; cell.border = thin_border; cell.number_format = "0.0%"

    # Table 5: Bootstrap CI
    ws3.cell(row=39, column=1, value="5. Validasi Statistik Bootstrap 1000x Resampling (Exact Macro)").font = font_sub_header
    headers_ci = ["Model Evaluasi", "Sampel Dokumen", "Mean Bootstrap", "Batas Bawah (2.5%)", "Batas Atas (97.5%)", "Rentang CI 95% (Width)", "Stabilitas Estimasi"]
    ws3.row_dimensions[40].height = 24
    for c_idx, text in enumerate(headers_ci, start=1):
        cell = ws3.cell(row=40, column=c_idx, value=text)
        cell.font = font_header; cell.fill = fill_section; cell.alignment = align_center; cell.border = header_border

    ci_data = [
        ["mDeBERTa-v3-base (86M)", 74, 0.3478, 0.2895, 0.4092, "Sangat Stabil (Normal Distribution)"],
        ["XLM-RoBERTa-large (560M)", 74, 0.4357, 0.3717, 0.5000, "Sangat Stabil (Normal Distribution)"],
        ["IndoBERT-ner-gold (334M)", 74, 0.4457, 0.3859, 0.5082, "BEST TOKEN CLASSIFIER (95% CI: 38.6% - 50.8%)"],
        ["GLiNER v2.1 Fine-Tuned (300M)", 74, 0.5443, 0.4778, 0.6076, "BEST ENCODER (95% CI Tertinggi: 47.8% - 60.8%)"],
    ]

    for idx, (m_name, n_doc, mean_v, low_v, high_v, notes) in enumerate(ci_data, start=41):
        ws3.row_dimensions[idx].height = 20
        c1 = ws3.cell(row=idx, column=1, value=m_name); c1.font = font_data_bold; c1.alignment = align_left
        c2 = ws3.cell(row=idx, column=2, value=n_doc); c2.alignment = align_center; c2.number_format = "0"
        c3 = ws3.cell(row=idx, column=3, value=mean_v); c3.alignment = align_right; c3.number_format = "0.0%"
        c4 = ws3.cell(row=idx, column=4, value=low_v); c4.alignment = align_right; c4.number_format = "0.0%"
        c5 = ws3.cell(row=idx, column=5, value=high_v); c5.alignment = align_right; c5.number_format = "0.0%"
        c6 = ws3.cell(row=idx, column=6, value=f"=E{idx}-D{idx}"); c6.alignment = align_right; c6.number_format = "0.0%pp"; c6.font = font_formula
        c7 = ws3.cell(row=idx, column=7, value=notes); c7.alignment = align_left; c7.font = font_data

        for c in [c1, c2, c3, c4, c5, c6, c7]:
            c.border = thin_border
            c.fill = fill_ice if idx % 2 == 1 else fill_gray

    # =========================================================================
    # SHEET 4: Uji Ketahanan OOD
    # =========================================================================
    ws4 = wb.create_sheet(title="Uji Ketahanan OOD")
    ws4.views.sheetView[0].showGridLines = True

    ws4.merge_cells("A1:Q1")
    ws4["A1"] = "UJI KETAHANAN OUT-OF-DISTRIBUTION (OOD STRESS TESTING PADA 236 SEL BEBAS-INSTITUSI)"
    ws4["A1"].font = font_title
    ws4["A1"].fill = fill_title
    ws4["A1"].alignment = align_center
    ws4.row_dimensions[1].height = 26

    ws4.merge_cells("A2:Q2")
    ws4["A2"] = "Ketahanan Field Tanggal, Nomor, dan Kegiatan terhadap Mutasi Entitas & Perturbasi Noise Karakter OCR"
    ws4["A2"].font = font_subtitle
    ws4["A2"].fill = fill_title
    ws4["A2"].alignment = align_center
    ws4.row_dimensions[2].height = 18

    headers_ood = [
        "Kondisi Uji Gangguan", "Jumlah Sel",
        "Akurasi GLiNER v2.1 (Zero-Shot)", "Drop GLiNER v2.1 (ZS)",
        "Akurasi GLiNER v2.1 (Fine-Tuned)", "Drop GLiNER v2.1 (FT)",
        "Akurasi GLiNER2.5 (Zero-Shot)", "Drop GLiNER2.5 (ZS)",
        "Akurasi IndoBERT (FT)", "Drop IndoBERT",
        "Akurasi mDeBERTa (FT)", "Drop mDeBERTa",
        "Akurasi XLM-RoBERTa (FT)", "Drop XLM-RoBERTa",
        "Akurasi Composite v4.x", "Drop Composite v4.x",
        "Toleransi & Evaluasi Robustness Gate (Lapis 2)"
    ]
    ws4.row_dimensions[4].height = 26
    for c_idx, text in enumerate(headers_ood, start=1):
        cell = ws4.cell(row=4, column=c_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

    ood_table = [
        ["Clean Baseline (Tanpa Noise)", 236, 0.3517, 0.5593, 0.2839, 0.4703, 0.3771, 0.4534, 0.8800, "Kondisi teks masukan OCR standar (Baseline Lapis 2)"],
        ["Mutasi Entitas (UNAIR->UNS dll)", 236, 0.3517, 0.4958, 0.2797, 0.3983, 0.3051, 0.3771, 0.8060, "GLiNER FT drop -6.36pp (FAIL batas <=2.0pp); adaptasi domain mengurangi ketahanan mutasi entitas"],
        ["Perturbasi Noise OCR 10%", 236, 0.2712, 0.3686, 0.2288, 0.3051, 0.2500, 0.2924, 0.7990, "Simulasi kebingungan karakter OCR 5<->S, 8<->B, 0<->O, 1<->I; GLiNER FT drop -19.07pp"],
        ["Perturbasi Noise OCR 25%", 236, 0.1780, 0.2754, 0.1525, 0.1822, 0.2034, 0.1949, 0.6980, "Tingkat noise OCR sedang pada dokumen buram/pindaian miring; drop -28.39pp"],
        ["Perturbasi Noise OCR 50%", 236, 0.1017, 0.1356, 0.0720, 0.0890, 0.1017, 0.1229, 0.5410, "Tingkat noise OCR ekstrem pada pindaian sangat rusak; drop -42.37pp"],
    ]

    for idx, (cond, n_cells, g1_zs, g1_ft, g2_zs, indob_acc, mdeb_acc, xlm_acc, comp_acc, notes) in enumerate(ood_table, start=5):
        ws4.row_dimensions[idx].height = 20
        c1 = ws4.cell(row=idx, column=1, value=cond); c1.font = font_data_bold; c1.alignment = align_left
        c2 = ws4.cell(row=idx, column=2, value=n_cells); c2.alignment = align_center; c2.number_format = "0"
        c3 = ws4.cell(row=idx, column=3, value=g1_zs); c3.alignment = align_right; c3.number_format = "0.0%"
        c4 = ws4.cell(row=idx, column=4, value=f"=C{idx}-C$5"); c4.alignment = align_right; c4.number_format = "-0.0%pp;+0.0%pp;0.0%pp"; c4.font = font_formula
        c5 = ws4.cell(row=idx, column=5, value=g1_ft); c5.alignment = align_right; c5.number_format = "0.0%"
        c6 = ws4.cell(row=idx, column=6, value=f"=E{idx}-E$5"); c6.alignment = align_right; c6.number_format = "-0.0%pp;+0.0%pp;0.0%pp"; c6.font = font_formula
        c7 = ws4.cell(row=idx, column=7, value=g2_zs); c7.alignment = align_right; c7.number_format = "0.0%"
        c8 = ws4.cell(row=idx, column=8, value=f"=G{idx}-G$5"); c8.alignment = align_right; c8.number_format = "-0.0%pp;+0.0%pp;0.0%pp"; c8.font = font_formula
        c9 = ws4.cell(row=idx, column=9, value=indob_acc); c9.alignment = align_right; c9.number_format = "0.0%"
        c10 = ws4.cell(row=idx, column=10, value=f"=I{idx}-I$5"); c10.alignment = align_right; c10.number_format = "-0.0%pp;+0.0%pp;0.0%pp"; c10.font = font_formula
        c11 = ws4.cell(row=idx, column=11, value=mdeb_acc); c11.alignment = align_right; c11.number_format = "0.0%"
        c12 = ws4.cell(row=idx, column=12, value=f"=K{idx}-K$5"); c12.alignment = align_right; c12.number_format = "-0.0%pp;+0.0%pp;0.0%pp"; c12.font = font_formula
        c13 = ws4.cell(row=idx, column=13, value=xlm_acc); c13.alignment = align_right; c13.number_format = "0.0%"
        c14 = ws4.cell(row=idx, column=14, value=f"=M{idx}-M$5"); c14.alignment = align_right; c14.number_format = "-0.0%pp;+0.0%pp;0.0%pp"; c14.font = font_formula
        c15 = ws4.cell(row=idx, column=15, value=comp_acc); c15.alignment = align_right; c15.number_format = "0.0%"
        c16 = ws4.cell(row=idx, column=16, value=f"=O{idx}-O$5"); c16.alignment = align_right; c16.number_format = "-0.0%pp;+0.0%pp;0.0%pp"; c16.font = font_formula
        c17 = ws4.cell(row=idx, column=17, value=notes); c17.alignment = align_left; c17.font = font_data

        fill_curr = fill_ice if idx % 2 == 1 else fill_gray
        for c in [c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13, c14, c15, c16, c17]:
            c.border = thin_border
            c.fill = fill_curr

    # =========================================================================
    # SHEET 5: Arsitektur Pipeline Gemini
    # =========================================================================
    ws5 = wb.create_sheet(title="Arsitektur Pipeline Gemini")
    ws5.views.sheetView[0].showGridLines = True

    ws5.merge_cells("A1:E1")
    ws5["A1"] = "ARSITEKTUR PIPELINE PRODUKSI: TWO-STAGE OCR-TO-LLM (TESSERACT-TO-GEMINI)"
    ws5["A1"].font = font_title
    ws5["A1"].fill = fill_title
    ws5["A1"].alignment = align_center
    ws5.row_dimensions[1].height = 26

    ws5.merge_cells("A2:E2")
    ws5["A2"] = "Penjelasan Rinci: Mengapa Pipeline Menggunakan Tesseract OCR Dahulu Sebelum Masuk ke LLM Gemini"
    ws5["A2"].font = font_subtitle
    ws5["A2"].fill = fill_title
    ws5["A2"].alignment = align_center
    ws5.row_dimensions[2].height = 18

    ws5.cell(row=4, column=1, value="1. Tahapan Alur Kerja Produksi (Step-by-Step)").font = font_sub_header
    headers_pipe = ["Tahap", "Komponen Sistem", "Masukan (Input)", "Keluaran (Output)", "Fungsi & Rasional Desain"]
    ws5.row_dimensions[5].height = 24
    for c_idx, text in enumerate(headers_pipe, start=1):
        cell = ws5.cell(row=5, column=c_idx, value=text)
        cell.font = font_header; cell.fill = fill_section; cell.alignment = align_center; cell.border = header_border

    steps = [
        ["Tahap 1: Fast Path", "PyMuPDF (fitz)", "File PDF Asli", "Teks Digital (raw_text)", "Ekstraksi instan (~0.05s) untuk 25 PDF yang memiliki text layer asli."],
        ["Tahap 2: OCR Fallback", "Tesseract Standalone Multi-PSM", "Raster PNG @300 DPI", "Teks Karakter (raw_text)", "Membaca teks dari sertifikat pindaian/scan (49 dokumen) dengan kamus ind+eng."],
        ["Tahap 3: Prompt Assembly", "gemini_extractor.py", "Teks OCR + Schema JSON", "HTTP Payload JSON", "Menyusun instruksi ekstraksi semantik & format JSON standar form KHP."],
        ["Tahap 4: LLM Parsing", "gemini-3.1-flash-lite", "Teks Hasil OCR via REST", "JSON Entitas Terstruktur", "Mengekstrak 7 field utama dengan kecerdasan semantik (temperature=0.0 deterministik)."],
        ["Tahap 5: Form Mapping", "form_mapper.py", "JSON Entitas + Full Text", "Form KHP Mapped Fields", "Memetakan nilai bersih ke dropdown master data KHP & menghitung skor verifikasi."],
        ["Tahap 6: Safety Net", "Graceful Fallback", "Status API / Koneksi", "Offline Pipeline Result", "Jika Google API offline (429/503/timeout), otomatis dialihkan ke Combined v4.2 tanpa error 500."]
    ]

    for idx, (st, comp, inp, out, fn) in enumerate(steps, start=6):
        ws5.row_dimensions[idx].height = 22
        fill_curr = fill_ice if idx % 2 == 1 else fill_gray
        for c_idx, val in enumerate([st, comp, inp, out, fn], start=1):
            c = ws5.cell(row=idx, column=c_idx, value=val)
            c.font = font_data_bold if c_idx in [1, 2] else font_data
            c.fill = fill_curr
            c.border = thin_border
            c.alignment = align_left if c_idx in [2, 3, 4, 5] else align_center

    ws5.cell(row=13, column=1, value="2. Perbandingan Arsitektur: Two-Stage (OCR-to-LLM) vs Direct Multimodal (Vision-to-LLM)").font = font_sub_header
    headers_comp_arch = ["Dimensi Arsitektur", "Two-Stage: Tesseract-to-Gemini (Pipeline Saat Ini)", "Direct Multimodal: Vision-to-Gemini (Kirim Gambar/PDF)", "Keuntungan Pendekatan Proyek"]
    ws5.row_dimensions[14].height = 24
    for c_idx, text in enumerate(headers_comp_arch, start=1):
        cell = ws5.cell(row=14, column=c_idx, value=text)
        cell.font = font_header; cell.fill = fill_section; cell.alignment = align_center; cell.border = header_border

    arch_compare = [
        ["Masukan ke LLM", "Teks Bersih / Hasil OCR (~300 - 800 kata teks polos)", "File Gambar Pindaian / PDF base64 utuh (~2 - 8 Megabyte)", "Ukuran payload HTTP sangat kecil (<5 KB vs >2 MB), hemat bandwidth."],
        ["Konsumsi Token", "1.369 Token per Sertifikat (Input + Output)", "3.000 - 8.000+ Token per Halaman (Image Tile Tokens)", "Menghemat biaya token hingga 75% per pemanggilan API."],
        ["Biaya API / Dokumen", "Rp9.50 per Sertifikat (Total 74 doc = Rp703.27)", "~Rp40.00 - Rp75.00 per Sertifikat (Tergantung resolusi gambar)", "Sangat ekonomis untuk beban kerja ribuan sertifikat mahasiswa."],
        ["Kecepatan / Latensi", "Rata-rata 1.36 detik per sertifikat", "3.5 - 6.0 detik per sertifikat (Encoding & pemrosesan visual)", "Pengguna form antarmuka web mendapatkan respon autofill lebih instan."],
        ["Ketahanan Fallback", "Teks OCR lokal sudah tersedia di memori; jika API mati, langsung fallback offline", "Jika API mati, proses gagal total kecuali ada OCR lokal terpisah", "Zero 500 error guarantee: jika kuota habis, form tetap terisi via Combined v4.2."],
        ["Presisi Karakter", "Tesseract multi-PSM unggul pada nomor surat resmi bertanda baca kompleks", "VLM generatif terkadang melakukan halusinasi pada digit nomor kecil", "Kombinasi OCR deterministik + LLM semantik memberikan hasil optimal."]
    ]

    for idx, (dim, two_s, multi_s, adv) in enumerate(arch_compare, start=15):
        ws5.row_dimensions[idx].height = 24
        fill_curr = fill_ice if idx % 2 == 1 else fill_gray
        for c_idx, val in enumerate([dim, two_s, multi_s, adv], start=1):
            c = ws5.cell(row=idx, column=c_idx, value=val)
            c.font = font_data_bold if c_idx == 1 else font_data
            c.fill = fill_curr
            c.border = thin_border
            c.alignment = align_left

    # Auto-fit Column Widths across all sheets with sensible max width
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                # Skip merged title rows
                if cell.row in [1, 2, 30, 31, 39, 40]:
                    continue
                val_str = str(cell.value or "")
                if val_str.startswith("="):
                    val_str = "00.0%pp"
                max_len = max(max_len, len(val_str))
            sheet.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 52)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT_PATH)
    print(f"Workbook berhasil disimpan: {OUTPUT_PATH}")

if __name__ == "__main__":
    build_excel_report()
