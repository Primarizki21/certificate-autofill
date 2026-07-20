from dataclasses import dataclass
import json
import tempfile
from pathlib import Path
from typing import Any


@dataclass
class DoclingParseResult:
    markdown: str
    json_data: dict[str, Any]
    text: str
    error: str | None = None


def parse_with_docling(pdf_bytes: bytes, original_file_name: str = "document.pdf") -> DoclingParseResult:
    try:
        from docling.document_converter import DocumentConverter
    except Exception as exc:  # pragma: no cover - depends on optional runtime package
        return DoclingParseResult(markdown="", json_data={}, text="", error=f"Docling import failed: {exc}")

    suffix = Path(original_file_name).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        try:
            converter = DocumentConverter()
            result = converter.convert(tmp.name)
            document = result.document
            markdown = document.export_to_markdown() if hasattr(document, "export_to_markdown") else ""
            json_data: dict[str, Any] = {}
            if hasattr(document, "export_to_dict"):
                try:
                    json_data = document.export_to_dict()
                except Exception:
                    json_data = {}
            text = markdown_to_plain_text(markdown)
            return DoclingParseResult(markdown=markdown, json_data=json_data, text=text)
        except Exception as exc:  # pragma: no cover - depends on optional runtime models
            return DoclingParseResult(markdown="", json_data={}, text="", error=f"Docling parse failed: {exc}")


def markdown_to_plain_text(markdown: str) -> str:
    lines = []
    for line in markdown.splitlines():
        clean = line.replace("#", " ").replace("*", " ").replace("|", " ").strip()
        if clean:
            lines.append(clean)
    return "\n".join(lines)
