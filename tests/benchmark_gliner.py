"""Benchmark GLiNER dan GLiNER2.5 pada dataset 74 sertifikat (GT v9 + Matcher v2).

Mendukung model:
1. urchade/gliner_multi-v2.1 (GLiNER v2.1 Multilingual Span Model)
2. fastino/gliner2.5-base-v1 (GLiNER2.5 Boundary Extractor dari paper arXiv:2507.18546)

Usage:
    uv run python -m tests.benchmark_gliner --models gliner-multi-v2.1 gliner2.5-base
"""
from __future__ import annotations

import argparse
import csv
import gc
import importlib.metadata
import json
import os
import random
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import torch

REPO = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO / "backend"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(BACKEND_DIR))

from app.services.field_extractor import ExtractedValue
from tests.evaluation_framework import EVAL_FIELDS, aggregate_results, evaluate_row, load_csv, print_report
from tests.post_processors import score_entity_for_field

GT_CSV = REPO / "Ground_Truth_Sertifikat_v9.csv"
TESSERACT_TEXTS = REPO / "tests" / "benchmark_runs" / "ocr_experiment" / "tesseract_primary_v4" / "extracted_texts"
RUNS_DIR = REPO / "tests" / "benchmark_runs"
SEED = 42

FREE_INSTITUTION_FIELDS = {
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "nomor_bukti_fisik_nomor_sertifikasi",
}

GLINER_MODELS = {
    "gliner-multi-v2.1": "urchade/gliner_multi-v2.1",
    "gliner2.5-base": "fastino/gliner2.5-base-v1",
}


@dataclass(frozen=True)
class ExtractedEntity:
    label: str
    text: str
    score: float
    start: int = 0
    end: int = 0


def _load_gt_rows(csv_path: Path) -> dict[str, dict[str, str]]:
    raw_rows = load_csv(str(csv_path))
    return {
        row.get("nama_file", "").rsplit(".", 1)[0]: row
        for row in raw_rows
        if row.get("nama_file")
    }


def _read_text(path: Path) -> str:
    return "\n".join(l for l in path.read_text(encoding="utf-8").splitlines() if not l.startswith("#")).strip()


def _chunk_text(text: str, chunk_size: int = 250, overlap: int = 50) -> list[str]:
    words = text.split()
    if len(words) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += (chunk_size - overlap)
    return chunks


def _predict_gliner_v1(model: Any, text: str, labels: list[str], threshold: float = 0.25) -> list[ExtractedEntity]:
    chunks = _chunk_text(text, chunk_size=200, overlap=40)
    entities: list[ExtractedEntity] = []
    seen = set()
    for chunk in chunks:
        preds = model.predict_entities(chunk, labels, threshold=threshold)
        for p in preds:
            txt = p["text"].strip()
            key = (p["label"], txt.lower())
            if key not in seen and len(txt) > 2:
                seen.add(key)
                entities.append(ExtractedEntity(label=p["label"], text=txt, score=float(p["score"])))
    return entities


def _predict_gliner2(model: Any, text: str, labels: list[str]) -> list[ExtractedEntity]:
    chunks = _chunk_text(text, chunk_size=250, overlap=50)
    entities: list[ExtractedEntity] = []
    seen = set()
    for chunk in chunks:
        try:
            res = model.extract_entities(chunk, labels)
            ent_dict = res.get("entities", {})
            for lbl, vals in ent_dict.items():
                if isinstance(vals, list):
                    for v in vals:
                        txt = str(v).strip()
                        key = (lbl, txt.lower())
                        if key not in seen and len(txt) > 2:
                            seen.add(key)
                            entities.append(ExtractedEntity(label=lbl, text=txt, score=0.85))
        except Exception as e:
            continue
    return entities


def map_gliner_entities_to_fields(entities: list[ExtractedEntity], full_text: str, source: str) -> dict[str, ExtractedValue]:
    fields: dict[str, ExtractedValue] = {}

    # 1. Nama Kegiatan
    evt_candidates = [e for e in entities if any(k in e.label.lower() for k in ("event", "kegiatan"))]
    if evt_candidates:
        # Filter out junk candidates (like NIP/NIM or single letters)
        valid_evts = [e for e in evt_candidates if not re.match(r'^(NIP|NIK|NIM|NO|NOMOR)\b', e.text, re.IGNORECASE) and len(e.text) > 4]
        if valid_evts:
            best_evt = max(valid_evts, key=lambda e: len(e.text))
            fields["nama_kegiatan_sertifikasi"] = ExtractedValue(best_evt.text.replace("\n", " ").strip(), round(best_evt.score, 2), source)

    # 2. Penyelenggara
    org_candidates = [e for e in entities if any(k in e.label.lower() for k in ("organizer", "penyelenggara", "organization", "organisasi"))]
    if org_candidates:
        valid_orgs = [e for e in org_candidates if not re.match(r'^(PANITIA|PESERTA|JUARA)\b', e.text, re.IGNORECASE) and len(e.text) > 3]
        if valid_orgs:
            best_org = max(valid_orgs, key=lambda e: len(e.text))
            fields["penyelenggara_kegiatan"] = ExtractedValue(best_org.text.replace("\n", " ").strip(), round(best_org.score, 2), source)

    # 3. Nomor Sertifikat
    num_candidates = [e for e in entities if any(k in e.label.lower() for k in ("certificate number", "nomor sertifikat", "nomor"))]
    if num_candidates:
        valid_nums = [e for e in num_candidates if any(c.isdigit() for c in e.text) and any(c in e.text for c in ("/", ".", "-"))]
        if valid_nums:
            best_num = max(valid_nums, key=lambda e: e.score)
            cleaned_num = re.sub(r'^(Nomor|No\.?|Number)\s*[:.]?\s*', '', best_num.text, flags=re.IGNORECASE).strip()
            fields["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(cleaned_num, round(best_num.score, 2), source)

    # 4. Tanggal
    date_candidates = [e for e in entities if any(k in e.label.lower() for k in ("date", "tanggal"))]
    if date_candidates:
        valid_dates = [e for e in date_candidates if any(c.isdigit() for c in e.text)]
        if valid_dates:
            d_start = valid_dates[0]
            d_end = valid_dates[-1]
            fields["waktu_mulai_pelaksanaan"] = ExtractedValue(d_start.text.strip(), round(d_start.score, 2), source)
            fields["waktu_selesai_pelaksanaan"] = ExtractedValue(d_end.text.strip(), round(d_end.score, 2), source)

    return fields


def _bootstrap_ci(row_results: list[dict], iterations: int = 1000, seed: int = SEED) -> dict[str, float]:
    rng = random.Random(seed)
    observations = []
    for result in row_results:
        exact = sum(1 for field in EVAL_FIELDS if field in result and result[field]["exact"])
        total = sum(1 for field in EVAL_FIELDS if field in result)
        observations.append((exact, total))
    values: list[float] = []
    for _ in range(iterations):
        sample = [rng.choice(observations) for _ in observations]
        exact = sum(item[0] for item in sample)
        total = sum(item[1] for item in sample)
        values.append(exact / total if total else 0.0)
    values.sort()
    return {
        "iterations": iterations,
        "mean": sum(values) / len(values),
        "lower_95": values[int(0.025 * (len(values) - 1))],
        "upper_95": values[int(0.975 * (len(values) - 1))],
    }


def _mutate_institution(text: str) -> str:
    replacements = (("Universitas Airlangga", "Universitas Negeri Semarang"), ("UNAIR", "UNS"), ("FTMM", "FST"))
    for source, target in replacements:
        text = re.sub(re.escape(source), target, text, flags=re.IGNORECASE)
    return text


def _inject_ocr_noise(text: str, rate: float, rng: random.Random) -> str:
    substitutions = {"5": "S", "S": "5", "8": "B", "B": "8", "0": "O", "O": "0", "1": "I", "I": "1"}
    return "".join(substitutions.get(char, char) if char.upper() in substitutions and rng.random() < rate else char for char in text)


def _free_field_exact(row_result: dict) -> tuple[int, int]:
    selected = [result for field, result in row_result.items() if field in FREE_INSTITUTION_FIELDS]
    return sum(1 for result in selected if result["exact"]), len(selected)


def run_benchmark(model_key: str, hf_id: str, gt_rows: dict[str, dict[str, str]], device: str) -> dict[str, Any]:
    print(f"\n=======================================================")
    print(f"BENCHMARKING: {model_key} ({hf_id}) on {device.upper()}")
    print(f"=======================================================")

    is_gliner2 = "gliner2" in model_key
    t0_load = time.perf_counter()

    if is_gliner2:
        from gliner2 import AutoExtractor
        model = AutoExtractor.from_pretrained(hf_id, map_location=device)
    else:
        from gliner import GLiNER
        model = GLiNER.from_pretrained(hf_id, map_location=device)

    print(f"Model loaded in {time.perf_counter() - t0_load:.2f}s")

    labels_en = ["event name", "certificate number", "organizer", "date"]
    source_tag = f"gliner:{model_key}"

    clean_results = []
    ood_raw = {"mutation": [], "noise_10": [], "noise_25": [], "noise_50": []}
    per_cert_times = []

    stems = sorted(gt_rows.keys())
    for stem in stems:
        txt_path = TESSERACT_TEXTS / f"{stem}.txt"
        if not txt_path.exists():
            continue
        text = _read_text(txt_path)
        expected = gt_rows[stem]

        t_start = time.perf_counter()
        if is_gliner2:
            entities = _predict_gliner2(model, text, labels_en)
        else:
            entities = _predict_gliner_v1(model, text, labels_en, threshold=0.25)
        elapsed = time.perf_counter() - t_start
        per_cert_times.append(elapsed)

        mapped = map_gliner_entities_to_fields(entities, text, source_tag)
        row_eval = evaluate_row(mapped, expected)
        clean_results.append(row_eval)

        # OOD evaluations
        mut_text = _mutate_institution(text)
        mut_ents = _predict_gliner2(model, mut_text, labels_en) if is_gliner2 else _predict_gliner_v1(model, mut_text, labels_en, threshold=0.25)
        ood_raw["mutation"].append(evaluate_row(map_gliner_entities_to_fields(mut_ents, mut_text, source_tag), expected))

        for rate, key in [(0.10, "noise_10"), (0.25, "noise_25"), (0.50, "noise_50")]:
            rng = random.Random(f"{SEED}:{stem}:{int(rate*100)}")
            n_text = _inject_ocr_noise(text, rate, rng)
            n_ents = _predict_gliner2(model, n_text, labels_en) if is_gliner2 else _predict_gliner_v1(model, n_text, labels_en, threshold=0.25)
            ood_raw[key].append(evaluate_row(map_gliner_entities_to_fields(n_ents, n_text, source_tag), expected))

    # Aggregasi hasil
    summary = aggregate_results(clean_results)
    ci = _bootstrap_ci(clean_results)

    # OOD summary
    clean_exact, clean_total = map(sum, zip(*(_free_field_exact(row) for row in clean_results)))
    clean_acc = clean_exact / clean_total if clean_total else 0.0
    ood_summary = {"clean": {"exact": clean_acc, "count": clean_total}}
    for name, rows in ood_raw.items():
        exact, total = map(sum, zip(*(_free_field_exact(row) for row in rows))) if rows else (0, 0)
        acc = exact / total if total else 0.0
        ood_summary[name] = {"exact": acc, "count": total, "drop_points": (clean_acc - acc) * 100}

    slug = model_key.replace("-", "_").replace(".", "_")
    run_dir = RUNS_DIR / f"gliner_{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "model": model_key,
        "hf_id": hf_id,
        "mode": "zero_shot_schema_extraction",
        "labels": labels_en,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "bootstrap_ci": ci,
        "ood": ood_summary,
        "avg_latency_s": sum(per_cert_times) / len(per_cert_times) if per_cert_times else 0,
        "total_time_s": sum(per_cert_times),
        "results": clean_results,
    }

    (run_dir / "results.json").write_text(json.dumps(payload, indent=2, default=str))
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\n--- REPORT: {model_key} ---")
    print_report(summary)
    print(f"Bootstrap 95% CI: [{ci['lower_95']:.2%}, {ci['upper_95']:.2%}] (Mean: {ci['mean']:.2%})")
    print(f"Avg Latency: {payload['avg_latency_s']:.3f}s / cert (Total: {payload['total_time_s']:.1f}s)")
    return payload
LABEL_SCHEMA = {
    "nama_kegiatan_sertifikasi": "event name",
    "nomor_bukti_fisik_nomor_sertifikasi": "certificate number",
    "penyelenggara_kegiatan": "organizer",
    "waktu_mulai_pelaksanaan": "date",
    "waktu_selesai_pelaksanaan": "date",
}
LABEL_TO_NER = {
    "event name": "EVT",
    "certificate number": "NUM",
    "organizer": "ORG",
    "date": "DAT",
}
MAX_LENGTH = 512
STRIDE = 64


@dataclass(frozen=True)
class GlinerTrainingSpan:
    start_word: int
    end_word: int
    label: str
    field: str
    matched_ocr_text: str


@dataclass(frozen=True)
class GlinerTrainingExample:
    stem: str
    text: str
    tokens: list[str]
    word_spans: list[tuple[int, int]]
    expected: dict[str, str]
    spans: tuple[GlinerTrainingSpan, ...]


@dataclass(frozen=True)
class GlinerTrainingWindow:
    stem: str
    text: str
    tokens: list[str]
    char_start: int
    char_end: int
    word_start: int
    word_end: int
    spans: tuple[GlinerTrainingSpan, ...]


def _whole_token_spans(tokens: list[str], value: str) -> list[tuple[int, int]]:
    from tests.benchmark_ner_encoders import normalize_token
    needle = normalize_token(value)
    if not needle:
        return []
    normalized = [normalize_token(token) for token in tokens]
    output: list[tuple[int, int]] = []
    for start, first in enumerate(normalized):
        if not first:
            continue
        joined = ""
        for end in range(start + 1, len(tokens) + 1):
            joined += normalized[end - 1]
            if joined == needle:
                if normalized[end - 1]:
                    output.append((start, end))
                continue
            if len(joined) > len(needle):
                break
    return output


def build_gliner_training_examples(
    examples: list[Example],
) -> tuple[list[GlinerTrainingExample], dict[str, object]]:
    """Build conservative training labels without modifying shared encoder alignment."""
    from tests.benchmark_ner_encoders import find_token_span
    audit: dict[str, object] = {
        "documents": len(examples),
        "fields_expected": 0,
        "candidate_found": 0,
        "initial_unmatched": 0,
        "first_hit_nonexact": 0,
        "fields_with_valid_whole_token": 0,
        "whole_token_ambiguous": 0,
        "whole_token_unambiguous": 0,
        "boundary_unmatched": 0,
        "usable_label_tuples": 0,
        "ambiguous": [],
        "boundary_expanded": [],
    }
    output: list[GlinerTrainingExample] = []
    labels_seen: set[tuple[str, int, int, str]] = set()
    for example in examples:
        spans: list[GlinerTrainingSpan] = []
        for field, label in LABEL_SCHEMA.items():
            value = (example.expected.get(field) or "").strip()
            if not value or value == "-":
                continue
            audit["fields_expected"] = int(audit["fields_expected"]) + 1
            first = find_token_span(example.tokens, value)
            if first is None:
                audit["initial_unmatched"] = int(audit["initial_unmatched"]) + 1
                continue
            audit["candidate_found"] = int(audit["candidate_found"]) + 1
            candidates = _whole_token_spans(example.tokens, value)
            if first not in candidates:
                audit["first_hit_nonexact"] = int(audit["first_hit_nonexact"]) + 1
            if not candidates:
                audit["boundary_unmatched"] = int(audit["boundary_unmatched"]) + 1
                cast = audit["boundary_expanded"]
                assert isinstance(cast, list)
                cast.append({"stem": example.stem, "field": field, "first_hit": first})
                continue
            audit["fields_with_valid_whole_token"] = int(audit["fields_with_valid_whole_token"]) + 1
            if len(candidates) != 1:
                audit["whole_token_ambiguous"] = int(audit["whole_token_ambiguous"]) + 1
                cast = audit["ambiguous"]
                assert isinstance(cast, list)
                cast.append({"stem": example.stem, "field": field, "positions": candidates})
                continue
            audit["whole_token_unambiguous"] = int(audit["whole_token_unambiguous"]) + 1
            start, end = candidates[0]
            key = (example.stem, start, end - 1, label)
            if key in labels_seen:
                continue
            labels_seen.add(key)
            char_start = example.word_spans[start][0]
            char_end = example.word_spans[end - 1][1]
            spans.append(GlinerTrainingSpan(start, end, label, field, example.text[char_start:char_end]))
        output.append(GlinerTrainingExample(
            example.stem, example.text, example.tokens, example.word_spans, example.expected, tuple(spans),
        ))
    audit["usable_label_tuples"] = len(labels_seen)
    expected = {
        "documents": 74, "fields_expected": 310, "candidate_found": 223,
        "initial_unmatched": 87, "first_hit_nonexact": 17,
        "fields_with_valid_whole_token": 213, "whole_token_ambiguous": 65,
        "whole_token_unambiguous": 148, "boundary_unmatched": 10,
        "usable_label_tuples": 130,
    }
    for key, value in expected.items():
        if audit[key] != value:
            raise RuntimeError(f"alignment precondition {key}={audit[key]!r}, expected {value!r}")
    return output, audit


def _encoded_length(tokenizer: Any, tokens: list[str]) -> int:
    encoded = tokenizer(tokens, is_split_into_words=True, add_special_tokens=True, truncation=False)
    return len(encoded["input_ids"])


def _safe_window_end(
    tokens: list[str], spans: Iterable[GlinerTrainingSpan], tokenizer: Any, start: int, max_length: int,
) -> int:
    end = start + 1
    while end <= len(tokens) and _encoded_length(tokenizer, tokens[start:end]) <= max_length:
        end += 1
    end -= 1
    if end <= start:
        raise ValueError("satu token melampaui max_length")
    for span in spans:
        if span.start_word < end < span.end_word:
            end = span.start_word
    if end <= start:
        raise ValueError("span label tunggal melampaui max_length")
    return end


def _next_window_start(tokens: list[str], spans: Iterable[GlinerTrainingSpan], tokenizer: Any, start: int, end: int, stride: int) -> int:
    next_start = end
    while next_start > start and _encoded_length(tokenizer, tokens[next_start - 1:end]) < stride:
        next_start -= 1
    for span in spans:
        if span.start_word < next_start < span.end_word:
            next_start = span.start_word
    return next_start if next_start > start else start + 1


def window_gliner_example(
    example: GlinerTrainingExample, tokenizer: Any, max_length: int = MAX_LENGTH, stride: int = STRIDE,
) -> list[GlinerTrainingWindow]:
    if stride <= 0 or stride >= max_length:
        raise ValueError("stride harus lebih kecil dari max_length")
    windows: list[GlinerTrainingWindow] = []
    start = 0
    while start < len(example.tokens):
        end = _safe_window_end(example.tokens, example.spans, tokenizer, start, max_length)
        included = tuple(
            GlinerTrainingSpan(
                span.start_word - start, span.end_word - start, span.label, span.field, span.matched_ocr_text,
            )
            for span in example.spans
            if start <= span.start_word and span.end_word <= end
        )
        windows.append(GlinerTrainingWindow(
            example.stem,
            example.text[example.word_spans[start][0]:example.word_spans[end - 1][1]],
            example.tokens[start:end],
            example.word_spans[start][0],
            example.word_spans[end - 1][1],
            start,
            end,
            included,
        ))
        if end == len(example.tokens):
            break
        start = _next_window_start(example.tokens, example.spans, tokenizer, start, end, stride)
    expected = {(span.start_word, span.end_word, span.label) for span in example.spans}
    covered = {
        (span.start_word + window.word_start, span.end_word + window.word_start, span.label)
        for window in windows for span in window.spans
    }
    if not expected <= covered:
        raise RuntimeError(f"window kehilangan span {example.stem}: {sorted(expected - covered)!r}")
    if any(_encoded_length(tokenizer, window.tokens) > max_length for window in windows):
        raise RuntimeError(f"window melebihi max_length: {example.stem}")
    return windows


def window_gliner_text(
    stem: str, text: str, tokenizer: Any, max_length: int = MAX_LENGTH, stride: int = STRIDE,
) -> list[GlinerTrainingWindow]:
    from tests.benchmark_ner_encoders import tokenize_with_spans
    tokens, word_spans = tokenize_with_spans(text)
    if not tokens:
        return []
    empty = GlinerTrainingExample(stem, text, tokens, word_spans, {}, ())
    return window_gliner_example(empty, tokenizer, max_length=max_length, stride=stride)


def to_gliner_v1_records(windows: list[GlinerTrainingWindow]) -> list[dict[str, object]]:
    return [{
        "tokenized_text": window.tokens,
        "ner": [[span.start_word, span.end_word - 1, span.label] for span in window.spans],
    } for window in windows if window.spans]


def to_gliner2_examples(windows: list[GlinerTrainingWindow]) -> list[Any]:
    from gliner2.training.data import InputExample
    output = []
    for window in windows:
        entities: dict[str, list[str]] = {}
        for span in window.spans:
            entities.setdefault(span.label, []).append(span.matched_ocr_text)
        if not entities:
            continue
        record = InputExample(text=window.text, entities=entities)
        errors = record.validate()
        if errors:
            raise ValueError(f"InputExample invalid {window.stem}: {errors}")
        output.append(record)
    return output


def _strict_gliner_trainer_class():
    from gliner.training import Trainer as NativeGlinerTrainer

    class StrictGlinerTrainer(NativeGlinerTrainer):
        """Native GLiNER loss path, except CUDA OOM and non-finite states are fatal."""
        def training_step(self, model: Any, inputs: dict[str, Any], num_items_in_batch: int | None = None) -> torch.Tensor:
            model.train()
            inputs = self._prepare_inputs(inputs)
            if "labels" not in inputs:
                raise KeyError(f"batch tanpa labels: {sorted(inputs)}")
            with self.compute_loss_context_manager():
                loss = self.compute_loss(model, inputs, num_items_in_batch=num_items_in_batch)
            if loss is None or not torch.isfinite(loss):
                raise RuntimeError("loss non-finite selama training GLiNER")
            if self.args.n_gpu > 1:
                loss = loss.mean()
            if self.args.gradient_accumulation_steps > 1 and self.deepspeed is None:
                loss = loss / self.args.gradient_accumulation_steps
            self.accelerator.backward(loss)
            return loss.detach()
    return StrictGlinerTrainer


def _gliner_v1_span_width(model: Any) -> int:
    return int(model.model.span_rep_layer.span_rep_layer.max_width)


def _model_tokenizer(model: Any) -> Any:
    for owner in (getattr(model, "data_processor", None), getattr(model, "processor", None), model):
        for name in ("transformer_tokenizer", "tokenizer"):
            tokenizer = getattr(owner, name, None)
            if tokenizer is not None:
                return tokenizer
    raise RuntimeError("tokenizer backbone tidak ditemukan")


def _peak_vram() -> int:
    return int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else 0
def _first_parameter_l1(model: Any) -> float:
    parameter = next(parameter for parameter in model.parameters() if parameter.requires_grad)
    return float(parameter.detach().float().abs().sum().item())




def _clear_cuda() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

def _package_versions() -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in ("gliner", "gliner2", "transformers", "torch")}


def _to_ner_entities(entities: list[ExtractedEntity]) -> list[Any]:
    from tests.benchmark_ner_encoders import NEREntity
    output = []
    for entity in entities:
        entity_type = LABEL_TO_NER.get(entity.label)
        if entity_type is not None:
            output.append(NEREntity(entity_type, entity.text, entity.start, entity.end, entity.score))
    return output


def _dedupe_entities(entities: list[ExtractedEntity], *, preserve_spans: bool) -> list[ExtractedEntity]:
    from tests.benchmark_ner_encoders import normalize_token
    best: dict[tuple[object, ...], ExtractedEntity] = {}
    for entity in entities:
        normalized = normalize_token(entity.text)
        if not normalized:
            continue
        key = (entity.label, entity.start, entity.end, normalized) if preserve_spans else (entity.label, normalized)
        previous = best.get(key)
        if previous is None or entity.score > previous.score:
            best[key] = entity
    return list(best.values())


def predict_gliner_v1_long(model: Any, stem: str, text: str, threshold: float = 0.5) -> list[ExtractedEntity]:
    tokenizer = _model_tokenizer(model)
    entities: list[ExtractedEntity] = []
    for window in window_gliner_text(stem, text, tokenizer):
        for prediction in model.predict_entities(window.text, list(LABEL_TO_NER), threshold=threshold):
            if not {"text", "label", "score", "start", "end"} <= prediction.keys():
                raise ValueError(f"prediksi GLiNER v1 tanpa span: {prediction!r}")
            entities.append(ExtractedEntity(
                str(prediction["label"]), str(prediction["text"]), float(prediction["score"]),
                window.char_start + int(prediction["start"]), window.char_start + int(prediction["end"]),
            ))
    return _dedupe_entities(entities, preserve_spans=False)


def _gliner2_entities(result: dict[str, Any], char_offset: int) -> list[ExtractedEntity]:
    root = result.get("entities", result)
    if not isinstance(root, dict):
        raise ValueError(f"format hasil GLiNER2 tidak dikenal: {result!r}")
    output: list[ExtractedEntity] = []
    for label, values in root.items():
        if not isinstance(values, list):
            values = [values]
        for value in values:
            if not isinstance(value, dict) or not {"text", "confidence", "start", "end"} <= value.keys():
                raise ValueError(f"hasil GLiNER2 harus menyimpan text/confidence/span: {value!r}")
            output.append(ExtractedEntity(
                str(label), str(value["text"]), float(value["confidence"]),
                char_offset + int(value["start"]), char_offset + int(value["end"]),
            ))
    return output


def predict_gliner2_long(model: Any, stem: str, text: str, threshold: float = 0.5) -> list[ExtractedEntity]:
    tokenizer = _model_tokenizer(model)
    entities: list[ExtractedEntity] = []
    for window in window_gliner_text(stem, text, tokenizer):
        result = model.extract_entities(
            window.text, list(LABEL_TO_NER), threshold=threshold, max_len=MAX_LENGTH,
            include_confidence=True, include_spans=True,
        )
        entities.extend(_gliner2_entities(result, window.char_start))
    return _dedupe_entities(entities, preserve_spans=True)


def _variants(example: Example) -> dict[str, str]:
    return {
        "mutation": _mutate_institution(example.text),
        "noise_10": _inject_ocr_noise(example.text, 0.10, random.Random(f"{SEED}:{example.stem}:10")),
        "noise_25": _inject_ocr_noise(example.text, 0.25, random.Random(f"{SEED}:{example.stem}:25")),
        "noise_50": _inject_ocr_noise(example.text, 0.50, random.Random(f"{SEED}:{example.stem}:50")),
    }


def _evaluate_gliner_fold(
    predictor: Callable[[str, str], list[ExtractedEntity]], held_out: list[Example], source: str, include_ood: bool,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    from tests.benchmark_ner_encoders import map_entities_to_fields
    clean: list[dict[str, Any]] = []
    ood = {"mutation": [], "noise_10": [], "noise_25": [], "noise_50": []}
    predictions = []
    for example in held_out:
        started = time.perf_counter()
        entities = predictor(example.stem, example.text)
        mapped = map_entities_to_fields(_to_ner_entities(entities), example.text, source)
        row = evaluate_row(mapped, example.expected)
        clean.append(row)
        predictions.append({
            "stem": example.stem, "source_fold": source, "latency_s": time.perf_counter() - started,
            "entities": [entity.__dict__ for entity in entities], "fields": {key: value.value for key, value in mapped.items()},
            "result": row,
        })
        if include_ood:
            for name, text in _variants(example).items():
                mapped_ood = map_entities_to_fields(_to_ner_entities(predictor(example.stem, text)), text, source)
                ood[name].append(evaluate_row(mapped_ood, example.expected))
    return clean, ood, predictions


def _summarize_ood(clean: list[dict], ood: dict[str, list[dict]]) -> dict[str, dict[str, float]]:
    clean_exact, clean_total = map(sum, zip(*(_free_field_exact(row) for row in clean)))
    clean_acc = clean_exact / clean_total if clean_total else 0.0
    summary: dict[str, dict[str, float]] = {"clean": {"exact": clean_acc, "count": clean_total}}
    for name, rows in ood.items():
        exact, total = map(sum, zip(*(_free_field_exact(row) for row in rows))) if rows else (0, 0)
        accuracy = exact / total if total else 0.0
        summary[name] = {"exact": accuracy, "count": total, "drop_points": (clean_acc - accuracy) * 100}
    return summary


def _fold_windows(examples: list[GlinerTrainingExample], tokenizer: Any) -> list[GlinerTrainingWindow]:
    return [window for example in examples for window in window_gliner_example(example, tokenizer)]


def run_gliner_v1_fold(
    hf_id: str, fold_index: int, train_examples: list[GlinerTrainingExample], held_out: list[Example],
    fold_dir: Path, args: argparse.Namespace,
) -> tuple[list[dict], dict[str, list[dict]], list[dict], dict[str, Any]]:
    from gliner import GLiNER
    from gliner.training import TrainingArguments
    torch.manual_seed(SEED + fold_index)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED + fold_index)
        torch.cuda.reset_peak_memory_stats()
    model = GLiNER.from_pretrained(hf_id, max_length=MAX_LENGTH, max_width=64)
    if model.config.max_len != MAX_LENGTH or model.config.max_width != 64 or _gliner_v1_span_width(model) != 64:
        raise RuntimeError("override GLiNER v1 max_length/max_width tidak diterapkan saat konstruksi model")
    model.float()
    model.model.token_rep_layer.bert_layer.model.gradient_checkpointing_enable()
    parameter_l1_before = _first_parameter_l1(model)
    tokenizer = _model_tokenizer(model)
    windows = _fold_windows(train_examples, tokenizer)
    records = to_gliner_v1_records(windows)
    training_args = TrainingArguments(
        output_dir=str(fold_dir / "checkpoint"), num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size, gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate, others_lr=args.learning_rate, weight_decay=0.01,
        max_grad_norm=1.0, optim="adafactor", lr_scheduler_type="linear", warmup_ratio=0.1,
        focal_loss_alpha=-1, focal_loss_gamma=0, negatives=1.0, masking="none", loss_reduction="sum",
        eval_strategy="no", save_strategy="no", report_to="none", dataloader_num_workers=0,
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(), fp16=False,
        remove_unused_columns=False, seed=SEED + fold_index,
    )
    trainer_class = _strict_gliner_trainer_class()
    trainer = trainer_class(
        model=model, args=training_args, train_dataset=records, data_collator=model._create_data_collator(),
        processing_class=tokenizer,
    )
    started = time.perf_counter()
    trainer.train()
    if not all(torch.isfinite(parameter).all() for parameter in model.parameters()):
        raise RuntimeError("parameter GLiNER v1 non-finite setelah training")
    parameter_l1_delta = abs(_first_parameter_l1(model) - parameter_l1_before)
    if parameter_l1_delta == 0.0:
        raise RuntimeError("parameter GLiNER v1 tidak berubah selama training")
    clean, ood, predictions = _evaluate_gliner_fold(
        lambda stem, text: predict_gliner_v1_long(model, stem, text), held_out, f"gliner-ft:v1:fold-{fold_index + 1}", not args.skip_ood,
    )
    report = {
        "fold": fold_index + 1, "train_documents": len(train_examples), "held_out_documents": len(held_out),
        "train_windows": len(windows), "seconds": time.perf_counter() - started, "peak_vram_bytes": _peak_vram(),
        "summary": aggregate_results(clean), "train_loss": trainer.state.log_history,
        "all_parameters_finite": all(torch.isfinite(parameter).all() for parameter in model.parameters()),
        "first_parameter_l1_delta": parameter_l1_delta,
    }
    del trainer, model, tokenizer
    _clear_cuda()
    return clean, ood, predictions, report


def run_gliner2_fold(
    hf_id: str, fold_index: int, train_examples: list[GlinerTrainingExample], held_out: list[Example],
    fold_dir: Path, args: argparse.Namespace,
) -> tuple[list[dict], dict[str, list[dict]], list[dict], dict[str, Any]]:
    from gliner2 import AutoExtractor
    from gliner2.training.trainer import ExtractorTrainer, TrainingConfig
    torch.manual_seed(SEED + fold_index)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED + fold_index)
        torch.cuda.reset_peak_memory_stats()
    model = AutoExtractor.from_pretrained(hf_id)
    if getattr(model, "architecture", None) != "boundary":
        raise RuntimeError(f"GLiNER2 checkpoint harus boundary, didapat {getattr(model, 'architecture', None)!r}")
    model.float()
    parameter_l1_before = _first_parameter_l1(model)
    tokenizer = _model_tokenizer(model)
    windows = _fold_windows(train_examples, tokenizer)
    records = to_gliner2_examples(windows)
    config = TrainingConfig(
        output_dir=str(fold_dir / "checkpoint"), experiment_name=f"gliner2_fold_{fold_index + 1}",
        num_epochs=int(args.epochs), batch_size=args.batch_size, gradient_accumulation_steps=args.gradient_accumulation_steps,
        encoder_lr=args.learning_rate, task_lr=args.learning_rate, weight_decay=0.01, max_grad_norm=1.0,
        scheduler_type="linear", warmup_ratio=0.1, max_len=MAX_LENGTH, gradient_checkpointing=True,
        use_lora=False, deterministic=False, eval_strategy="no", save_best=False, num_workers=0,
        strict_training=True, allow_invalid_samples=False, skip_step_errors=False, ignore_nonfinite_losses=False,
        on_capacity_exceeded="raise", fp16=False, bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        seed=SEED + fold_index,
    )
    trainer = ExtractorTrainer(model, config)
    started = time.perf_counter()
    trainer.train(train_data=records)
    if not all(torch.isfinite(parameter).all() for parameter in model.parameters()):
        raise RuntimeError("parameter GLiNER2 non-finite setelah training")
    parameter_l1_delta = abs(_first_parameter_l1(model) - parameter_l1_before)
    if parameter_l1_delta == 0.0:
        raise RuntimeError("parameter GLiNER2 tidak berubah selama training")
    clean, ood, predictions = _evaluate_gliner_fold(
        lambda stem, text: predict_gliner2_long(model, stem, text), held_out, f"gliner-ft:v2:fold-{fold_index + 1}", not args.skip_ood,
    )
    report = {
        "fold": fold_index + 1, "train_documents": len(train_examples), "held_out_documents": len(held_out),
        "train_windows": len(windows), "seconds": time.perf_counter() - started, "peak_vram_bytes": _peak_vram(),
        "summary": aggregate_results(clean), "optimizer": type(trainer.optimizer).__name__,
        "trainable_parameters": sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad),
        "all_parameters_finite": all(torch.isfinite(parameter).all() for parameter in model.parameters()),
        "first_parameter_l1_delta": parameter_l1_delta,
    }
    del trainer, model, tokenizer
    _clear_cuda()
    return clean, ood, predictions, report


def _checkpoint_revision(hf_id: str) -> str:
    from huggingface_hub import snapshot_download
    return Path(snapshot_download(hf_id, local_files_only=True)).name


def finetune_manifest(
    model_key: str, args: argparse.Namespace, alignment: dict[str, object], checkpoint_revision: str,
) -> dict[str, object]:
    return {
        "experiment": "NER-GLINER-002", "model": GLINER_MODELS[model_key], "model_key": model_key,
        "checkpoint_revision": checkpoint_revision, "versions": _package_versions(), "csv_path": str(GT_CSV),
        "ocr_corpus": str(TESSERACT_TEXTS), "folds": args.folds, "fold_seed": SEED,
        "epochs": args.epochs, "batch_size": args.batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "effective_batch_size": args.batch_size * args.gradient_accumulation_steps,
        "max_length": MAX_LENGTH, "stride": STRIDE, "learning_rate": args.learning_rate,
        "weight_decay": 0.01, "max_grad_norm": 1.0, "scheduler": "linear", "warmup_ratio": 0.1,
        "dataloader_num_workers": 0, "eval_strategy": "no", "lora": False,
        "precision": "bf16 autocast bila CUDA mendukung; selain itu FP32", "alignment": alignment,
        "gate": "OOF 74/74, no OOM/nonfinite/invalid labels, no regression vs zero-shot; no production promotion",
    }


def run_finetuned_fold(
    model_key: str, fold_num: int, run_dir: Path, examples: list[Example], args: argparse.Namespace,
) -> None:
    training_examples, _ = build_gliner_training_examples(examples)
    from tests.benchmark_ner_encoders import stratified_folds
    folds = stratified_folds(examples, args.folds)
    fold_index = fold_num - 1
    held_out = folds[fold_index]
    by_stem = {example.stem: example for example in training_examples}
    train = [by_stem[example.stem] for index, fold in enumerate(folds) if index != fold_index for example in fold]
    fold_dir = run_dir / f"fold_{fold_num}"
    fold_dir.mkdir(parents=True, exist_ok=True)
    out_file = fold_dir / "fold_output.json"
    if out_file.exists():
        print(f"[{model_key}] Fold {fold_num}/{args.folds} sudah ada ({out_file}), skip.", flush=True)
        return
    import psutil
    avail_gb = psutil.virtual_memory().available / (1024**3)
    if avail_gb < 1.5:
        raise RuntimeError(f"Memori sistem terlalu rendah ({avail_gb:.2f} GB). Hentikan untuk mencegah crash WSL.")
    print(f"[{model_key}] Starting Fold {fold_num}/{args.folds} ({len(train)} train docs, {len(held_out)} held-out, RAM avail: {avail_gb:.2f} GB)...", flush=True)
    runner = run_gliner2_fold if model_key == "gliner2.5-base" else run_gliner_v1_fold
    clean, ood, predictions, report = runner(GLINER_MODELS[model_key], fold_index, train, held_out, fold_dir, args)
    macro_acc = report.get("summary", {}).get("macro_avg", {}).get("exact_acc", 0.0)
    print(f"[{model_key}] Fold {fold_num}/{args.folds} finished in {report['seconds']:.1f}s | Peak VRAM: {report['peak_vram_bytes'] / (1024**2):.1f} MB | Fold Exact: {macro_acc:.1%}", flush=True)
    payload = {"clean": clean, "ood": ood, "predictions": predictions, "report": report}
    out_file.write_text(json.dumps(payload, indent=2, default=str))


def run_finetuned_model(model_key: str, examples: list[Example], args: argparse.Namespace) -> Path:
    import subprocess, sys
    training_examples, alignment_audit = build_gliner_training_examples(examples)
    slug = model_key.replace("-", "_").replace(".", "_")
    run_dir = Path(args.run_dir) if args.run_dir else RUNS_DIR / f"gliner_ft_{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    config = finetune_manifest(
        model_key, args, alignment_audit, _checkpoint_revision(GLINER_MODELS[model_key]),
    )
    (run_dir / "config.json").write_text(json.dumps(config, indent=2, default=str))
    (run_dir / "alignment_audit.json").write_text(json.dumps(alignment_audit, indent=2, default=str))
    started = time.perf_counter()
    for fold_num in range(1, args.folds + 1):
        fold_out = run_dir / f"fold_{fold_num}" / "fold_output.json"
        if not fold_out.exists():
            cmd = [
                sys.executable, "-m", "tests.benchmark_gliner",
                "--mode", "fine-tune",
                "--models", model_key,
                "--fold", str(fold_num),
                "--run-dir", str(run_dir),
                "--folds", str(args.folds),
                "--epochs", str(args.epochs),
                "--batch-size", str(args.batch_size),
                "--gradient-accumulation-steps", str(args.gradient_accumulation_steps),
                "--learning-rate", str(args.learning_rate),
            ]
            if args.skip_ood:
                cmd.append("--skip-ood")
            res = subprocess.run(cmd)
            if res.returncode != 0:
                raise RuntimeError(f"Fold {fold_num} gagal dengan return code {res.returncode}")
    all_clean: list[dict] = []
    all_ood = {"mutation": [], "noise_10": [], "noise_25": [], "noise_50": []}
    all_predictions: list[dict] = []
    fold_reports: list[dict] = []
    for fold_num in range(1, args.folds + 1):
        fold_out = run_dir / f"fold_{fold_num}" / "fold_output.json"
        if not fold_out.exists():
            raise FileNotFoundError(f"Fold output tidak ditemukan: {fold_out}")
        data = json.loads(fold_out.read_text())
        all_clean.extend(data["clean"])
        all_predictions.extend(data["predictions"])
        fold_reports.append(data["report"])
        for name, values in data["ood"].items():
            all_ood[name].extend(values)
    if len(all_clean) != 74:
        raise RuntimeError(f"prediksi OOF harus 74, didapat {len(all_clean)}")
    summary = aggregate_results(all_clean)
    payload = {
        "config": config, "summary": summary, "bootstrap_macro_exact": _bootstrap_ci(all_clean),
        "ood_free_institution_fields": _summarize_ood(all_clean, all_ood) if not args.skip_ood else {},
        "runtime_seconds": time.perf_counter() - started, "n_out_of_fold_documents": len(all_clean),
        "folds": fold_reports, "per_cert_results": all_clean,
    }
    (run_dir / "results.json").write_text(json.dumps(payload, indent=2, default=str))
    (run_dir / "summary_oof.json").write_text(json.dumps(summary, indent=2))
    (run_dir / "folds.json").write_text(json.dumps(fold_reports, indent=2, default=str))
    (run_dir / "predictions.json").write_text(json.dumps(all_predictions, indent=2, default=str))
    return run_dir


def run_sanity_overfit(model_key: str, examples: list[Example], args: argparse.Namespace) -> Path:
    from tests.benchmark_ner_encoders import normalize_token
    training_examples, alignment_audit = build_gliner_training_examples(examples)
    selected = sorted(training_examples, key=lambda example: len(example.spans), reverse=True)[:2]
    if len(selected) != 2 or not all(example.spans for example in selected):
        raise RuntimeError("sanity memerlukan dua dokumen berlabel")
    originals = {example.stem: example for example in examples}
    sanity_args = argparse.Namespace(**vars(args))
    sanity_args.epochs = 20
    sanity_args.skip_ood = True
    run_dir = RUNS_DIR / f"gliner_sanity_{model_key.replace('-', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=False)
    fold_dir = run_dir / "fold_1"
    fold_dir.mkdir()
    runner = run_gliner2_fold if model_key == "gliner2.5-base" else run_gliner_v1_fold
    clean, _, predictions, report = runner(
        GLINER_MODELS[model_key], 0, selected, [originals[example.stem] for example in selected], fold_dir, sanity_args,
    )
    expected = {
        (span.label, normalize_token(span.matched_ocr_text), example.word_spans[span.start_word][0], example.word_spans[span.end_word - 1][1])
        for example in selected for span in example.spans
    }
    actual = {
        (entity["label"], normalize_token(entity["text"]), entity["start"], entity["end"])
        for prediction in predictions for entity in prediction["entities"]
    }
    missing = expected - actual
    if missing:
        raise RuntimeError(f"sanity span recall bukan 100%: {sorted(missing)!r}")
    if not report["all_parameters_finite"]:
        raise RuntimeError("parameter non-finite pada sanity")
    payload = {
        "model": model_key, "epochs": 20, "alignment": alignment_audit, "report": report,
        "span_exact_recall": 1.0, "expected_spans": len(expected), "predictions": predictions, "results": clean,
    }
    (run_dir / "sanity.json").write_text(json.dumps(payload, indent=2, default=str))
    return run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark GLiNER pada Tesseract OCR + GT v9")
    parser.add_argument("--mode", choices=("zero-shot", "fine-tune"), default="zero-shot")
    parser.add_argument("--models", nargs="+", choices=list(GLINER_MODELS), default=list(GLINER_MODELS))
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--fold", type=int, default=None, help="Index fold 1-N (jika ingin menjalankan satu fold saja)")
    parser.add_argument("--run-dir", type=str, default=None, help="Direktori run target")
    parser.add_argument("--epochs", type=float, default=10)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--sanity-overfit", action="store_true")
    parser.add_argument("--skip-ood", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "zero-shot":
        gt_rows = _load_gt_rows(GT_CSV)
        for model_key in args.models:
            run_benchmark(model_key, GLINER_MODELS[model_key], gt_rows, args.device)
        return
    from tests.benchmark_ner_encoders import build_examples
    examples, stats = build_examples()
    if stats != {"documents": 74, "fields_expected": 310, "fields_matched": 223, "fields_unmatched": 87}:
        raise RuntimeError(f"baseline encoder alignment berubah: {stats!r}")
    if args.fold is not None:
        if len(args.models) != 1:
            raise ValueError("--fold hanya dapat dijalankan untuk satu model")
        if not args.run_dir:
            raise ValueError("--fold memerlukan --run-dir")
        run_finetuned_fold(args.models[0], args.fold, Path(args.run_dir), examples, args)
        return
    if args.sanity_overfit:
        for model_key in args.models:
            print(f"Sanity overfit selesai: {run_sanity_overfit(model_key, examples, args)}")
        return
    for model_key in args.models:
        run_dir = run_finetuned_model(model_key, examples, args)
        print(f"Fine-tune OOF selesai: {run_dir}")


if __name__ == "__main__":
    main()
