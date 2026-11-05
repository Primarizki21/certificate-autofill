"""Ekspor artefak eksperimen dalam 5 format wajib.

Dipisah agar empat runner evaluasi produksi tidak menduplikasi penulisan
CSV/JSONL/XLSX/JSON/Markdown.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from openpyxl import Workbook


def prepare_output_dir(path: str | Path, force: bool = False) -> Path:
    output_dir = Path(path)
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise SystemExit(
            f"{output_dir} sudah berisi artefak. Gunakan folder eksperimen baru "
            "atau berikan --force secara eksplisit."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path = Path(path)
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: str | Path, records: Iterable[Mapping[str, Any]]) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)


def write_xlsx(path: str | Path, sheets: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(title=name[:31])
        headers: list[str] = []
        for row in rows:
            for key in row:
                if key not in headers:
                    headers.append(key)
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(header) for header in headers])
    workbook.save(path)


def write_summary(path: str | Path, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def write_bundle(
    output_dir: str | Path,
    *,
    rows: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, Any],
    manifest: Mapping[str, Any],
    summary: str,
    xlsx_sheets: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    force: bool = False,
) -> Path:
    """Tulis 5 format: CSV, JSONL, XLSX, JSON, Markdown."""
    directory = prepare_output_dir(output_dir, force=force)
    write_csv(directory / "variant_comparisons.csv", rows)
    write_jsonl(directory / "per_cert_results.jsonl", records)
    write_json(directory / "metrics.json", metrics)
    write_json(directory / "manifest.json", manifest)
    write_xlsx(directory / "results.xlsx", xlsx_sheets or {"Ringkasan": rows})
    write_summary(directory / "summary.md", summary)
    return directory
