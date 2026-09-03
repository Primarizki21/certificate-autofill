#!/usr/bin/env python3
"""Script untuk menghasilkan workbook Excel komparasi lengkap:
- Evaluasi komparasi pipeline & encoder NER (mDeBERTa, XLM-RoBERTa, Gemini, Composite v4.x)
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
    ACCENT_RED = "F8D7DA"     # Drop / Noise
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
    ws1["A2"] = "Evaluasi Frozen Baseline Matcher v2 (Framework 5-Field: 310 Sel & All-Cells 6-Field: 444 Sel) | Tanggal Evaluasi: 2026-09-02"
    ws1["A2"].font = font_subtitle
    ws1["A2"].fill = fill_title
    ws1["A2"].alignment = align_center
    ws1.row_dimensions[2].height = 18

    # Table 1: Komparasi Utama
    headers_t1 = [
        "Metode / Model", "Kategori Arsitektur", "MACRO Exact", "MACRO Fuzzy",
        "95% CI Exact", "Nama Kegiatan", "Nomor Sertifikat", "Penyelenggara",
        "Tgl Mulai", "Tgl Selesai", "Tingkat (All-Cells)", "Waktu Proses (74 Cert)", "VRAM / Biaya", "Status Produksi"
    ]
    ws1.row_dimensions[4].height = 28
    for col_idx, text in enumerate(headers_t1, start=1):
        cell = ws1.cell(row=4, column=col_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

    rows_t1 = [
        ["IndoBERT Pre-trained (indobert-ner-gold)", "Token Classification (Zero-Shot)", 0.128, 0.288, "[9.50%, 16.20%]", 0.164, 0.000, 0.110, 0.273, 0.073, "N/A", "5.1 detik (0.07s/c)", "~2.5 GB", "Baseline Pre-trained (Off-the-shelf)"],
        ["IndoBERT Fine-Tuned Gagal (indobert-base-p1)", "Full Fine-Tuning (59 Sampel)", 0.015, 0.082, "N/A", 0.027, 0.000, 0.014, 0.036, 0.000, "N/A", "~240 detik (5 ep)", "~3.5 GB", "Gagal (Catastrophic Forgetting)"],
        ["mDeBERTa-v3-base (86M)", "5-Fold CV Token Classif.", 0.3484, 0.5129, "[28.95%, 40.92%]", 0.2568, 0.5577, 0.2568, 0.3273, 0.4182, "N/A", "734 detik (~12.2m)", "4.08 GB", "Eksplorasi (PASS)"],
        ["XLM-RoBERTa-large (560M)", "5-Fold CV Token Classif.", 0.4355, 0.5548, "[37.17%, 50.00%]", 0.3514, 0.5962, 0.3784, 0.4545, 0.4545, "N/A", "794 detik (~13.2m)", "7.09 GB (Adafactor)", "Eksplorasi (PASS)"],
        ["IndoBERT-ner-gold Fine-Tuned (334M)", "5-Fold CV Token Classif.", 0.4452, 0.5710, "[38.59%, 50.82%]", 0.4324, 0.5769, 0.3649, 0.4909, 0.4000, "N/A", "700.1 detik (~11.7m)", "4.65 GB", "BEST ENCODER (PASS)"],
        ["Direct Gemini 3.1 Flash Lite", "Two-Stage Tesseract-to-LLM", 0.6324, 0.7378, "[58.78%, 68.92%]", 0.6216, 0.5946, 0.5946, 0.6757, 0.6757, 0.6622, "100.6 detik (1.36s/c)", "Rp703 (~Rp9.50/c)", "PRODUKSI AKTIF (Opt A)"],
        ["Composite v4.x (Pure OCR)", "Pure 100% Tesseract OCR + Rules", 0.7710, 0.8516, "[72.10%, 81.80%]", 0.7600, 0.8947, 0.3600, 0.9000, 0.9000, 0.6847, "0 detik (Offline)", "0 GB (CPU Local)", "Baseline Pure OCR"],
        ["Combined v4.2 (Hybrid)", "Hybrid Layer + 3 Pillars & Crop", 0.8742, 0.9000, "[83.50%, 91.20%]", 0.7970, 0.9230, 0.6620, 0.9090, 0.9090, 0.7682, "0 detik (Offline)", "0 GB (CPU Local)", "Fallback Produksi"],
    ]

    for r_idx, row_data in enumerate(rows_t1, start=5):
        ws1.row_dimensions[r_idx].height = 20
        fill_current = fill_ice if r_idx % 2 == 1 else fill_gray
        if "PRODUKSI AKTIF" in str(row_data[-1]):
            fill_current = fill_win

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
    row_avg = 13
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
        cell = ws1.cell(row=row_avg, column=c, value=f"=AVERAGE({col_letter}5:{col_letter}12)")
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
    ws1.cell(row=15, column=1, value="ANALISIS DELTA PERFORMANSI VS BASELINE PRE-TRAINED NER V1 (INDOBERT)").font = font_sub_header
    headers_t2 = ["Model Komparasi", "Baseline Exact", "Model Exact", "Peningkatan Mutlak (pp)", "Peningkatan Relatif (%)", "Kesimpulan Arsitektural"]
    ws1.row_dimensions[16].height = 24
    for c_idx, text in enumerate(headers_t2, start=1):
        cell = ws1.cell(row=16, column=c_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

    delta_rows = [
        ["IndoBERT Fine-Tuned Gagal (Phase v2)", 5, 6, "Anjlok -11.3pp akibat catastrophic forgetting pada 59 sampel dan ketiadaan weighted loss."],
        ["mDeBERTa-v3-base (86M)", 5, 7, "Peningkatan substansial (+22.04pp) pada recall entitas non-O via FP32 & soft-capping."],
        ["XLM-RoBERTa-large (560M)", 5, 8, "Model 560M melompat +30.75pp; representasi BPE multilingual sangat kuat."],
        ["IndoBERT-ner-gold Fine-Tuned (334M)", 5, 9, "ENCODER TERBAIK (+31.72pp vs pre-trained, +0.97pp vs XLM-RoBERTa-large, kegiatan melonjak ke 43.2%)."],
        ["Direct Gemini 3.1 Flash Lite", 5, 10, "LLM murni melampaui seluruh encoder lokal tanpa memerlukan fine-tuning."],
        ["Composite v4.x (Pure OCR Rules)", 5, 11, "Rule deterministik offline tetap paling unggul pada domain penanggalan & nomor."],
        ["Combined v4.2 (Hybrid Pipeline)", 5, 12, "Pipeline komposit offline terbaik, unggul +74.62pp dibanding baseline NER v1."],
    ]

    for idx, (label, base_r, model_r, notes) in enumerate(delta_rows, start=17):
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

    ws2.merge_cells("A1:D1")
    ws2["A1"] = "SPESIFIKASI TEKNIS & KONFIGURASI HYPERPARAMETER ENCODER (NER-ENCODER-001)"
    ws2["A1"].font = font_title
    ws2["A1"].fill = fill_title
    ws2["A1"].alignment = align_center
    ws2.row_dimensions[1].height = 26

    ws2.merge_cells("A2:D2")
    ws2["A2"] = "Perbandingan Parameter Pelatihan & Stabilisasi Numerik untuk mDeBERTa-v3-base vs XLM-RoBERTa-large"
    ws2["A2"].font = font_subtitle
    ws2["A2"].fill = fill_title
    ws2["A2"].alignment = align_center
    ws2.row_dimensions[2].height = 18

    headers_t3 = ["Parameter / Spesifikasi", "treamyracle/indobert-ner-gold", "microsoft/mdeberta-v3-base", "facebookai/xlm-roberta-large", "Rasional & Detail Desain Arsitektural"]
    ws2.row_dimensions[4].height = 26
    for c_idx, text in enumerate(headers_t3, start=1):
        cell = ws2.cell(row=4, column=c_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

    configs = [
        ["Model Checkpoint", "treamyracle/indobert-ner-gold", "microsoft/mdeberta-v3-base", "facebookai/xlm-roberta-large", "Bobot resmi dari Hugging Face Hub."],
        ["Jumlah Parameter", "334 Juta Parameter", "86 Juta Parameter", "560 Juta Parameter", "IndoBERT-large (334M) di tengah antara mDeBERTa dan XLM-RoBERTa."],
        ["Arsitektur Dasar", "BERT-large (Bidirectional Transformer)", "DeBERTa-v2 (Disentangled Attention)", "RoBERTa (Transformer Encoder)", "IndoBERT fokus monolingual Indonesia vs DeBERTa & XLM-RoBERTa multilingual."],
        ["Tokenizer & Vocab", "BertTokenizerFast (Indo4B: 32k)", "DeBERTaV2TokenizerFast (SPM: 250k)", "XLMRobertaTokenizerFast (BPE: 250k)", "Kosakata IndoBERT utuh pada kata Indonesia; tidak terfragmentasi seperti multilingual."],
        ["Skema Validasi", "5-Fold Stratified Cross-Validation", "5-Fold Stratified Cross-Validation", "5-Fold Stratified Cross-Validation", "Identik 100%: stratified berdasarkan kelengkapan field 74 dokumen."],
        ["Loss Function", "Weighted Cross Entropy", "Weighted Cross Entropy", "Weighted Cross Entropy", "Penyeimbang ketimpangan ekstrem antara kelas O (92%) vs entitas non-O (8%)."],
        ["Formula Bobot Kelas", "Square-Root Inverse-Frequency", "Square-Root Inverse-Frequency", "Square-Root Inverse-Frequency", "w_c = min(sqrt(N_max / N_c), 10.0) mencegah bobot ekstrem meledakkan loss."],
        ["Batas Bobot Maksimal", "10.0x", "10.0x", "10.0x", "Bobot dibatasi maksimal 10.0 mencegah divergensi gradien."],
        ["Optimizer", "Adafactor (scale=False, rel=False)", "Adafactor (scale=False, rel=False)", "Adafactor (scale=False, rel=False)", "Memfaktorkan momen orde kedua; memangkas memori dari ~2.5GB ke ~35MB."],
        ["Learning Rate", "2.0e-5 (0.00002)", "2.0e-5 (0.00002)", "2.0e-5 (0.00002)", "Learning rate standar fine-tuning transformer encoder."],
        ["Weight Decay", "0.01", "0.01", "0.01", "Regularisasi L2 standar untuk mencegah overfitting pada dataset kecil."],
        ["Batch Size (Per Device)", "1", "1", "1", "Menghindari lonjakan memori aktivasi token pada GPU 8GB."],
        ["Gradient Accumulation", "8 langkah", "8 langkah", "8 langkah", "Akumulasi gradien menghasilkan Effective Batch Size = 8."],
        ["Effective Batch Size", "8 dokumen", "8 dokumen", "8 dokumen", "Ukuran batch efektif yang stabil untuk optimasi gradien."],
        ["Total Epoch", "10 Epoch", "10 Epoch", "10 Epoch", "10 epoch per fold; total 70-100 langkah pembaruan bobot per fold."],
        ["Langkah Optimizer / Fold", "70 - 100 Langkah", "80 - 100 Langkah", "80 - 100 Langkah", "Langkah optimasi per fold sesuai pembagian fold data latih."],
        ["Presisi Bobot (Master)", "torch.float32 (model.float())", "torch.float32 (model.float())", "torch.float32 (model.float())", "Stabilitas master weight FP32."],
        ["Presisi Autocast", "bfloat16 (autocast GPU)", "bfloat16 (autocast GPU)", "bfloat16 (autocast GPU)", "Didukung native oleh arsitektur RTX 5050; dynamic range FP32."],
        ["Gradient Checkpointing", "Aktif (gradient_checkpointing_enable)", "Aktif (gradient_checkpointing_enable)", "Aktif (gradient_checkpointing_enable)", "Menukar sedikit komputasi dengan penghematan VRAM aktivasi ~60%."],
        ["Max Sequence Length", "512 Token", "512 Token", "512 Token", "Batas panjang konteks maksimum standar model encoder."],
        ["Sliding Window Stride", "64 Token", "64 Token", "64 Token", "Overlap jendela sliding agar token di batas 512 tidak terpotong."],
        ["Inisialisasi Seed", "SEED = 42 + fold_index", "SEED = 42 + fold_index", "SEED = 42 + fold_index", "Deterministik penuh untuk reproduksibilitas hasil eksperimen."],
        ["Hasil Sanity Overfit", "96.0% Recall (24/25 token)", "100.0% Recall (25/25 token)", "100.0% Recall (25/25 token)", "Verifikasi bahwa model mampu menghafal label non-O sebelum pelatihan OOF."],
        ["Total Waktu Latih (5 Fold)", "700.1 detik (~11.7 menit)", "734 detik (~12.2 menit)", "794 detik (~13.2 menit)", "Kecepatan eksekusi rata-rata 1.4 - 1.8 detik per langkah optimizer."],
        ["Puncak Konsumsi VRAM", "4.65 GB / 8.15 GB", "4.08 GB / 8.15 GB", "7.09 GB / 8.15 GB", "Ketiga model berhasil dilatih pada workstation RTX 5050 tanpa error OOM."]
    ]

    for r_idx, row_data in enumerate(configs, start=5):
        ws2.row_dimensions[r_idx].height = 20
        fill_curr = fill_ice if r_idx % 2 == 1 else fill_gray
        for c_idx, val in enumerate(row_data, start=1):
            cell = ws2.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_data_bold if c_idx == 1 else font_data
            cell.fill = fill_curr
            cell.border = thin_border
            cell.alignment = align_left if c_idx in [1, 5] else align_center



    # Section 2 di Sheet 2: Analisis Mendalam Kegagalan Fine-Tune IndoBERT & Potensi Retry
    ws2.cell(row=32, column=1, value="2. Analisis Mendalam: Mengapa Fine-Tuning IndoBERT Gagal & Rekomendasi Retry dengan Konfigurasi Tepat").font = font_sub_header
    headers_t4 = [
        "Dimensi Arsitektural / Faktor",
        "Konfigurasi Percobaan Gagal (Phase v2)",
        "Dampak Nyata Kerusakan Model",
        "Konfigurasi Rekomendasi Retry",
        "Potensi Unik & Keunggulan IndoBERT"
    ]
    ws2.row_dimensions[34].height = 24
    for c_idx, text in enumerate(headers_t4, start=1):
        cell = ws2.cell(row=34, column=c_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

    indobert_analysis = [
        [
            "Model Checkpoint Awal",
            "indobenchmark/indobert-base-p1 (Base model kosongan tanpa head NER).",
            "Head klasifikasi diinisialisasi secara acak (random weights), harus belajar representasi dari nol pada 59 sampel.",
            "Gunakan treamyracle/indobert-ner-gold (sudah pre-trained pada Indonesian NER Gold).",
            "Checkpoint sudah memahami pola entitas nama, organisasi, dan tanggal bahasa Indonesia; tinggal adaptasi domain sertifikat."
        ],
        [
            "Skema Pelatihan & Bobot",
            "Full Fine-Tuning (seluruh 110M parameter dibuka tanpa perlindungan).",
            "Catastrophic forgetting parah (F1=0.15); representasi bahasa Indonesia umum rusak akibat gradient step agresif.",
            "PEFT / LoRA (rank=8, alpha=16) pada query/value ATAU freeze 10 layer bawah encoder.",
            "Backbone terlindungi 100% dari kerusakan memori; hanya adapter dan classifier head yang beradaptasi dengan domain."
        ],
        [
            "Fungsi Loss & Ketimpangan Kelas",
            "Standard Cross-Entropy tanpa pembobotan (Unweighted loss).",
            "Rasio token non-entitas 'O' mencapai 92%. Model belajar strategi trivial: memprediksi semua token sebagai 'O'.",
            "Weighted Cross-Entropy dengan formula Square-Root Inverse-Frequency (soft-capped max 10.0x).",
            "Gradien kelas minoritas (nomor sertifikat, tanggal, nama acara) terlindungi sehingga tidak tertelan oleh kelas 'O'."
        ],
        [
            "Langkah Optimizer (Training Steps)",
            "Batch size 8 pada 59 sampel, 5 epoch -> hanya ~7 step/epoch = 35 langkah pembaruan bobot total.",
            "Underfitting parah; 35 langkah pembaruan tidak cukup secara matematis bagi model 110M untuk konvergen.",
            "Batch size 1, Gradient Accumulation 8 (effective batch 8), 10-15 epoch dengan 5-fold CV (~600-900 step).",
            "Konvergensi gradien stabil, smooth, dan terverifikasi secara statistik out-of-fold tanpa data leakage."
        ],
        [
            "Panjang Konteks & Truncation",
            "max_length=512 token, truncation keras tanpa sliding window / stride.",
            "Teks di bagian bawah sertifikat (tanda tangan dekan, NIP, tanggal terbit) terpotong dan tidak pernah terlihat model.",
            "Sliding window dengan max_length=512, stride=64, return_overflowing_tokens=True via Fast Tokenizer.",
            "Seluruh baris dokumen dari header, isi penghargaan, hingga footer pejabat tanda tangan terbaca utuh."
        ],
        [
            "Kualitas Label Anotasi (BIO)",
            "BIO silver labels hasil string-matching naif dari CSV ke teks OCR (generate_bio_labels.py).",
            "Typo kecil OCR langsung menyebabkan kata sah berlabel 'O'. Terjadi kontaminasi label latih (label noise).",
            "Normalisasi karakter & fuzzy subword alignment sebelum melabeli BIO token untuk mentoleransi derau OCR.",
            "Kualitas data latih bersih dan konsisten; model tidak diajari salah bahwa kata bertypo adalah non-entitas."
        ],
        [
            "Spesialisasi Tokenizer",
            "Tokenizer SentencePiece IndoBERT tidak dimanfaatkan fitur fast alignment word_ids.",
            "Alignment token-ke-kata bergeser pada karakter spasi ganda atau tanda baca pindaian OCR.",
            "Fast Tokenizer dengan word_ids mapping & deteksi span kata presisi.",
            "KEUNGGULAN UTAMA: IndoBERT dilatih murni teks Indonesia (Indo4B), kosakata sertifikat (Penyelenggara, Dekan, Fakultas) utuh tidak terpecah jadi subword acak."
        ],
        [
            "Efisiensi Komputasi & Deployment",
            "Pelatihan standar tanpa optimasi memori modern.",
            "VRAM ~3.5 GB tanpa checkpointing; model hasil gagal tidak dapat dipakai.",
            "Optimizer Adafactor + Autocast bfloat16 + Gradient Checkpointing.",
            "VRAM puncak <2.5 GB pada GPU lokal, inferensi sangat kencang (<0.08 detik/cert), 100% offline tanpa biaya cloud API."
        ]
    ]

    for r_idx, r_data in enumerate(indobert_analysis, start=35):
        ws2.row_dimensions[r_idx].height = 36
        fill_curr = fill_ice if r_idx % 2 == 1 else fill_gray
        for c_idx, val in enumerate(r_data, start=1):
            cell = ws2.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_data_bold if c_idx == 1 else font_data
            cell.fill = fill_curr
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

    ws2.row_dimensions[33].height = 14
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

    # Table mDeBERTa
    ws3.cell(row=3, column=1, value="1. Evaluasi Per-Fold: microsoft/mdeberta-v3-base (86M)").font = font_sub_header
    headers_folds = ["Fold", "Train Docs", "Val Docs", "Durasi (s)", "Nama Kegiatan", "Nomor", "Penyelenggara", "Tgl Mulai", "Tgl Selesai", "MACRO Exact", "MACRO Fuzzy"]
    ws3.row_dimensions[4].height = 24
    for c_idx, text in enumerate(headers_folds, start=1):
        cell = ws3.cell(row=4, column=c_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

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
            cell.font = font_data
            cell.fill = fill_curr
            cell.border = thin_border
            if isinstance(val, float) and c_idx >= 5:
                cell.number_format = "0.0%"
                cell.alignment = align_right
            elif c_idx == 4:
                cell.number_format = "0.0"
                cell.alignment = align_right
            else:
                cell.alignment = align_center

    # Rata-rata mDeBERTa row
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

    # Table XLM-RoBERTa
    ws3.cell(row=12, column=1, value="2. Evaluasi Per-Fold: facebookai/xlm-roberta-large (560M)").font = font_sub_header
    ws3.row_dimensions[13].height = 24
    for c_idx, text in enumerate(headers_folds, start=1):
        cell = ws3.cell(row=13, column=c_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

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
            cell.font = font_data
            cell.fill = fill_curr
            cell.border = thin_border
            if isinstance(val, float) and c_idx >= 5:
                cell.number_format = "0.0%"
                cell.alignment = align_right
            elif c_idx == 4:
                cell.number_format = "0.0"
                cell.alignment = align_right
            else:
                cell.alignment = align_center

    # Rata-rata XLM-RoBERTa row
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


    # Table IndoBERT-ner-gold (334M)
    ws3.cell(row=21, column=1, value="3. Evaluasi Per-Fold: treamyracle/indobert-ner-gold (334M) — BEST ENCODER").font = font_sub_header
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
    # Table Bootstrap CI
    ws3.cell(row=30, column=1, value="4. Validasi Statistik Bootstrap 1000x Resampling (Exact Macro)").font = font_sub_header
    headers_ci = ["Model Evaluasi", "Sampel Dokumen", "Mean Bootstrap", "Batas Bawah (2.5%)", "Batas Atas (97.5%)", "Rentang CI 95% (Width)", "Stabilitas Estimasi"]
    ws3.row_dimensions[31].height = 24
    for c_idx, text in enumerate(headers_ci, start=1):
        cell = ws3.cell(row=31, column=c_idx, value=text)
        cell.font = font_header; cell.fill = fill_section; cell.alignment = align_center; cell.border = header_border

    ci_data = [
        ["mDeBERTa-v3-base (86M)", 74, 0.3478, 0.2895, 0.4092, "Sangat Stabil (Normal Distribution)"],
        ["XLM-RoBERTa-large (560M)", 74, 0.4357, 0.3717, 0.5000, "Sangat Stabil (Normal Distribution)"],
        ["IndoBERT-ner-gold (334M)", 74, 0.4457, 0.3859, 0.5082, "ENCODER TERBAIK (95% CI Tertinggi: 38.6% - 50.8%)"],
    ]

    for idx, (m_name, n_doc, mean_v, low_v, high_v, notes) in enumerate(ci_data, start=32):
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

    ws4.merge_cells("A1:I1")
    ws4["A1"] = "UJI KETAHANAN OUT-OF-DISTRIBUTION (OOD STRESS TESTING PADA 236 SEL BEBAS-INSTITUSI)"
    ws4["A1"].font = font_title
    ws4["A1"].fill = fill_title
    ws4["A1"].alignment = align_center
    ws4.row_dimensions[1].height = 26

    ws4.merge_cells("A2:I2")
    ws4["A2"] = "Ketahanan Field Tanggal, Nomor, dan Kegiatan terhadap Mutasi Entitas & Perturbasi Noise Karakter OCR"
    ws4["A2"].font = font_subtitle
    ws4["A2"].fill = fill_title
    ws4["A2"].alignment = align_center
    ws4.row_dimensions[2].height = 18

    headers_ood = [
        "Kondisi Uji Gangguan", "Jumlah Sel",
        "Akurasi IndoBERT", "Penurunan IndoBERT",
        "Akurasi mDeBERTa", "Penurunan mDeBERTa",
        "Akurasi XLM-RoBERTa", "Penurunan XLM-RoBERTa",
        "Akurasi Composite v4.x", "Penurunan Composite v4.x",
        "Toleransi & Karakteristik"
    ]
    ws4.row_dimensions[4].height = 26
    for c_idx, text in enumerate(headers_ood, start=1):
        cell = ws4.cell(row=4, column=c_idx, value=text)
        cell.font = font_header
        cell.fill = fill_section
        cell.alignment = align_center
        cell.border = header_border

    ood_table = [
        ["Clean Baseline (Tanpa Noise)", 236, 0.4703, 0.3771, 0.4534, 0.8800, "Kondisi teks masukan OCR standar"],
        ["Mutasi Entitas (UNAIR->UNS dll)", 236, 0.3983, 0.3051, 0.3771, 0.8060, "Mengganti nama univ/fakultas/hima ke institusi lain"],
        ["Perturbasi Noise OCR 10%", 236, 0.3051, 0.2500, 0.2924, 0.7990, "Simulasi kebingungan karakter 5<->S, 8<->B, 0<->O, 1<->I"],
        ["Perturbasi Noise OCR 25%", 236, 0.1822, 0.2034, 0.1949, 0.6980, "Tingkat noise OCR sedang pada dokumen buram"],
        ["Perturbasi Noise OCR 50%", 236, 0.0890, 0.1017, 0.1229, 0.5410, "Tingkat noise OCR ekstrem pada pindaian sangat rusak"],
    ]

    for idx, (cond, n_cells, indob_acc, mdeb_acc, xlm_acc, comp_acc, notes) in enumerate(ood_table, start=5):
        ws4.row_dimensions[idx].height = 20
        c1 = ws4.cell(row=idx, column=1, value=cond); c1.font = font_data_bold; c1.alignment = align_left
        c2 = ws4.cell(row=idx, column=2, value=n_cells); c2.alignment = align_center; c2.number_format = "0"
        c3 = ws4.cell(row=idx, column=3, value=indob_acc); c3.alignment = align_right; c3.number_format = "0.0%"
        c4 = ws4.cell(row=idx, column=4, value=f"=C{idx}-C$5"); c4.alignment = align_right; c4.number_format = "-0.0%pp;+0.0%pp;0.0%pp"; c4.font = font_formula
        c5 = ws4.cell(row=idx, column=5, value=mdeb_acc); c5.alignment = align_right; c5.number_format = "0.0%"
        c6 = ws4.cell(row=idx, column=6, value=f"=E{idx}-E$5"); c6.alignment = align_right; c6.number_format = "-0.0%pp;+0.0%pp;0.0%pp"; c6.font = font_formula
        c7 = ws4.cell(row=idx, column=7, value=xlm_acc); c7.alignment = align_right; c7.number_format = "0.0%"
        c8 = ws4.cell(row=idx, column=8, value=f"=G{idx}-G$5"); c8.alignment = align_right; c8.number_format = "-0.0%pp;+0.0%pp;0.0%pp"; c8.font = font_formula
        c9 = ws4.cell(row=idx, column=9, value=comp_acc); c9.alignment = align_right; c9.number_format = "0.0%"
        c10 = ws4.cell(row=idx, column=10, value=f"=I{idx}-I$5"); c10.alignment = align_right; c10.number_format = "-0.0%pp;+0.0%pp;0.0%pp"; c10.font = font_formula
        c11 = ws4.cell(row=idx, column=11, value=notes); c11.alignment = align_left; c11.font = font_data

        fill_curr = fill_ice if idx % 2 == 1 else fill_gray
        for c in [c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11]:
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

    # Auto-fit Column Widths across all sheets
    # Auto-fit Column Widths across all sheets with sensible max width
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                # Skip merged title rows
                if cell.row in [1, 2, 32]:
                    continue
                val_str = str(cell.value or "")
                if val_str.startswith("="):
                    val_str = "00.0%pp"
                max_len = max(max_len, len(val_str))
            sheet.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 48)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT_PATH)
    print(f"Workbook berhasil disimpan: {OUTPUT_PATH}")

if __name__ == "__main__":
    build_excel_report()
