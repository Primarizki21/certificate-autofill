# V5 - Date Force OCR

Perbaikan:
- Pipeline sekarang tetap menjalankan OCR tambahan jika field tanggal belum ditemukan, walaupun PyMuPDF/Docling sudah menghasilkan teks panjang.
- OCR fallback sekarang menggabungkan RapidOCR dan Tesseract, bukan hanya memakai Tesseract ketika RapidOCR kosong.
- Render OCR dinaikkan ke zoom 3.0 agar teks kecil seperti tanggal pelaksanaan lebih mudah terbaca.
- Tidak ada hardcode tanggal spesifik. Rule tetap membaca tanggal dari teks PDF/OCR.
