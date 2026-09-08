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
    LLMCallMeta,
    PromptingResult,
    _extract_meta,
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
    prompt_tokens: int = 0
    candidates_tokens: int = 0
    cached_tokens: int = 0
    thoughts_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    cost_idr: float = 0.0
    web_queries: list[str] = field(default_factory=list)
    raw_response: str = ""
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
    gemini_model: str = "gemini-3.1-flash-lite",
    enable_grounding: bool = False,
) -> Callable[[str, float], LLMCallMeta]:
    """Factory provider-neutral LLM runner dengan fail-fast check dan per-call token accounting."""
    if backend == "mock":
        def mock_runner(prompt: str, temperature: float = 0.0) -> LLMCallMeta:
            lower = prompt.lower()
            if "lomba" in lower or "kompetisi" in lower or "contest" in lower:
                ans = "TINGKAT: Nasional\nLangkah 4: Nasional"
            elif "dekan cup" in lower or "fakultas" in lower:
                ans = "TINGKAT: Fakultas\nLangkah 4: Fakultas"
            elif "rektor" in lower or "universitas" in lower:
                ans = "TINGKAT: Universitas\nLangkah 4: Universitas"
            elif "himpunan" in lower or "departemen" in lower:
                ans = "TINGKAT: Departemen/Program Studi\nLangkah 4: Departemen/Program Studi"
            elif "international" in lower or "internasional" in lower:
                ans = "TINGKAT: Internasional\nLangkah 4: Internasional"
            else:
                ans = "TINGKAT: Lainnya"
            return LLMCallMeta(
                text=ans,
                prompt_tokens=len(prompt) // 4,
                candidates_tokens=len(ans) // 4,
                total_tokens=(len(prompt) + len(ans)) // 4,
            )
        return mock_runner

    elif backend == "ollama":
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(f"{ollama_host}/api/tags")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                pass
        except Exception as e:
            raise ConnectionError(
                f"Ollama backend tidak aktif di {ollama_host}: {e}. "
                "Jalankan Ollama terlebih dahulu (misal: 'ollama serve' atau 'scripts/start_ollama.sh')."
            )

        def ollama_runner(prompt: str, temperature: float = 0.0) -> LLMCallMeta:
            url = f"{ollama_host}/api/generate"
            payload = json.dumps({
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 150,
                },
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=45.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                p_tok = int(data.get("prompt_eval_count") or (len(prompt) // 4))
                c_tok = int(data.get("eval_count") or 10)
                return LLMCallMeta(
                    text=data.get("response", "").strip(),
                    prompt_tokens=p_tok,
                    candidates_tokens=c_tok,
                    total_tokens=p_tok + c_tok,
                )
            except Exception as e:
                return LLMCallMeta(text=f"[OLLAMA_ERROR: {e}]")

        return ollama_runner

    elif backend == "gemini":
        from tests.gemini_client import GeminiClient, load_google_api_key

        api_key = load_google_api_key()
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY tidak ditemukan di environment atau .env. "
                "Set GOOGLE_API_KEY sebelum menjalankan benchmark dengan backend Gemini."
            )
        client = GeminiClient(api_key=api_key, default_model=gemini_model)

        def gemini_runner(prompt: str, temperature: float = 0.0) -> LLMCallMeta:
            res = client.generate_text(
                prompt,
                model=gemini_model,
                temperature=temperature,
                enable_grounding=enable_grounding,
            )
            if res.status != "success":
                return LLMCallMeta(
                    text=f"[GEMINI_ERROR: {res.error_message}]",
                    prompt_tokens=res.prompt_tokens,
                    candidates_tokens=res.candidates_tokens,
                    cached_tokens=res.cached_tokens,
                    thoughts_tokens=res.thoughts_tokens,
                    total_tokens=res.total_tokens,
                    cost_usd=res.cost_usd,
                    cost_idr=res.cost_idr,
                    web_search_queries=res.web_search_queries,
                )
            return LLMCallMeta(
                text=res.response_text.strip(),
                prompt_tokens=res.prompt_tokens,
                candidates_tokens=res.candidates_tokens,
                cached_tokens=res.cached_tokens,
                thoughts_tokens=res.thoughts_tokens,
                total_tokens=res.total_tokens,
                cost_usd=res.cost_usd,
                cost_idr=res.cost_idr,
                web_search_queries=res.web_search_queries,
            )

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
        call_res = llm_func(prompt, 0.0)
        meta = _extract_meta(call_res)
        tingkat = validate_tingkat(meta.text)
        conf = 0.85 if tingkat else 0.0
        return PromptingResult(
            tingkat=tingkat,
            raw_response=meta.text,
            technique="zero_shot",
            confidence=conf,
            needs_review=bool(conf < 0.85 or tingkat in (None, "Lainnya")),
            prompt_tokens=meta.prompt_tokens,
            candidates_tokens=meta.candidates_tokens,
            cached_tokens=meta.cached_tokens,
            thoughts_tokens=meta.thoughts_tokens,
            total_tokens=meta.total_tokens,
            cost_usd=meta.cost_usd,
            cost_idr=meta.cost_idr,
            web_search_queries=meta.web_search_queries,
        )

    elif technique == "few_shot":
        prompt = build_few_shot_prompt(raw_text, known_fields)
        call_res = llm_func(prompt, 0.0)
        meta = _extract_meta(call_res)
        tingkat = validate_tingkat(meta.text)
        conf = 0.85 if tingkat else 0.0
        return PromptingResult(
            tingkat=tingkat,
            raw_response=meta.text,
            technique="few_shot",
            confidence=conf,
            needs_review=bool(conf < 0.85 or tingkat in (None, "Lainnya")),
            prompt_tokens=meta.prompt_tokens,
            candidates_tokens=meta.candidates_tokens,
            cached_tokens=meta.cached_tokens,
            thoughts_tokens=meta.thoughts_tokens,
            total_tokens=meta.total_tokens,
            cost_usd=meta.cost_usd,
            cost_idr=meta.cost_idr,
            web_search_queries=meta.web_search_queries,
        )

    elif technique == "cot":
        prompt = build_cot_prompt(raw_text, known_fields)
        call_res = llm_func(prompt, 0.0)
        meta = _extract_meta(call_res)
        tingkat = validate_tingkat(meta.text)
        conf = 0.85 if tingkat else 0.0
        return PromptingResult(
            tingkat=tingkat,
            raw_response=meta.text,
            technique="cot",
            confidence=conf,
            needs_review=bool(conf < 0.85 or tingkat in (None, "Lainnya")),
            prompt_tokens=meta.prompt_tokens,
            candidates_tokens=meta.candidates_tokens,
            cached_tokens=meta.cached_tokens,
            thoughts_tokens=meta.thoughts_tokens,
            total_tokens=meta.total_tokens,
            cost_usd=meta.cost_usd,
            cost_idr=meta.cost_idr,
            web_search_queries=meta.web_search_queries,
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
    mapping_path: Path | None = None,
    backend: str = "mock",
    techniques: list[str] | None = None,
    limit: int | None = None,
    output_dir: Path | None = None,
    gemini_model: str = "gemini-3.1-flash-lite",
    enable_grounding: bool = False,
) -> dict[str, Any]:
    """Menjalankan benchmark lengkap untuk teknik prompting."""
    records = load_gt(gt_path)
    if limit:
        records = records[:limit]

    # Load mapping teks OCR mentah secara ketat (fail-fast bila tidak ada)
    ocr_texts_map = load_ocr_texts_map(texts_path)

    filename_map: dict[str, str] = {}
    if mapping_path and mapping_path.exists():
        filename_map = json.loads(mapping_path.read_text(encoding="utf-8"))

    selected_techniques = techniques or [
        "zero_shot",
        "few_shot",
        "cot",
        "self_consistency",
        "iterative",
    ]

    llm_func = make_llm_runner(backend, gemini_model=gemini_model, enable_grounding=enable_grounding)
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
        orig_filename = row.get("Nama File", f"doc_{i}").strip()
        target_filename = filename_map.get(orig_filename, orig_filename)
        gt_tingkat = (row.get("Tingkat") or "").strip()

        # Exact-map Nama File ke OCR artifact (tanpa fuzzy/stem guess)
        norm_key = target_filename.lower()
        if norm_key not in ocr_texts_map:
            raise FileNotFoundError(
                f"Teks OCR mentah tidak ditemukan untuk exact Nama File '{target_filename}' di {texts_path}. "
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
                filename=orig_filename,
                gt_tingkat=gt_tingkat,
                pred_tingkat=res.tingkat,
                is_match=is_match,
                needs_review=res.needs_review,
                confidence=res.confidence,
                technique=tech,
                latency_s=lat,
                prompt_tokens=res.prompt_tokens,
                candidates_tokens=res.candidates_tokens,
                cached_tokens=res.cached_tokens,
                thoughts_tokens=res.thoughts_tokens,
                total_tokens=res.total_tokens,
                cost_usd=res.cost_usd,
                cost_idr=res.cost_idr,
                web_queries=res.web_search_queries,
                raw_response=res.raw_response,
                metadata={**res.metadata, "call_metrics": res.call_metrics},
            )
            results_by_tech[tech].append(eval_rec)

            # Checkpoint per row bila output_dir disediakan
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
                ckpt_path = output_dir / "checkpoint_details.jsonl"
                with open(ckpt_path, "a", encoding="utf-8") as f_ckpt:
                    f_ckpt.write(json.dumps({
                        "filename": orig_filename,
                        "technique": tech,
                        "gt_tingkat": gt_tingkat,
                        "pred_tingkat": res.tingkat,
                        "is_match": is_match,
                        "needs_review": res.needs_review,
                        "confidence": res.confidence,
                        "latency_s": round(lat, 3),
                        "prompt_tokens": res.prompt_tokens,
                        "candidates_tokens": res.candidates_tokens,
                        "cached_tokens": res.cached_tokens,
                        "thoughts_tokens": res.thoughts_tokens,
                        "total_tokens": res.total_tokens,
                        "cost_usd": res.cost_usd,
                        "cost_idr": res.cost_idr,
                        "web_queries": res.web_search_queries,
                    }) + "\n")

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

        tot_p_tokens = sum(e.prompt_tokens for e in evals)
        tot_c_tokens = sum(e.candidates_tokens for e in evals)
        tot_cached_tokens = sum(e.cached_tokens for e in evals)
        tot_thoughts_tokens = sum(e.thoughts_tokens for e in evals)
        tot_tokens = sum(e.total_tokens for e in evals)
        tot_cost_usd = sum(e.cost_usd for e in evals)
        tot_cost_idr = sum(e.cost_idr for e in evals)
        tot_web_queries = sum(len(e.web_queries) for e in evals)

        summary[tech] = {
            "total": total,
            "correct": correct,
            "accuracy": round(accuracy * 100, 2),
            "review_rate": round(review_rate * 100, 2),
            "avg_latency_s": round(avg_lat, 3),
            "total_prompt_tokens": tot_p_tokens,
            "total_candidates_tokens": tot_c_tokens,
            "total_cached_tokens": tot_cached_tokens,
            "total_thoughts_tokens": tot_thoughts_tokens,
            "total_tokens": tot_tokens,
            "avg_tokens_per_doc": round(tot_tokens / total, 1) if total > 0 else 0,
            "total_cost_usd": round(tot_cost_usd, 5),
            "total_cost_idr": round(tot_cost_idr, 2),
            "total_web_queries": tot_web_queries,
            "nasional_misclassified_as_fakultas": nasional_as_fakultas,
            "fakultas_misclassified_as_nasional": fakultas_as_nasional,
        }

    # Cetak tabel ringkasan
    print("\n=== RINGKASAN HASIL BENCHMARK PROMPTING TINGKAT ===")
    print(f"{'Teknik':<18} | {'Accuracy':<9} | {'Review Rate':<11} | {'Tokens (In/Out)':<18} | {'Cost (IDR)':<10} | {'Avg Latency'}")
    print("-" * 88)
    for tech, stats in summary.items():
        tokens_str = f"{stats['total_prompt_tokens']}/{stats['total_candidates_tokens']}"
        print(
            f"{tech:<18} | {stats['accuracy']:>6.2f}%   | {stats['review_rate']:>8.2f}%   | "
            f"{tokens_str:>16}   | Rp{stats['total_cost_idr']:>7.2f}  | {stats['avg_latency_s']:.3f}s"
        )
    print("=" * 88)
    # Simpan artefak dokumentasi jika output_dir dispesifikasikan
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        # 1. Summary JSON
        summary_file = output_dir / "benchmark_summary.json"
        summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        # 2. Evaluation Details CSV
        details_file = output_dir / "evaluation_details.csv"
        with open(details_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Nama File", "Teknik", "GT Tingkat", "Pred Tingkat",
                "Is Match", "Needs Review", "Confidence", "Latency (s)",
                "Model", "Status",
                "Prompt Tokens", "Candidates Tokens", "Cached Tokens", "Thoughts Tokens", "Total Tokens",
                "Cost (USD)", "Cost (IDR)", "Web Search Queries", "Call Metrics JSON", "Raw Response"
            ])
            for tech, evals in results_by_tech.items():
                for e in evals:
                    writer.writerow([
                        e.filename, e.technique, e.gt_tingkat, e.pred_tingkat,
                        e.is_match, e.needs_review, e.confidence, f"{e.latency_s:.3f}",
                        gemini_model if backend == "gemini" else backend,
                        "success" if e.pred_tingkat else "unparsed",
                        e.prompt_tokens, e.candidates_tokens, e.cached_tokens, e.thoughts_tokens, e.total_tokens,
                        f"{e.cost_usd:.6f}", f"{e.cost_idr:.2f}", "; ".join(e.web_queries),
                        json.dumps(e.metadata.get("call_metrics", [])), e.raw_response[:100]
                    ])

        # 3. Markdown Report
        md_file = output_dir / "report.md"
        md_lines = [
            f"# Laporan Eksperimen Prompting Tingkat ({backend.upper()})",
            f"\nDataset: `{gt_path.name}` ({len(records)} baris)  ",
            f"Sumber Teks OCR: `{texts_path.name}`  ",
            f"Tanggal Eksekusi: {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
            "## Ringkasan Perbandingan Teknik Prompting\n",
            "| Teknik | Akurasi | Review Rate | Prompt Tok | Cand Tok | Cached | Thoughts | Total Tok | Cost (IDR) | Cost (USD) | Web Queries | Nas->Fak | Fak->Nas | Avg Latency |",
            "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
        ]
        for tech, stats in summary.items():
            md_lines.append(
                f"| {tech} | {stats['accuracy']:.2f}% | {stats['review_rate']:.2f}% | "
                f"{stats['total_prompt_tokens']} | {stats['total_candidates_tokens']} | "
                f"{stats.get('total_cached_tokens', 0)} | {stats.get('total_thoughts_tokens', 0)} | "
                f"{stats['total_tokens']} | Rp{stats['total_cost_idr']:.2f} | ${stats['total_cost_usd']:.5f} | "
                f"{stats['total_web_queries']} | {stats['nasional_misclassified_as_fakultas']} | {stats['fakultas_misclassified_as_nasional']} | {stats['avg_latency_s']:.3f}s |"
            )
        md_file.write_text("\n".join(md_lines), encoding="utf-8")

        # 4. Excel Report (.xlsx) via openpyxl
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws_summary = wb.active
            ws_summary.title = "Summary"
            ws_summary.append([
                "Teknik", "Akurasi (%)", "Review Rate (%)",
                "Prompt Tokens", "Candidates Tokens", "Cached Tokens", "Thoughts Tokens", "Total Tokens",
                "Cost (IDR)", "Cost (USD)", "Web Queries",
                "Nasional -> Fakultas", "Fakultas -> Nasional", "Avg Latency (s)"
            ])
            for tech, stats in summary.items():
                ws_summary.append([
                    tech, stats["accuracy"], stats["review_rate"],
                    stats["total_prompt_tokens"], stats["total_candidates_tokens"],
                    stats.get("total_cached_tokens", 0), stats.get("total_thoughts_tokens", 0),
                    stats["total_tokens"], stats["total_cost_idr"], stats["total_cost_usd"],
                    stats["total_web_queries"],
                    stats["nasional_misclassified_as_fakultas"], stats["fakultas_misclassified_as_nasional"],
                    stats["avg_latency_s"]
                ])

            ws_details = wb.create_sheet(title="Details")
            ws_details.append([
                "Nama File", "Teknik", "GT Tingkat", "Pred Tingkat",
                "Match", "Needs Review", "Confidence", "Latency (s)",
                "Model", "Status",
                "Prompt Tokens", "Candidates Tokens", "Cached Tokens", "Thoughts Tokens", "Total Tokens",
                "Cost (IDR)", "Cost (USD)", "Web Queries", "Call Metrics JSON"
            ])
            for tech, evals in results_by_tech.items():
                for e in evals:
                    ws_details.append([
                        e.filename, e.technique, e.gt_tingkat, e.pred_tingkat,
                        1 if e.is_match else 0, 1 if e.needs_review else 0, e.confidence, round(e.latency_s, 3),
                        gemini_model if backend == "gemini" else backend,
                        "success" if e.pred_tingkat else "unparsed",
                        e.prompt_tokens, e.candidates_tokens, e.cached_tokens, e.thoughts_tokens, e.total_tokens,
                        e.cost_idr, e.cost_usd, "; ".join(e.web_queries),
                        json.dumps(e.metadata.get("call_metrics", []))
                    ])
            xlsx_file = output_dir / "results.xlsx"
            wb.save(xlsx_file)
        except ImportError:
            pass

        print(f"\n[Dokumentasi Eksperimen Tersimpan]: {output_dir}/ (.json, .csv, .md, .xlsx)")

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
        "--mapping-file",
        type=str,
        default=None,
        help="Path ke file JSON mapping nama file CSV ke header OCR marker",
    )
    parser.add_argument(
        "--backend",
        type=str,
        choices=["mock", "ollama", "gemini"],
        default="mock",
        help="Backend LLM (mock, ollama, gemini)",
    )
    parser.add_argument(
        "--gemini-model",
        type=str,
        default=os.environ.get("GOOGLE_GEMINI_MODEL", "gemini-3.1-flash-lite"),
        help="Model Gemini yang digunakan (default: gemini-3.1-flash-lite atau dari env)",
    )
    parser.add_argument(
        "--enable-search",
        action="store_true",
        help="Aktifkan Google Search Grounding tool untuk pencarian web live via API",
    )
    parser.add_argument(
        "--technique",
        type=str,
        default="all",
        help="Teknik prompting (all, zero_shot, few_shot, cot, self_consistency, iterative)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Batasi jumlah dokumen")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Direktori penyimpanan output dokumentasi eksperimen (docs/experiments/<ID>/)",
    )
    args = parser.parse_args()

    if not args.texts_path:
        print("ERROR: --texts-path atau env GT_TEXTS_DIR wajib diisi untuk menentukan lokasi artefak teks OCR mentah.")
        sys.exit(1)

    gt_file = REPO_ROOT / args.gt_path if not Path(args.gt_path).is_absolute() else Path(args.gt_path)
    texts_file = REPO_ROOT / args.texts_path if not Path(args.texts_path).is_absolute() else Path(args.texts_path)
    mapping_file = REPO_ROOT / args.mapping_file if args.mapping_file and not Path(args.mapping_file).is_absolute() else (Path(args.mapping_file) if args.mapping_file else None)
    out_dir = REPO_ROOT / args.output_dir if args.output_dir and not Path(args.output_dir).is_absolute() else (Path(args.output_dir) if args.output_dir else None)

    techs = None
    if args.technique != "all":
        techs = [args.technique]

    run_benchmark(
        gt_file,
        texts_file,
        mapping_path=mapping_file,
        backend=args.backend,
        techniques=techs,
        limit=args.limit,
        output_dir=out_dir,
        gemini_model=args.gemini_model,
        enable_grounding=args.enable_search,
    )


if __name__ == "__main__":
    main()
