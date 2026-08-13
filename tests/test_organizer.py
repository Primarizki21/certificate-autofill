"""Unit test: port produksi normalisasi organizer & nomor (PROD-002).

Menjaga agar `backend/app/services/organizer_normalize.py` tetap konsisten
dengan spesifikasi handoff v29 (dengan KOREKSI R3): KEEP R0/PREFIX_HELD/R2/R3/
R6 + F1 alias + F3 BEM FKM + nomor D/E; SKIP R1/R4 (keputusan user); DROP R5.

Setiap kasus = input sintetik yang meniru teks korpus asli (PRIMARIZKI,
Venedict, 2954933, IRIS, SERTIF76, Gelar Rasa, Ananda, APHSA, BINARY, 2439919).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.config import settings
from app.services.organizer_normalize import normalize_nomor, normalize_organizer

UNAIR_RAW = "diselenggarakan oleh BEM FTMM Universitas Airlangga Surabaya"


def test_config_flag_default_off():
    assert settings.enable_organizer_normalization is False


# --- R0 + UNIV_TRAIL (has_unair gated) ---------------------------------------

def test_r0_strip_trailing_hima_setelah_konteks_univ():
    v = "Program Studi S1 Teknologi Sains Data Universitas Airlangga Himpunan Mahasiswa TSD"
    assert normalize_organizer(v, UNAIR_RAW) == "Program Studi S1 Teknologi Sains Data Universitas Airlangga"


def test_r0_hima_murni_tidak_di_strip():
    v = "Himpunan Mahasiswa S1 Akuntansi"
    assert normalize_organizer(v, UNAIR_RAW) == v


def test_univ_trail_expand_ke_airlangga():
    v = "Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas"
    assert normalize_organizer(v, UNAIR_RAW) == "Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga"


# --- PREFIX_HELD + R2 ---------------------------------------------------------

def test_prefix_held_strip():
    v = "Which Held From September 21 to December 7, 2024 by BEM FTMM Universitas Airlangga"
    assert normalize_organizer(v, UNAIR_RAW) == "BEM FTMM Universitas Airlangga"


def test_r2_library_class_strip():
    v = "Library Class BEM FEB UNAIR"
    assert normalize_organizer(v, UNAIR_RAW) == "BEM FEB UNAIR"


# --- R6 enrich kurang_lengkap -------------------------------------------------

def test_r6_himasada_fakultas():
    raw = "DEKAN FAKUETASILMU KOMPUTER KETUAHIMASADA"
    assert normalize_organizer("Himasada", raw) == "Himasada, Fakultas Ilmu Komputer"


def test_r6_iris_prepend():
    raw = "INNOVATIVERESEARCHOFINTELLIGENTSYSTEMIRIS Faculty of Advanced Technology"
    v = "Faculty of Advanced Technology and Multidisciplinary"
    assert normalize_organizer(v, raw) == "Innovative Research of Intelligent System (IRIS) Faculty of Advanced Technology and Multidisciplinary"


def test_r6_biro_prefix():
    v = "Penelitian dan Pengembangan Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis"
    raw = "Biro Penelitian dan Pengembangan Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga"
    assert normalize_organizer(v, raw) == "Biro " + v


def test_r6_dept_suffix_ocr_merge():
    v = "Faculty of Science and Technology"
    assert normalize_organizer(v, "INFORMATIONSYSTEMSSTUDYPROGRAM") == "Faculty of Science and Technology Information System Dept."


def test_r6_join_baris_beruntun_dan_typo():
    v = "Himpunan Mahasiswa Statistika"
    raw = "Himpunan Mahasiswa Statistika\nFakultasMatematika dan llmuPengetahuanAlam Universitas Gadjah Mada\nSertifikat"
    assert normalize_organizer(v, raw) == (
        "Himpunan Mahasiswa Statistika Fakultas Matematika dan ilmu Pengetahuan Alam Universitas Gadjah Mada"
    )


def test_r6_tidak_menyentuh_v_yang_sudah_lengkap():
    v = "Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga"
    raw = "Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga\nHimpunan Mahasiswa X"
    assert normalize_organizer(v, raw) == v


# --- F1 alias canonical + F3 BEM FKM ------------------------------------------

def test_f1_alias_is_dept():
    v = "Faculty of Science and Technology INFORMATION SYSTEMS DEPT."
    assert normalize_organizer(v, UNAIR_RAW) == "Faculty of Science and Technology Information System Dept."


def test_f1_alias_studisl():
    assert normalize_organizer("Program Studi sl Teknologi Sains Data", UNAIR_RAW) == "Program Studi S1 Teknologi Sains Data"


def test_f1_alias_aphsa():
    v = "DivisiKaprofAPHSA BEM FKM UniversitasAirlangga"
    assert normalize_organizer(v, UNAIR_RAW) == "Divisi Kaprof APHSA BEM FKM Universitas Airlangga"


def test_f1_alias_facultyof_ub():
    assert normalize_organizer("Faculty of Computer Science UB", UNAIR_RAW) == "Faculty of Computer Science Brawijaya University"


def test_f1_alias_majudan():
    v = "Fakultas Teknologi Majudan Multidisiplin Universitas Airlangga"
    assert normalize_organizer(v, UNAIR_RAW) == "Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga"


def test_f3_bem_fkm_suffix_konteks_unair():
    v = "Divisi Kaprof APHSA BEM FKM"
    assert normalize_organizer(v, UNAIR_RAW) == "Divisi Kaprof APHSA BEM FKM Universitas Airlangga"


def test_f3_tanpa_konteks_unair_tidak_di_suffix():
    v = "Divisi Kaprof APHSA BEM FKM"
    assert normalize_organizer(v, "diselenggarakan oleh BEM FKM Unisba Bandung") == v


# --- R1/R4/R5 SKIP (keputusan user handoff v29) + R3 KOREKSI -----------------

def test_r3_strip_sampai_oleh_membuka_alias_aphsa():
    # KOREKSI handoff v29: R3 bukan dead code — strip prefix "oleh" membuat
    # alias F1 APHSA match (1952296/2030335 = 2 fix, pola "Xoleh Divisi...").
    v = "Public Health Career Track2oleh Divisi Kaprof APHSABEMFKM Universitas Airlangga"
    assert normalize_organizer(v, UNAIR_RAW) == "Divisi Kaprof APHSA BEM FKM Universitas Airlangga"


def test_r1_suffix_faculty_skip():
    v = "Himpunan Mahasiswa TSD, Faculty of Science"
    assert normalize_organizer(v, UNAIR_RAW) == v


def test_r4_suffix_tanggal_skip():
    v = "BEM FTMM on July 30, 2023"
    assert normalize_organizer(v, UNAIR_RAW) == v


def test_r5_dash_jenjang_skip():
    v = "Himpunan Mahasiswa S-1 Akuntansi"
    assert normalize_organizer(v, UNAIR_RAW) == v


# --- normalize_nomor (D/E: SERT, dot, space, fallback raw) --------------------

def test_nomor_sert_pattern():
    # Prefix "SERT-" ikut tertangkap (identik replica tests / ORG-002).
    assert normalize_nomor("No. SERT-123/STF/PCR/2025") == "SERT-123/STF/PCR/2025"


def test_nomor_dot_pattern():
    # Perilaku identik replica tests (ORG-002): extract_certificate_number
    # pattern 3 menang sebelum DOT_PATTERN -> prefix "0101." terpotong.
    assert normalize_nomor("Nomor: 0101.17/STF/PCR/2025") == "17/STF/PCR/2025"


def test_nomor_un3_pattern_raw_text():
    assert normalize_nomor("No. 3497/B/UN3.FTMM/KM.04/2024") == "3497/B/UN3.FTMM/KM.04/2024"


def test_nomor_tanpa_match():
    assert normalize_nomor("Sertifikat tanpa nomor yang valid") is None
