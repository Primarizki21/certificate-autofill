from __future__ import annotations

from pathlib import Path

from app.services.aucc_catalog import (
    Kegiatan2LookupRow,
    MasterKegiatanRule,
    load_aucc_catalog,
)


def test_load_aucc_catalog_parses_nullable_rows_and_rules(tmp_path: Path) -> None:
    snapshot = tmp_path / "aucc.sql"
    snapshot.write_text(
        "\n".join(
            (
                'INSERT INTO "aucc"."kegiatan_2" VALUES (9001, 41, NULL, 6);',
                'INSERT INTO "aucc"."master_kegiatan_rule" VALUES '
                "(1, 26, 1, 41, NULL, 6, 'Sert/SK/SP', 9001, true, "
                "'2026-09-14 02:22:42+07', '2026-09-14 02:22:42+07');",
            )
        ),
        encoding="utf-8",
    )

    catalog = load_aucc_catalog(snapshot)

    assert catalog.kegiatan2_rows == (Kegiatan2LookupRow(9001, 41, None, 6),)
    assert catalog.master_rules == (
        MasterKegiatanRule(
            source_no=26,
            id_kelompok_kegiatan=1,
            id_kegiatan_1=41,
            id_tingkat=None,
            id_jabatan_prestasi=6,
            dasar_penilaian="Sert/SK/SP",
            id_kegiatan_2=9001,
        ),
    )
