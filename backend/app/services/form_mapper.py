import re

from app.master_data import BUMN_KEYWORDS, FOREIGN_UNIVERSITY_HINTS, FORM_OPTIONS, PTN_KEYWORDS, PTS_KEYWORDS
from app.services.field_extractor import ExtractedValue


def map_fields_to_form(extracted: dict[str, ExtractedValue], tahun_akademik: str, bukti_fisik: str) -> dict[str, ExtractedValue]:
    full_text = (extracted.get("full_text") or ExtractedValue("", 0, "")).value or ""
    upper = full_text.upper()
    raw_role = (extracted.get("raw_role") or ExtractedValue(None, 0, "")).value or ""
    role_upper = raw_role.upper()
    activity = (extracted.get("nama_kegiatan_sertifikasi") or ExtractedValue("", 0, "")).value or ""
    organizer = (extracted.get("penyelenggara_kegiatan") or ExtractedValue("", 0, "")).value or ""

    mapped: dict[str, ExtractedValue] = {}
    mapped["tahun_akademik"] = ExtractedValue(tahun_akademik, 1.0, "user_input")
    mapped["bukti_fisik"] = ExtractedValue(bukti_fisik or "Sertifikat", 1.0, "user_input")

    kelompok, jenis = map_kelompok_dan_jenis(upper, role_upper, activity, organizer)
    mapped["kelompok_kegiatan"] = ExtractedValue(kelompok, 0.86, "rule_mapper")
    mapped["jenis_kegiatan"] = ExtractedValue(jenis, 0.86, "rule_mapper")

    tingkat = map_tingkat(upper)
    mapped["tingkat"] = ExtractedValue(tingkat, 0.88 if tingkat in ["Fakultas", "Universitas", "Departemen/Program Studi", "UKM"] else 0.70, "rule_mapper")

    jabatan = map_jabatan(raw_role)
    mapped["prestasi_partisipasi_jabatan"] = ExtractedValue(jabatan, 0.84 if jabatan else 0.0, "rule_mapper")

    passthrough_fields = [
        "nama_kegiatan_sertifikasi",
        "waktu_mulai_pelaksanaan",
        "waktu_selesai_pelaksanaan",
        "penyelenggara_kegiatan",
        "nomor_bukti_fisik_nomor_sertifikasi",
    ]
    for field in passthrough_fields:
        mapped[field] = extracted.get(field, ExtractedValue(None, 0.0, "missing"))

    jenis_penyelenggara = map_jenis_penyelenggara(upper, tingkat)
    mapped["jenis_penyelenggara"] = ExtractedValue(jenis_penyelenggara, 0.90, "rule_mapper_strict")

    return validate_with_needs_review(mapped)


def map_kelompok_dan_jenis(upper: str, role_upper: str, activity: str, organizer: str) -> tuple[str, str]:
    activity_upper = (activity or "").upper()
    organizer_upper = (organizer or "").upper()

    if "PKKMB" in upper or "PENGENALAN KEHIDUPAN KAMPUS" in upper:
        return "Kegiatan Wajib Universitas", "Peserta PKKMB"

    # Panitia/committee harus diprioritaskan sebelum keyword organisasi, karena sertifikat
    # panitia sering memuat BEM/HIMA/Student Association sebagai penyelenggara.
    if any(k in role_upper for k in ["PANITIA", "COMMITTEE"]):
        return "Kegiatan Bidang Organisasi dan Kepemimpinan", "Panitia Dalam Suatu Kegiatan Kemahasiswaan"

    if any(k in role_upper for k in ["MENTERI", "KETUA", "SEKRETARIS", "ANGGOTA", "PENGURUS"]):
        return "Kegiatan Bidang Organisasi dan Kepemimpinan", "Pengurus Organisasi"

    # Seminar/talkshow/workshop dengan status peserta tidak boleh otomatis menjadi
    # Pengurus Organisasi hanya karena penyelenggaranya HIMA/BEM. Prioritas konteks
    # kegiatan ditempatkan sebelum keyword organisasi penyelenggara.
    if any(k in upper for k in ["SEMINAR", "TALKSHOW", "WORKSHOP", "WEBINAR", "LOMBA", "COMPETITION", "BRIEF", "SPECTA"]):
        return "Kegiatan Bidang Penalaran dan Keilmuan", "--"

    if any(k in upper for k in ["KEPENGURUSAN", "ORGANISASI", "BEM", "HIMA", "STUDENT ASSOCIATION"]):
        return "Kegiatan Bidang Organisasi dan Kepemimpinan", "Pengurus Organisasi"

    return "Kegiatan Lainnya", "--"


def map_tingkat(upper_text: str) -> str:
    """Map certificate scope/level to the form's Tingkat field.

    Rule order matters. For student association certificates, HIMA/IM context in the
    signature area is more specific than generic Faculty/Dean text, because many
    department/program-study associations still use faculty dean signatures.
    """
    # Direktur Kemahasiswaan biasanya level universitas; prioritaskan sebelum aturan lain.
    if "DIREKTUR KEMAHASISWAAN" in upper_text or "DIRECTOR OF STUDENT" in upper_text:
        return "Universitas"

    # Aturan dari kebutuhan form:
    # - Jika ada HIMA/Himpunan Mahasiswa/IM/Ikatan Mahasiswa pada konteks tanda tangan
    #   dan dokumen punya konteks/logo Universitas Airlangga, levelnya Departemen/Program Studi.
    # - Jika konteks HIMA/IM ada tetapi tidak ada konteks/logo Universitas Airlangga,
    #   levelnya Nasional.
    if has_student_association_signature_context(upper_text):
        if has_airlangga_affiliation_context(upper_text):
            return "Departemen/Program Studi"
        return "Nasional"

    # Program studi/departemen lebih spesifik daripada fakultas.
    if any(k in upper_text for k in ["PROGRAM STUDI", "DEPARTEMEN", "DEPARTMENT", "STUDY PROGRAM"]):
        return "Departemen/Program Studi"
    if any(k in upper_text for k in ["DEKAN", "DEAN", "FAKULTAS", "FACULTY", "FTMM", "FAKULTAS TEKNOLOGI MAJU"]):
        return "Fakultas"
    if any(k in upper_text for k in ["UKM", "UNIT KEGIATAN MAHASISWA"]):
        return "UKM"
    if any(k in upper_text for k in ["UNIVERSITAS", "UNIVERSITY", "UNAIR", "AIRLANGGA"]):
        return "Universitas"
    return "Nasional"


def has_airlangga_affiliation_context(upper_text: str) -> bool:
    """Detect explicit Universitas Airlangga/UNAIR context only.

    For the HIMA/IM/Ikatan Mahasiswa -> Tingkat rule, FTMM/Fakultas text is
    intentionally not enough. The rule requires explicit Universitas Airlangga
    or UNAIR evidence so that HIMA/IM certificates without that context map to
    Nasional.
    """
    airlangga_markers = [
        "UNIVERSITAS AIRLANGGA",
        "UNIVERSITAS AIRLANGCA",  # common OCR confusion
        "UNAIR",
        "AIRLANGGA",
    ]
    return any(marker in upper_text for marker in airlangga_markers)


def has_student_association_signature_context(upper_text: str) -> bool:
    """Detect HIMA/IM/student association terms in signature-like context.

    This intentionally does not treat every body mention of "Himpunan Mahasiswa" as
    signature context. It looks for association terms near signer roles such as
    Ketua/Pembina/President/Chief/Coordinator, or explicit English signature wording.
    """
    association_patterns = [
        r"HIMA[A-Z0-9]*",                 # HIMA, HIMANO, HIMATESDA, etc.
        r"HIMPUNAN\s+MAHASISWA",
        r"IKATAN\s+MAHASISWA",
        r"(?<![A-Z0-9])IM(?![A-Z0-9])",
        r"STUDENT\s+ASSOCIATION",
    ]
    signer_patterns = [
        r"KETUA",
        r"PEMBINA",
        r"PRESIDEN",
        r"PRESIDENT",
        r"CHIEF",
        r"KOORDINATOR",
        r"COORDINATOR",
        r"DEWAN",
    ]
    association = r"(?:" + "|".join(association_patterns) + r")"
    signer = r"(?:" + "|".join(signer_patterns) + r")"

    # Signature phrases normally put signer role close to organization name, but OCR
    # order can be swapped, so check both directions.
    if re.search(signer + r".{0,90}" + association, upper_text, flags=re.DOTALL):
        return True
    if re.search(association + r".{0,90}" + signer, upper_text, flags=re.DOTALL):
        return True

    # Some English certificates put only "President of Student Association" under the signature.
    if "PRESIDENT OF STUDENT ASSOCIATION" in upper_text or "CHIEF EXECUTIVE" in upper_text and re.search(association, upper_text):
        return True
    return False


def map_jabatan(raw_role: str | None) -> str | None:
    if not raw_role:
        return None
    role = raw_role.upper()
    if "COMMITTEE" in role or "PANITIA" in role:
        return "Panitia"
    if "PARTICIPANT" in role or "PESERTA" in role or "PARTISIPASI" in role:
        return "Peserta"
    if "WAKIL" in role and "KETUA" in role:
        return "Wakil Ketua"
    if "KETUA" in role:
        return "Ketua"
    if "SEKRETARIS" in role:
        return "Sekretaris"
    if "MENTERI" in role or "KOORDINATOR" in role or "KEPALA" in role or "MINISTER" in role:
        return "Pengurus Inti Lain"
    if "ANGGOTA" in role:
        return "Anggota Pengurus"
    return raw_role.title()


def map_jenis_penyelenggara(upper_text: str, tingkat: str | None = None) -> str:
    tingkat = tingkat or ""

    # Aturan ketat dari kebutuhan form:
    # - Tingkat Fakultas / Departemen / UKM adalah kegiatan internal kampus -> PTN Indonesia.
    # - Tingkat Internasional -> PT di luar negeri.
    if tingkat in {"Fakultas", "Departemen/Program Studi", "UKM", "Universitas"}:
        return "PTN di Indonesia"
    if tingkat == "Internasional":
        return "PT di luar negeri"

    if "KEMENTERIAN" in upper_text or "KEMENTERIAN NEGARA" in upper_text:
        return "Kementerian Negara"

    # Prioritaskan kampus sebelum sponsor/BUMN. Sertifikat mahasiswa sering punya sponsor logo,
    # tetapi penyelenggaranya tetap kampus/organisasi kampus.
    if any(contains_keyword(upper_text, keyword) for keyword in PTN_KEYWORDS) or any(
        k in upper_text for k in ["UNIVERSITAS AIRLANGGA", "UNIVERSITAS AIRLANGCA", "UNAIR", "AIRLANGGA"]
    ):
        return "PTN di Indonesia"
    if any(contains_keyword(upper_text, keyword) for keyword in PTS_KEYWORDS):
        return "PTS di Indonesia"
    if any(contains_keyword(upper_text, keyword) for keyword in FOREIGN_UNIVERSITY_HINTS) and "INDONESIA" not in upper_text:
        return "PT di luar negeri"
    if any(contains_keyword(upper_text, keyword) for keyword in BUMN_KEYWORDS):
        return "BUMN"
    return "Lembaga/Yayasan lain"


def contains_keyword(upper_text: str, keyword: str) -> bool:
    escaped = re.escape(keyword.upper())
    if len(keyword) <= 4 or " " not in keyword:
        return bool(re.search(rf"(?<![A-Z0-9]){escaped}(?![A-Z0-9])", upper_text))
    return keyword.upper() in upper_text


def validate_with_needs_review(fields: dict[str, ExtractedValue]) -> dict[str, ExtractedValue]:
    required_fields = {
        "kelompok_kegiatan",
        "jenis_kegiatan",
        "tingkat",
        "prestasi_partisipasi_jabatan",
        "nama_kegiatan_sertifikasi",
        "waktu_mulai_pelaksanaan",
        "waktu_selesai_pelaksanaan",
        "jenis_penyelenggara",
        "penyelenggara_kegiatan",
        "nomor_bukti_fisik_nomor_sertifikasi",
    }
    for key in required_fields:
        if key not in fields:
            fields[key] = ExtractedValue(None, 0.0, "missing")
    return fields


def field_needs_review(field_name: str, value: str | None, confidence: float) -> bool:
    if field_name in {"tahun_akademik", "bukti_fisik"}:
        return False
    if not value:
        return True
    return confidence < 0.80
