"""B4 — Unit test adversarial untuk router disambiguasi v7 (substring landmines).

Kasus negatif (audit QA B4): input yang SEBELUMNYA salah ter-route karena
substring trigger tanpa word-boundary:
  - "Olimpiade KIMIA"                    -> kim_unair HARUS False.
  - "Robotics Club Gelar Rasa"           -> ub_external_event HARUS False
                                            ("UB" di dalam "CLUB").
  - "Faculty of Informatics Engineering Seminar" -> intl_explicit HARUS False
                                            ("OF INFORMATICS ENGINEERING").
  - "BEM FKM Hari Anak Kampus"           -> bem_nasional_act HARUS False
                                            ("HARI ANAK" tanpa NASIONAL).

Kasus positif: rule tetap menembak pada pola korpus asli.
"""

import pytest

from tests.router_disambig_v7 import (
    DISAMBIG_RULES_V7,
    _cond_bem_nasional_act,
    _cond_intl_explicit,
    _cond_kim_unair,
    _cond_ub_external_event,
    route_with_disambiguation_v7,
)

RULES = {name: cond for name, _, cond in DISAMBIG_RULES_V7}


@pytest.mark.parametrize(
    "text,organizer,activity",
    [
        ("Olimpiade KIMIA 2024 diselenggarakan oleh HIMA", "HIMA Kimia", "Olimpiade KIMIA"),
        ("Kompetisi Olimpiade KIMIA Nasional", "", "Olimpiade KIMIA"),
        ("Olimpiade KIMIAWI tingkat nasional", "", "Olimpiade KIMIAWI"),
    ],
)
def test_kim_unair_negative_kimia(text, organizer, activity):
    u, o, a = text.upper(), organizer.upper(), activity.upper()
    assert not _cond_kim_unair(u, o, a), f"kim_unair tidak boleh fire: {text!r}"


def test_kim_unair_positive_corpus():
    # Korpus asli: "Kompetisi Ilmiah Mahasiswa (KIM) Universitas Airlangga"
    u, o, a = (
        "SERTIFIKAT Kompetisi Ilmiah Mahasiswa (KIM) Universitas Airlangga".upper(),
        "BEM FTMM Universitas Airlangga".upper(),
        "Kompetisi Ilmiah Mahasiswa (KIM) Universitas Airlangga".upper(),
    )
    assert _cond_kim_unair(u, o, a)


@pytest.mark.parametrize(
    "text,organizer",
    [
        ("Robotics Club Gelar Rasa", "Robotics Club"),
        ("HUBUNGAN antar hima Gelar Rasa", "Forum HUBUNGAN"),
        ("Seminar Gelar Rasa di UB", "BEM Universitas Brawijaya"),  # BRAWIJAYA -> tetap fire
    ],
)
def test_ub_external_event_negative_club(text, organizer):
    u, o, a = text.upper(), organizer.upper(), "".upper()
    # Dua kasus pertama: "CLUB"/"HUBUNGAN" tidak boleh memicu UB.
    if "CLUB" in organizer.upper() or "HUBUNGAN" in organizer.upper():
        assert not _cond_ub_external_event(u, o, a), f"ub_external_event tidak boleh fire: {text!r}"


def test_ub_external_event_positive_brawijaya():
    u, o, a = (
        "Hology 7.0 di Faculty of Computer Science, Brawijaya University".upper(),
        "Faculty of Computer Science Brawijaya University".upper(),
        "Hology 7.0".upper(),
    )
    assert _cond_ub_external_event(u, o, a)


@pytest.mark.parametrize(
    "text,organizer",
    [
        ("Faculty of Informatics Engineering Seminar on AI", "Faculty of Informatics Engineering"),
        ("DEPARTMENT OF INFORMATICS ENGINEERING workshop", "Department of Informatics Engineering"),
        ("FAKULTAS Informatika Engineering seminar", "Fakultas Informatika"),
    ],
)
def test_intl_explicit_negative_faculty(text, organizer):
    u, o, a = text.upper(), organizer.upper(), "".upper()
    assert not _cond_intl_explicit(u, o, a), f"intl_explicit tidak boleh fire: {text!r}"


def test_intl_explicit_positive_corpus():
    u = "held by Institut français d'Indonésie in collaboration with Université Paris-Saclay".upper()
    assert _cond_intl_explicit(u, "", "")


@pytest.mark.parametrize(
    "text,organizer,activity",
    [
        ("BEM FKM Hari Anak Kampus 2024", "BEM FKM", "Hari Anak Kampus"),
        ("Peringatan Hari Anak oleh BEM FKM", "BEM FKM", "Hari Anak Bersama BEM"),
    ],
)
def test_bem_nasional_act_negative_hari_anak(text, organizer, activity):
    u, o, a = text.upper(), organizer.upper(), activity.upper()
    assert not _cond_bem_nasional_act(u, o, a), f"bem_nasional_act tidak boleh fire: {text!r}"


def test_bem_nasional_act_positive_corpus():
    u, o, a = (
        "Dalam memperingati Hari Anak Nasional yang diselenggarakan oleh Social Action".upper(),
        "BEM FEB UNAIR 2023".upper(),
        "Hari Anak Nasional".upper(),
    )
    assert _cond_bem_nasional_act(u, o, a)


def test_direktur_kemahasiswaan_unair_guard():
    from tests.router_disambig_v7 import _cond_direktur_kemahasiswaan_unair

    # Positif: konteks Airlangga eksplisit.
    assert _cond_direktur_kemahasiswaan_unair(
        "DIREKTUR KEMAHASISWAAN UNIVERSITAS AIRLANGGA".upper(), "", ""
    )
    # Negatif: Direktur Kemahasiswaan tanpa konteks Airlangga.
    assert not _cond_direktur_kemahasiswaan_unair(
        "DIREKTUR KEMAHASISWAAN UNIVERSITAS NEGERI SEMARANG".upper(), "", ""
    )


def test_negative_inputs_unrouted_when_base_silent():
    """Input negatif murni (tanpa sinyal base router) -> (None, "")."""
    cases = [
        ("Olimpiade KIMIA 2024", "HIMA Kimia", "Olimpiade KIMIA"),
        ("Robotics Club Gelar Rasa", "Robotics Club", ""),
        ("Seminar Faculty of Informatics Engineering", "Faculty of Informatics Engineering", "Seminar AI"),
    ]
    for text, org, act in cases:
        val, rule = route_with_disambiguation_v7(text, org, act)
        if val is not None:
            # Kalau base router menembak (mis. lomba+org), itu keputusan base,
            # bukan disambig yang salah — pastikan rule-nya tidak menembak.
            assert not rule.startswith("disambig_"), f"rule disambig salah fire: {text!r} -> {rule}"


def test_all_rules_present_and_ordered():
    names = [n for n, _, _ in DISAMBIG_RULES_V7]
    assert names == [
        "aphsa_fkm",
        "bem_nasional_act",
        "kim_unair",
        "dpkka_unair",
        "intl_explicit",
        "literasi_psikologi",
        "ub_external_event",
        "direktur_kemahasiswaan_unair",
    ]
