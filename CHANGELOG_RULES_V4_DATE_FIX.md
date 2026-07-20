# CHANGELOG RULES V4 DATE FIX

Perubahan:
- Parser tanggal dibuat lebih ketat dan lebih tahan hasil OCR.
- Mendukung interval `24 Agustus - 22 September 2024`.
- Mendukung interval tanpa dash akibat OCR, misalnya `24 Agustus 22 September 2024`.
- Mendukung interval bulan sama, misalnya `18 - 27 Agustus 2022`.
- Mendukung tanggal numerik `24/08/2024 - 22/09/2024`.
- OCR fallback Tesseract mencoba beberapa mode PSM agar tanggal kecil lebih sering terbaca.
