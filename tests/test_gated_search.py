"""Unit test suite for Gated Search Grounding (EXP-GATED-SEARCH-001)."""

import pytest
from app.services.field_extractor import ExtractedValue
from tests.benchmark_gated_search import (
    detect_explicit_level,
    evaluate_gated_search_hybrid,
)


class TestDetectExplicitLevel:
    def test_detects_tingkat_nasional(self):
        text = "Sertifikat ini diberikan sebagai Juara 1 Tingkat Nasional dalam Lomba Inovasi."
        lvl, pat, is_conf = detect_explicit_level(text)
        assert lvl == "Nasional"
        assert pat is not None and "Tingkat Nasional" in pat
        assert is_conf is False

    def test_detects_tingkatan_nasional(self):
        text = "Lomba karya tulis ilmiah mahasiswa pada tingkatan nasional tahun 2025."
        lvl, pat, is_conf = detect_explicit_level(text)
        assert lvl == "Nasional"
        assert pat is not None and "tingkatan nasional" in pat
        assert is_conf is False

    def test_detects_se_indonesia(self):
        text = "Kompetisi pemrograman terbuka mahasiswa se-Indonesia tahun 2025."
        lvl, pat, is_conf = detect_explicit_level(text)
        assert lvl == "Nasional"
        assert pat is not None and "se-Indonesia" in pat
        assert is_conf is False

    def test_detects_tingkat_fakultas(self):
        text = "Pemilihan Mahasiswa Berprestasi 2024 Tingkat Fakultas Teknologi Maju dan Multidisiplin."
        lvl, pat, is_conf = detect_explicit_level(text)
        assert lvl == "Fakultas"
        assert pat is not None and "Tingkat Fakultas" in pat
        assert is_conf is False

    def test_detects_tingkat_universitas(self):
        text = "Kegiatan seminar ilmiah skala universitas bertempat di Gedung Garuda Mukti."
        lvl, pat, is_conf = detect_explicit_level(text)
        assert lvl == "Universitas"
        assert pat is not None and "skala universitas" in pat
        assert is_conf is False

    def test_detects_tingkat_internasional(self):
        text = "Presented to keynote speaker in the international competition event 2024."
        lvl, pat, is_conf = detect_explicit_level(text)
        assert lvl == "Internasional"
        assert pat is not None and "international competition" in pat
        assert is_conf is False

    def test_detects_departemen_prodi(self):
        text = "Kegiatan upgrading pengurus himpunan tingkat program studi sistem informasi."
        lvl, pat, is_conf = detect_explicit_level(text)
        assert lvl == "Departemen/Program Studi"
        assert pat is not None and "tingkat program studi" in pat
        assert is_conf is False

    def test_returns_none_for_ambiguous_text(self):
        text = "Sertifikat diberikan kepada peserta lomba koding Data Slayer 2.0 diselenggarakan oleh HIMA."
        lvl, pat, is_conf = detect_explicit_level(text)
        assert lvl is None
        assert pat is None
        assert is_conf is False

    def test_handles_negation_guard(self):
        text = "Kegiatan ini bukan tingkat nasional melainkan kaderisasi internal."
        lvl, pat, is_conf = detect_explicit_level(text)
        assert lvl is None
        assert pat is None
        assert is_conf is False

    def test_detects_multi_level_conflict(self):
        text = "Acara perlombaan Tingkat Fakultas yang diadakan serentak dengan Tingkat Nasional."
        lvl, pat, is_conf = detect_explicit_level(text)
        assert is_conf is True
        assert lvl in ("Fakultas", "Nasional")
    def test_detects_transitional_menuju_as_conflict(self):
        text = "Kompetisi Tingkat Fakultas sekaligus seleksi menuju Tingkat Nasional"
        lvl, pat, is_conf = detect_explicit_level(text)
        assert is_conf is True
        assert lvl in ("Fakultas", "Nasional")


class TestEvaluateGatedSearchHybrid:
    def test_gated_bypass_on_explicit_level(self):
        raw = "Peserta Lomba Inovasi Mahasiswa Tingkat Nasional 2025"
        extracted, meta = evaluate_gated_search_hybrid(
            raw_text=raw,
            nama_kegiatan="Lomba Inovasi",
            penyelenggara="BEM",
            client=None,
            enable_search_fallback=True,
        )
        assert isinstance(extracted, ExtractedValue)
        assert extracted.value == "Nasional"
        assert extracted.confidence == 0.92
        assert extracted.source == "regex_explicit_gate"
        assert meta["gated_bypass"] is True
        assert meta["web_queries_count"] == 0
        assert meta["search_fee_idr"] == 0.0
        assert meta["needs_review"] is False

    def test_gated_conflict_triggers_review(self):
        raw = "Kompetisi Tingkat Fakultas yang diselenggarakan bersamaan dengan agenda Tingkat Nasional"
        extracted, meta = evaluate_gated_search_hybrid(
            raw_text=raw,
            nama_kegiatan="Seleksi Lomba",
            penyelenggara="BEM",
            client=None,
            enable_search_fallback=True,
        )
        assert isinstance(extracted, ExtractedValue)
        assert extracted.confidence == 0.60
        assert extracted.source == "regex_explicit_gate_conflict"
        assert meta["is_conflict"] is True
        assert meta["gated_bypass"] is False
        assert meta["needs_review"] is True

    def test_fallback_unresolved_when_client_none(self):
        raw = "Peserta Lomba Koding FIT Competition 2025 diselenggarakan oleh HMP SI UKSW"
        extracted, meta = evaluate_gated_search_hybrid(
            raw_text=raw,
            nama_kegiatan="FIT Competition",
            penyelenggara="HMP SI UKSW",
            client=None,
            enable_search_fallback=False,
        )
        assert isinstance(extracted, ExtractedValue)
        assert extracted.value is None
        assert extracted.confidence == 0.0
        assert extracted.source == "fallback_unresolved"
        assert meta["gated_bypass"] is False
        assert meta["needs_review"] is True
