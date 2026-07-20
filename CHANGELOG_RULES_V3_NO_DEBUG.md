# CHANGELOG RULES V3 NO DEBUG

Perubahan:
- Panel Debug hasil parsing dihapus dari frontend.
- Raw text preview tidak lagi ditampilkan di halaman pengguna.
- Pemanggilan renderDebug dinonaktifkan.
- CSS menambahkan fallback `#debugPanel { display: none !important; }` agar tidak muncul walaupun browser masih menyimpan cache HTML lama.
- Backend API tetap mengembalikan data parsing seperti biasa; perubahan hanya pada tampilan frontend.
