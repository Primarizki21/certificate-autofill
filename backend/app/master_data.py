FORM_OPTIONS = {
    "tahun_akademik": [
        "2022/2023 - Ganjil",
        "2022/2023 - Genap",
        "2023/2024 - Ganjil",
        "2023/2024 - Genap",
        "2024/2025 - Ganjil",
        "2024/2025 - Genap",
        "2025/2026 - Ganjil",
        "2025/2026 - Genap",
        "2035/2036 - Genap",
    ],
    "kelompok_kegiatan": [
        ":: Pilih Kelompok Kegiatan ::",
        "Kegiatan Wajib Universitas",
        "Kegiatan Bidang Organisasi dan Kepemimpinan",
        "Kegiatan Bidang Penalaran dan Keilmuan",
        "Kegiatan Bidang Minat dan Bakat",
        "Kegiatan Bidang Kepedulian Sosial",
        "Kegiatan Lainnya",
    ],
    "jenis_kegiatan": [
        "--",
        "Pengurus Organisasi",
        "Anggota Aktif Organisasi",
        "Mengikuti Pelatihan Kepemimpinan LKMM",
        "Latihan Kepemimpinan Lainnya",
        "Panitia Dalam Suatu Kegiatan Kemahasiswaan",
        "Mencalonkan Diri Sebagai Calon Ketua/Anggota Organisasi Mahasiswa",
        "Berpartisipasi Dalam Pemira",
        "Peserta PKKMB",
    ],
    "tingkat": [
        "Internasional",
        "Nasional",
        "Universitas",
        "Fakultas",
        "Departemen/Program Studi",
        "Lainnya",
    ],
    "prestasi_partisipasi_jabatan": [
        "Ketua",
        "Wakil Ketua",
        "Sekretaris",
        "Pengurus Inti Lain",
        "Anggota Pengurus",
        "Panitia",
        "Peserta",
    ],
    "jenis_penyelenggara": [
        "PTN di Indonesia",
        "PTS di Indonesia",
        "PT di luar negeri",
        "Kementerian Negara",
        "BUMN",
        "Lembaga/Yayasan lain",
    ],
    "bukti_fisik": [
        "Sertifikat",
        "Surat Keputusan",
        "Surat Perintah",
        "Presensi",
        "Kartu Pemilih",
        "Patent",
        "Fotocopi Hasil Karya",
        "Daftar Hadir",
        "Hasil Karya",
        "Dokumen",
        "Daftar Nilai",
    ],
}
# Group labels reuse existing form labels because source workbook exposes IDs only.
def _khp_option(option_id: int, label: str, group_id: int | None = None) -> dict[str, object]:
    option: dict[str, object] = {"id": option_id, "label": label, "active": True}
    if group_id is not None:
        option["group_id"] = group_id
    return option


KHP_ACTIVITY_MASTER = (
    (41, "PKKMB", 1),
    (42, "KKN-BBM", 1),
    (67, "Pengurus Organisasi", 2),
    (68, "Anggota Aktif Organisasi", 2),
    (69, "Mengikuti Pelatihan Kepemimpinan LKMM", 2),
    (70, "Latihan Kepemimpinan Lainnya", 2),
    (71, "Panitia Dalam Suatu Kegiatan Kemahasiswaan", 2),
    (72, "Mencalonkan Diri Sebagai Calon Ketua/Anggota Organisasi Mahasiswa", 2),
    (73, "Berpartisipasi Dalam Pemira", 2),
    (
        74,
        "Memperoleh prestasi dalam Lomba Karya Tulis Ilmiah/Lingkungan Hidup/Kreativitas/Inovatif/Pemikiran Kritis/Populer/Interpreneurship/Business Plan",
        3,
    ),
    (83, "Mengikuti Kegiatan Lomba Ilmiah", 3),
    (84, "Mengikuti kegiatan/forum ilmiah (seminar, lokakarya, workshop, pameran)", 3),
    (85, "Menghasilkan temuan inovasi yang dipatenkan", 3),
    (86, "Menghasilkan karya ilmiah yang dipublikasikan dalam majalah ilmiah", 3),
    (87, "Menghasilkan karya populer yang diterbitkan di surat kabar/majalah/media lainnya", 3),
    (88, "Menghasilkan karya yang didanai oleh pemerintah/pihak lain", 3),
    (89, "Memberikan pelatihan/bimbingan dalam penyusunan karya tulis", 3),
    (90, "Menghasilkan karya yang tidak dipublikasikan", 3),
    (91, "Mengikuti kuliah tamu", 3),
    (92, "Terlibat dalam penelitian pihak lain", 3),
    (93, "MAWAPRES", 3),
    (98, "Memperoleh prestasi dalam kegiatan Minat dan Bakat (Olahraga, Seni,Kerohanian dan IT)", 4),
    (99, "Mengikuti kegiatan Minat dan Bakat (Olahraga, Seni dan Kerohanian)", 4),
    (100, "Menjadi Pelatih/Pembimbing kegiatan Minat dan Bakat", 4),
    (101, "Melaksanakan Latihan Gabungan", 4),
    (102, "Melaksanakan aktivitas rutin berkaitan dengan kegiatan minat dan bakat yang diselenggarakan UKM", 4),
    (103, "Menjadi mitra tanding pada kegiatan minat dan bakat", 4),
    (104, "Menghasilkan karya seni (konser, pameran seni, puisi, fotografi, teater, dll)", 4),
    (105, "Mengelola Kewirausahaan", 4),
    (106, "Mengikuti Pelaksanaan Bakti Sosial", 5),
    (107, "Penanganan Bencana", 5),
    (108, "Bantuan pembimbingan rutin (LBB, Pengajian, TPA, PAUD)", 5),
    (109, "Kegiatan lain individual-sosial", 5),
    (110, "Upacara Bendera", 6),
    (111, "Berpartisipasi dalam kegiatan Alumni", 6),
    (112, "Melakukan kunjungan/studi banding", 6),
    (113, "Magang Kerja", 6),
    (114, "Magang Penelitian", 6),
    (115, "ESQ", 6),
    (116, "Kegiatan Jati Diri Lainnya", 6),
    (117, "Kompetisi Ilmiah Mahasiswa (KIM) tingkat Fakultas", 1),
    (121, "PKL", 1),
    (127, "Magang UKM", 1),
    (129, "Mengikuti Kegiatan Sertifikasi", 3),
)

KHP_LEVEL_MASTER = (
    (1, "Internasional"),
    (2, "Nasional"),
    (3, "Regional"),
    (4, "Universitas"),
    (5, "Fakultas"),
    (6, "Departemen/Program Studi"),
    (7, "UKM"),
    (8, "Nasional Ter-Akreditasi"),
    (9, "Nasional Tidak Ter-Akreditasi"),
    (10, "Lanjut"),
    (11, "Menengah"),
    (12, "Dasar"),
    (13, "Lainnya"),
)

KHP_ROLE_MASTER = (
    (1, "Ketua"),
    (2, "Wakil Ketua"),
    (3, "Sekretaris"),
    (4, "Pengurus Inti Lain"),
    (5, "Anggota Pengurus"),
    (6, "Peserta"),
    (7, "Juara I"),
    (8, "Juara II"),
    (9, "Juara III"),
    (10, "Finalis"),
    (11, "Peserta Terpilih"),
    (12, "Pembicara"),
    (13, "Moderator"),
    (14, "Anggota"),
    (15, "Delegasi"),
    (16, "Peserta Undangan"),
    (17, "Peserta Biasa"),
    (18, "Fasilitator"),
    (19, "Mandiri"),
    (20, "Kemitraan"),
    (21, "Panitia"),
    (27, "Juara Harapan III"),
    (29, "Best"),
    (25, "Juara Harapan I"),
    (26, "Juara Harapan II"),
    (31, "Completion"),
    (34, "LSP UNAIR"),
    (35, "Fakultas/Prodi"),
    (30, "Kompetensi"),
    (32, "BNSP"),
    (33, "Brevet A/B/C"),
)

KHP_MASTER_OPTIONS = {
    "tahun_akademik": FORM_OPTIONS["tahun_akademik"],
    "bukti_fisik": FORM_OPTIONS["bukti_fisik"],
    "kelompok_kegiatan": [
        _khp_option(1, "Kegiatan Wajib Universitas"),
        _khp_option(2, "Kegiatan Bidang Organisasi dan Kepemimpinan"),
        _khp_option(3, "Kegiatan Bidang Penalaran dan Keilmuan"),
        _khp_option(4, "Kegiatan Bidang Minat dan Bakat"),
        _khp_option(5, "Kegiatan Bidang Kepedulian Sosial"),
        _khp_option(6, "Kegiatan Lainnya"),
    ],
    "jenis_kegiatan": [
        _khp_option(option_id, label, group_id)
        for option_id, label, group_id in KHP_ACTIVITY_MASTER
    ],
    "tingkat": [
        _khp_option(option_id, label)
        for option_id, label in KHP_LEVEL_MASTER
    ],
    "prestasi_partisipasi_jabatan": [
        _khp_option(option_id, label)
        for option_id, label in KHP_ROLE_MASTER
    ],
    "jenis_penyelenggara": FORM_OPTIONS["jenis_penyelenggara"],
}

KHP_ACTIVITY_BY_ID = {
    option["id"]: option for option in KHP_MASTER_OPTIONS["jenis_kegiatan"]
}
KHP_LEVEL_BY_ID = {
    option["id"]: option for option in KHP_MASTER_OPTIONS["tingkat"]
}
KHP_ROLE_BY_ID = {
    option["id"]: option
    for option in KHP_MASTER_OPTIONS["prestasi_partisipasi_jabatan"]
}
KHP_TINGKAT_LABELS = tuple(option["label"] for option in KHP_MASTER_OPTIONS["tingkat"])

PTN_KEYWORDS = [
    "UNIVERSITAS AIRLANGGA",
    "UNIVERSITAS INDONESIA",
    "UNIVERSITAS GADJAH MADA",
    "INSTITUT TEKNOLOGI BANDUNG",
    "INSTITUT TEKNOLOGI SEPULUH NOPEMBER",
    "UNIVERSITAS BRAWIJAYA",
    "UNIVERSITAS DIPONEGORO",
    "UNIVERSITAS PADJADJARAN",
    "UNIVERSITAS NEGERI",
]

PTS_KEYWORDS = [
    "UNIVERSITAS MUHAMMADIYAH",
    "UNIVERSITAS ISLAM INDONESIA",
    "UNIVERSITAS BINA NUSANTARA",
    "UNIVERSITAS TELKOM",
    "UNIVERSITAS TRISAKTI",
    "UNIVERSITAS PELITA HARAPAN",
]

BUMN_KEYWORDS = [
    "PERTAMINA",
    "TELKOM INDONESIA",
    "BANK MANDIRI",
    "BANK RAKYAT INDONESIA",
    "BRI",
    "BANK NEGARA INDONESIA",
    "BNI",
    "PLN",
    "KAI",
    "ANGKASA PURA",
]

FOREIGN_UNIVERSITY_HINTS = [
    "UNIVERSITY OF",
    "COLLEGE OF",
    "NATIONAL UNIVERSITY OF",
    "TECHNICAL UNIVERSITY",
    "INSTITUTE OF TECHNOLOGY",
]
