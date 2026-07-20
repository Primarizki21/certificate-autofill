from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_fields_to_form


def mapped(text: str):
    extracted = extract_certificate_fields(text)
    return map_fields_to_form(extracted, "2035/2036 - Genap", "Sertifikat")


def test_airnology_indonesian_interval():
    text = """No. 3994/B/UN3.FTMM/KM.04/2024
    HADYAN ADIRA PERDANA SEBAGAI PANITIA
    Dalam rangkaian kegiatan Airnology 3.0 yang diselenggarakan oleh Badan Eksekutif Mahasiswa (BEM) bekerja sama dengan Himpunan Mahasiswa (Hima)
    Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga
    Surabaya, 24 Agustus - 22 September 2024
    Dekan FTMM Universitas Airlangga"""
    m = mapped(text)
    assert m["waktu_mulai_pelaksanaan"].value == "24/08/2024"
    assert m["waktu_selesai_pelaksanaan"].value == "22/09/2024"
    assert m["jenis_penyelenggara"].value == "PTN di Indonesia"
    assert m["jenis_kegiatan"].value == "Panitia Dalam Suatu Kegiatan Kemahasiswaan"


def test_specta_english_interval():
    text = """Certificate Number: 5028/B/UN3.FTMM/KM.06.02/2024
    This certification is proudly presented to Hadyan Adira Perdana as a committee at SPECTA
    which held fromSeptember 21 to December7,2024 byHimatesda
    Dean of FTMM Unair"""
    m = mapped(text)
    assert m["waktu_mulai_pelaksanaan"].value == "21/09/2024"
    assert m["waktu_selesai_pelaksanaan"].value == "07/12/2024"
    assert m["nama_kegiatan_sertifikasi"].value == "SPECTA"
    assert m["penyelenggara_kegiatan"].value == "HIMATESDA"
    assert m["tingkat"].value == "Fakultas"
    assert m["jenis_penyelenggara"].value == "PTN di Indonesia"
    assert m["jenis_kegiatan"].value == "Panitia Dalam Suatu Kegiatan Kemahasiswaan"


def test_brief_single_date():
    text = """NOMOR: 5025/B/UN.3FTMM/KM.06.02/2024
    CERTIFICATE OF PARTICIPATION
    Atas partisipasinya dalam seminar Brief 2024 “Luxurious of the Successful Entrepreneurship with Igniting Ambition” yang diselenggarakan oleh HIMANO, Fakultas Teknologi Maju dan Multidisiplin pada 23 November 2024
    Dekan FTMM"""
    m = mapped(text)
    assert m["waktu_mulai_pelaksanaan"].value == "23/11/2024"
    assert m["waktu_selesai_pelaksanaan"].value == "23/11/2024"
    assert m["nama_kegiatan_sertifikasi"].value == "Brief 2024"
    assert m["prestasi_partisipasi_jabatan"].value == "Peserta"
    assert m["jenis_penyelenggara"].value == "PTN di Indonesia"


def test_kakiwima_single_date():
    text = """Nomor : 4408/B/UN3.FTMM/KM.06.02/2024
    SEBAGAI PANITIA
    Dalam kegiatan Talkshow Kakiwima dengan tema Mengasah Jiwa Kewirausahaan Mahasiswa di Era AI yang termasuk dalam rangkaian Program Kerja Kakiwima Kementerian Kewirausahaan dan Ekonomi Kreatif BEM FTMM pada tanggal 3 November 2024
    Dekan FTMM Universitas Airlangga"""
    m = mapped(text)
    assert m["waktu_mulai_pelaksanaan"].value == "03/11/2024"
    assert m["waktu_selesai_pelaksanaan"].value == "03/11/2024"
    assert m["nama_kegiatan_sertifikasi"].value == "Talkshow Kakiwima"
    assert m["jenis_kegiatan"].value == "Panitia Dalam Suatu Kegiatan Kemahasiswaan"


def test_hima_signature_with_explicit_airlangga_affiliation_maps_to_department_program():
    text = """NOMOR: 5025/B/UN.3FTMM/KM.06.02/2024
    CERTIFICATE OF PARTICIPATION
    Atas partisipasinya dalam seminar Brief 2024 yang diselenggarakan oleh HIMANO, Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga pada 23 November 2024
    Prof. Dr. Dwi Setyawan Dekan FTMM
    Pembina HIMANO Ketua HIMANO Ketua Pelaksana"""
    m = mapped(text)
    assert m["tingkat"].value == "Departemen/Program Studi"
    assert m["jenis_penyelenggara"].value == "PTN di Indonesia"


def test_hima_signature_with_only_ftmm_no_airlangga_maps_to_national():
    text = """NOMOR: 5025/B/UN.3FTMM/KM.06.02/2024
    CERTIFICATE OF PARTICIPATION
    Atas partisipasinya dalam seminar Brief 2024 yang diselenggarakan oleh HIMANO, Fakultas Teknologi Maju dan Multidisiplin pada 23 November 2024
    Prof. Dr. Dwi Setyawan Dekan FTMM
    Pembina HIMANO Ketua HIMANO Ketua Pelaksana"""
    m = mapped(text)
    assert m["tingkat"].value == "Nasional"


def test_hima_signature_without_airlangga_affiliation_maps_to_national():
    text = """SERTIFIKAT NOMOR 123/B/ABC/2024
    diberikan kepada Hadyan sebagai peserta seminar nasional pada tanggal 23 November 2024
    Pembina HIMA Ketua HIMA Ketua Pelaksana"""
    m = mapped(text)
    assert m["tingkat"].value == "Nasional"
