"""Benchmark 5 Teknik Prompting LLM untuk Klasifikasi Tingkat Sertifikat.

Mengevaluasi:
1. Zero-Shot Prompting
2. Few-Shot Prompting
3. Chain-of-Thought (CoT)
4. Self-Consistency (Majority Voting, n_samples=3)
5. Iterative Prompting (Sequential Decomposition)

Mendukung backend:
- ollama: Ollama lokal (default llama3.1:8b)
- gemini: Google Gemini REST API (x-goog-api-key header)
- mock: Deterministic offline mock runner untuk pengujian struktur & dry-run

Penggunaan:
  uv run python -m tests.benchmark_prompting_tingkat --backend mock --limit 5
  uv run python -m tests.benchmark_prompting_tingkat --backend ollama --technique zero_shot
  uv run python -m tests.benchmark_prompting_tingkat --backend gemini --technique all
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Tambahkan root directory ke sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.prompting_tingkat import (
    TINGKAT_OPTIONS,
    PromptingResult,
    build_zero_shot_prompt,
    build_few_shot_prompt,
    build_cot_prompt,
    validate_tingkat,
    run_self_consistency,
    run_iterative_prompting,
)


@dataclass
class EvalRecord:
    filename: str
    gt_tingkat: str
    pred_tingkat: str | None
    is_match: bool
    needs_review: bool
    confidence: float
    technique: str
    latency_s: float
    raw_response: str
    metadata: dict[str, Any] = field(default_factory=dict)


def load_gt(csv_path: Path) -> list[dict[str, str]]:
    """Membaca file ground truth CSV secara fail-closed."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"File Ground Truth tidak ditemukan di {csv_path}. "
            f"Pastikan file ground truth tersedia atau set GT_CSV_PATH."
        )
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows

def load_ocr_texts_map(texts_source: Path) -> dict[str, str]:
    """Membaca teks OCR mentah dengan exact filename mapping (fail-closed bila bentrok/hilang)."""
    if not texts_source.exists():
        raise FileNotFoundError(f"Sumber teks OCR tidak ditemukan di: {texts_source}")

    texts_map: dict[str, str] = {}

    if texts_source.is_file():
        # Format marker file: ========== <filename> ==========
        content = texts_source.read_text(encoding="utf-8", errors="replace")
        parts = re.split(r"={5,}\s+([^=\n\r]+?)\s+={5,}", content)
        for i in range(1, len(parts), 2):
            fn = parts[i].strip()
            txt = parts[i + 1].strip()
            norm_fn = fn.lower()
            if norm_fn in texts_map and texts_map[norm_fn] != txt:
                raise ValueError(f"Deteksi duplikasi/konflik teks OCR untuk file: '{fn}'")
            texts_map[norm_fn] = txt
    elif texts_source.is_dir():
        for p in texts_source.glob("*.txt"):
            txt = p.read_text(encoding="utf-8", errors="replace").strip()
            norm_name = p.name.lower()
            texts_map[norm_name] = txt
            # Izinkan juga pencocokan jika nama file di GT berakhiran .pdf tapi di dir berakhiran .txt
            if norm_name.endswith(".txt"):
                pdf_variant = norm_name[:-4] + ".pdf"
                texts_map[pdf_variant] = txt

    return texts_map

def make_llm_runner(
    backend: str,
    ollama_host: str = "http://localhost:11434",
    ollama_model: str = "llama3.1:8b",
    gemini_model: str = "gemini-2.5-flash",
) -> Callable[[str, float], str]:
    """Factory provider-neutral LLM runner dengan fail-fast check."""
    if backend == "mock":
        def mock_runner(prompt: str, temperature: float = 0.0) -> str:
            # Harness plumbing test only - bukan untuk evaluasi akurasi
            lower = prompt.lower()
            if "lomba" in lower or "kompetisi" in lower or "contest" in lower:
                return "TINGKAT: Nasional\nLangkah 4: Nasional"
            if "dekan cup" in lower or "fakultas" in lower:
                return "TINGKAT: Fakultas\nLangkah 4: Fakultas"
            if "rektor" in lower or "universitas" in lower:
                return "TINGKAT: Universitas\nLangkah 4: Universitas"
            if "himpunan" in lower or "departemen" in lower:
                return "TINGKAT: Departemen/Program Studi\nLangkah 4: Departemen/Program Studi"
            if "international" in lower or "internasional" in lower:
                return "TINGKAT: Internasional\nLangkah 4: Internasional"
            return "TINGKAT: Lainnya"
        return mock_runner

    elif backend == "ollama":
        import urllib.request
        import urllib.error

        # Pre-check koneksi ke Ollama
        try:
            req = urllib.request.Request(f"{ollama_host}/api/tags")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                pass
        except Exception as e:
            raise ConnectionError(
                f"Ollama backend tidak aktif di {ollama_host}: {e}. "
                "Jalankan Ollama terlebih dahulu (misal: 'ollama serve' atau 'scripts/start_ollama.sh')."
            )

        def ollama_runner(prompt: str, temperature: float = 0.0) -> str:
            url = f"{ollama_host}/api/generate"
            payload = json.dumps({
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 300,
                },
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=45.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", "").strip()
            except Exception as e:
                return f"[OLLAMA_ERROR: {e}]"

        return ollama_runner

    elif backend == "gemini":
        from tests.gemini_client import GeminiClient, load_google_api_key

        api_key = load_google_api_key()
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY tidak ditemukan di environment atau .env.google. "
                "Set GOOGLE_API_KEY sebelum menjalankan benchmark dengan backend Gemini."
            )
        client = GeminiClient(api_key=api_key, default_model=gemini_model)

        def gemini_runner(prompt: str, temperature: float = 0.0) -> str:
            res = client.generate_text(prompt, model=gemini_model, temperature=temperature)
            if res.status != "success":
                return f"[GEMINI_ERROR: {res.error_message}]"
            return res.response_text.strip()

        return gemini_runner

    else:
        raise ValueError(f"Backend '{backend}' tidak dikenali. Pilih: mock, ollama, gemini.")


def evaluate_single(
    technique: str,
    raw_text: str,
    known_fields: dict[str, str],
    llm_func: Callable[[str, float], str],
) -> PromptingResult:
    """Mengevaluasi satu teknik prompting."""
    t0 = time.perf_counter()

    if technique == "zero_shot":
        prompt = build_zero_shot_prompt(raw_text, known_fields)
        resp = llm_func(prompt, 0.0)
        tingkat = validate_tingkat(resp)
        conf = 0.85 if tingkat else 0.0
        return PromptingResult(
            tingkat=tingkat,
            raw_response=resp,
            technique="zero_shot",
            confidence=conf,
            needs_review=bool(conf < 0.85 or tingkat in (None, "Lainnya")),
        )

    elif technique == "few_shot":
        prompt = build_few_shot_prompt(raw_text, known_fields)
        resp = llm_func(prompt, 0.0)
        tingkat = validate_tingkat(resp)
        conf = 0.85 if tingkat else 0.0
        return PromptingResult(
            tingkat=tingkat,
            raw_response=resp,
            technique="few_shot",
            confidence=conf,
            needs_review=bool(conf < 0.85 or tingkat in (None, "Lainnya")),
        )

    elif technique == "cot":
        prompt = build_cot_prompt(raw_text, known_fields)
        resp = llm_func(prompt, 0.0)
        tingkat = validate_tingkat(resp)
        conf = 0.85 if tingkat else 0.0
        return PromptingResult(
            tingkat=tingkat,
            raw_response=resp,
            technique="cot",
            confidence=conf,
            needs_review=bool(conf < 0.85 or tingkat in (None, "Lainnya")),
        )

    elif technique == "self_consistency":
        return run_self_consistency(raw_text, known_fields, llm_func, n_samples=3, temperature=0.5)

    elif technique == "iterative":
        return run_iterative_prompting(raw_text, known_fields, llm_func)

    else:
        raise ValueError(f"Teknik '{technique}' tidak dikenali.")


def run_benchmark(
    gt_path: Path,
    texts_path: Path,
    backend: str = "mock",
    techniques: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Menjalankan benchmark lengkap untuk teknik prompting."""
    records = load_gt(gt_path)
    if limit:
        records = records[:limit]

    # Load mapping teks OCR mentah secara ketat (fail-fast bila tidak ada)
    ocr_texts_map = load_ocr_texts_map(texts_path)

    selected_techniques = techniques or [
        "zero_shot",
        "few_shot",
        "cot",
        "self_consistency",
        "iterative",
    ]

    llm_func = make_llm_runner(backend)
    results_by_tech: dict[str, list[EvalRecord]] = {tech: [] for tech in selected_techniques}

    print(f"=== Menjalankan Benchmark Prompting Tingkat ===")
    print(f"Dataset: {gt_path.name} ({len(records)} baris)")
    print(f"Teks OCR Source: {texts_path}")
    print(f"Backend: {backend}")
    print(f"Teknik: {', '.join(selected_techniques)}")
    if backend == "mock":
        print("PERINGATAN: Backend mock HANYA untuk validasi struktur harness, BUKAN evaluasi kualitas model.")
    print("=" * 60)

    for i, row in enumerate(records, 1):
        filename = row.get("Nama File", f"doc_{i}").strip()
        gt_tingkat = (row.get("Tingkat") or "").strip()

        # Exact-map Nama File ke OCR artifact (tanpa fuzzy/stem guess)
        norm_key = filename.lower()
        if norm_key not in ocr_texts_map:
            raise FileNotFoundError(
                f"Teks OCR mentah tidak ditemukan untuk exact Nama File '{filename}' di {texts_path}. "
                f"Dilarang menggunakan metadata GT sebagai fallback!"
            )
        raw_text = ocr_texts_map[norm_key]

        # Invariant anti-leakage: known_fields TIDAK BOLEH diisi dari kolom GT!
        known_fields: dict[str, str] = {}

        for tech in selected_techniques:
            t0 = time.perf_counter()
            res = evaluate_single(tech, raw_text, known_fields, llm_func)
            lat = time.perf_counter() - t0

            is_match = (res.tingkat is not None) and (res.tingkat.upper() == gt_tingkat.upper())

            eval_rec = EvalRecord(
                filename=filename,
                gt_tingkat=gt_tingkat,
                pred_tingkat=res.tingkat,
                is_match=is_match,
                needs_review=res.needs_review,
                confidence=res.confidence,
                technique=tech,
                latency_s=lat,
                raw_response=res.raw_response,
                metadata=res.metadata,
            )
            results_by_tech[tech].append(eval_rec)
    # Hitung metrik per teknik
    summary: dict[str, Any] = {}
    for tech, evals in results_by_tech.items():
        total = len(evals)
        correct = sum(1 for e in evals if e.is_match)
        reviewed = sum(1 for e in evals if e.needs_review)
        accuracy = (correct / total) if total > 0 else 0.0
        review_rate = (reviewed / total) if total > 0 else 0.0
        avg_lat = sum(e.latency_s for e in evals) / total if total > 0 else 0.0

        # Analisis disagreement spesifik: GT Nasional vs Pred Fakultas, dan GT Fakultas vs Pred Nasional
        nasional_as_fakultas = sum(
            1 for e in evals if e.gt_tingkat == "Nasional" and e.pred_tingkat == "Fakultas"
        )
        fakultas_as_nasional = sum(
            1 for e in evals if e.gt_tingkat == "Fakultas" and e.pred_tingkat == "Nasional"
        )

        summary[tech] = {
            "total": total,
            "correct": correct,
            "accuracy": round(accuracy * 100, 2),
            "review_rate": round(review_rate * 100, 2),
            "avg_latency_s": round(avg_lat, 3),
            "nasional_misclassified_as_fakultas": nasional_as_fakultas,
            "fakultas_misclassified_as_nasional": fakultas_as_nasional,
        }

    # Cetak tabel ringkasan
    print("\n=== RINGKASAN HASIL BENCHMARK PROMPTING TINGKAT ===")
    print(f"{'Teknik':<18} | {'Accuracy':<10} | {'Review Rate':<12} | {'Nas->Fak':<10} | {'Fak->Nas':<10} | {'Avg Latency'}")
    print("-" * 80)
    for tech, stats in summary.items():
        print(
            f"{tech:<18} | {stats['accuracy']:>6.2f}%    | {stats['review_rate']:>8.2f}%    | "
            f"{stats['nasional_misclassified_as_fakultas']:>8}   | {stats['fakultas_misclassified_as_nasional']:>8}   | {stats['avg_latency_s']:.3f}s"
        )
    print("=" * 80)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark 5 Teknik Prompting Tingkat")
    parser.add_argument(
        "--gt-path",
        type=str,
        default=os.environ.get("GT_CSV_PATH", "Ground_Truth_Sertifikat_v9.csv"),
        help="Path ke file Ground Truth CSV",
    )
    parser.add_argument(
        "--texts-path",
        type=str,
        default=os.environ.get("GT_TEXTS_DIR", ""),
        help="Path ke file marker (_extracted.txt) atau direktori teks OCR mentah",
    )
    parser.add_argument(
        "--backend",
        type=str,
        choices=["mock", "ollama", "gemini"],
        default="mock",
        help="Backend LLM (mock, ollama, gemini)",
    )
    parser.add_argument(
        "--technique",
        type=str,
        default="all",
        help="Teknik prompting (all, zero_shot, few_shot, cot, self_consistency, iterative)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Batasi jumlah dokumen")
    args = parser.parse_args()

    if not args.texts_path:
        print("ERROR: --texts-path atau env GT_TEXTS_DIR wajib diisi untuk menentukan lokasi artefak teks OCR mentah.")
        sys.exit(1)

    gt_file = REPO_ROOT / args.gt_path if not Path(args.gt_path).is_absolute() else Path(args.gt_path)
    texts_file = REPO_ROOT / args.texts_path if not Path(args.texts_path).is_absolute() else Path(args.texts_path)

    techs = None
    if args.technique != "all":
        techs = [args.technique]

    run_benchmark(gt_file, texts_file, backend=args.backend, techniques=techs, limit=args.limit)

if __name__ == "__main__":
    main()
