from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_fields_to_form


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
