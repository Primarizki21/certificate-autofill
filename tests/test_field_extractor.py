from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import field_needs_review, map_fields_to_form


def test_airnology_certificate_rules():
    text = """
    BADAN EKSEKUTIF MAHASISWA FAKULTAS TEKNOLOGI MAJU DAN MULTIDISIPLIN
    SERTIFIKAT
    No. 3994/B/UN3.FTMM/KM.04/2024
    HADYAN ADIRA PERDANA
    SEBAGAI
    PANITIA
    Dalam rangkaian kegiatan Airnology 3.0 yang diselenggarakan oleh
    Badan Eksekutif Mahasiswa (BEM) bekerja sama dengan Himpunan Mahasiswa (Hima)
    Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga
    Surabaya, 24 Agustus - 22 September 2024
    Dekan FTMM Universitas Airlangga
    """
    extracted = extract_certificate_fields(text)
    mapped = map_fields_to_form(extracted, "2024/2025 - Ganjil", "Sertifikat")

    assert mapped["jenis_kegiatan"].value == "Panitia Dalam Suatu Kegiatan Kemahasiswaan"
    assert mapped["tingkat"].value == "Fakultas"
    assert mapped["jenis_penyelenggara"].value == "PTN di Indonesia"
    assert mapped["waktu_mulai_pelaksanaan"].value == "24/08/2024"
    assert mapped["waktu_selesai_pelaksanaan"].value == "22/09/2024"
    assert mapped["nomor_bukti_fisik_nomor_sertifikasi"].value == "3994/B/UN3.FTMM/KM.04/2024"


def test_pkkmb_date_range_and_university_level():
    text = """
    UNIVERSITAS AIRLANGGA
    Atas Partisipasinya sebagai :
    PESERTA
    PENGENALAN KEHIDUPAN KAMPUS BAGI MAHASISWA BARU (PKKMB)
    UNIVERSITAS AIRLANGGA TAHUN AKADEMIK 2022/2023
    18 - 27 AGUSTUS 2022
    DIREKTUR KEMAHASISWAAN
    """
    extracted = extract_certificate_fields(text)
    mapped = map_fields_to_form(extracted, "2022/2023 - Ganjil", "Sertifikat")

    assert mapped["tingkat"].value == "Universitas"
    assert mapped["jenis_penyelenggara"].value == "PTN di Indonesia"
    assert mapped["waktu_mulai_pelaksanaan"].value == "18/08/2022"
    assert mapped["waktu_selesai_pelaksanaan"].value == "27/08/2022"


def test_extract_dates_airnology_interval_one_year():
    text = "Surabaya, 24 Agustus - 22 September 2024"
    fields = extract_certificate_fields(text)
    assert fields["waktu_mulai_pelaksanaan"].value == "24/08/2024"
    assert fields["waktu_selesai_pelaksanaan"].value == "22/09/2024"


def test_extract_dates_airnology_interval_without_dash():
    text = "Surabaya 24 Agustus 22 September 2024"
    fields = extract_certificate_fields(text)
    assert fields["waktu_mulai_pelaksanaan"].value == "24/08/2024"
    assert fields["waktu_selesai_pelaksanaan"].value == "22/09/2024"


def test_extract_dates_same_month_interval():
    text = "Pengenalan kegiatan 18 - 27 Agustus 2022"
    fields = extract_certificate_fields(text)
    assert fields["waktu_mulai_pelaksanaan"].value == "18/08/2022"
    assert fields["waktu_selesai_pelaksanaan"].value == "27/08/2022"

def test_date_interval_only_year_once_airnology_generic():
    text = "Surabaya, 24 Agustus - 22 September 2024"
    fields = extract_certificate_fields(text)
    assert fields["waktu_mulai_pelaksanaan"].value == "24/08/2024"
    assert fields["waktu_selesai_pelaksanaan"].value == "22/09/2024"


def test_missing_dates_do_not_require_review() -> None:
    assert field_needs_review("waktu_mulai_pelaksanaan", None, 0.0) is False
    assert field_needs_review("waktu_selesai_pelaksanaan", "", 0.0) is False
    assert field_needs_review("nomor_bukti_fisik_nomor_sertifikasi", None, 0.0) is True

def test_extract_role_kementerian_header_does_not_extract_menteri():
    from app.services.field_extractor import extract_role
    text = "KEMENTERIAN PENDIDIKAN, KEBUDAYAAN, RISET DAN TEKNOLOGI UNIVERSITAS NEGERI SURABAYA"
    assert extract_role(text) is None

def test_extract_role_juara_and_menteri():
    from app.services.field_extractor import extract_role
    text_juara = "DIBERIKAN KEPADA FAZIL ATAS PRESTASINYA SEBAGAI JUARA 1 LOMBA DATA SCIENCE"
    assert extract_role(text_juara) == "Juara 1"

    text_menteri = "DIBERIKAN KEPADA ATAS PENGABDIANNYA SEBAGAI MENTERI KOORDINATOR BEM"
    assert extract_role(text_menteri) == "MENTERI KOORDINATOR BEM"
