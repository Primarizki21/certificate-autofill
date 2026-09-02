"""Benchmark NER encoder berbasis Tesseract dengan validasi out-of-fold.

Model base Hugging Face tidak dapat dievaluasi langsung sebagai NER. Runner ini
melatih head token-classification memakai BIO dari GT v9 dan hanya mengukur
prediksi pada fold yang tidak dipakai melatih model tersebut.

Usage:
    uv run python -m tests.benchmark_ner_encoders
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


import torch
import torch.nn.functional as F
from datasets import Dataset
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    Trainer,
    TrainingArguments,
    set_seed,
)

from app.services.field_extractor import ExtractedValue
from tests.evaluation_framework import EVAL_FIELDS, aggregate_results, evaluate_row, print_report
from tests.post_processors import score_entity_for_field

REPO = Path(__file__).resolve().parents[1]
GT_CSV = REPO / "Ground_Truth_Sertifikat_v9.csv"
TESSERACT_TEXTS = REPO / "tests" / "benchmark_runs" / "ocr_experiment" / "tesseract_primary_v4" / "extracted_texts"
RUNS_DIR = REPO / "tests" / "benchmark_runs"
LABEL_LIST = ["O", "B-ORG", "I-ORG", "B-EVT", "I-EVT", "B-DAT", "I-DAT", "B-NUM", "I-NUM"]
LABEL2ID = {label: index for index, label in enumerate(LABEL_LIST)}
ID2LABEL = {index: label for label, index in LABEL2ID.items()}
FIELD_TO_ENTITY = {
    "nama_kegiatan_sertifikasi": "EVT",
    "penyelenggara_kegiatan": "ORG",
    "waktu_mulai_pelaksanaan": "DAT",
    "waktu_selesai_pelaksanaan": "DAT",
    "nomor_bukti_fisik_nomor_sertifikasi": "NUM",
}
FREE_INSTITUTION_FIELDS = {
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "nomor_bukti_fisik_nomor_sertifikasi",
}
MODEL_SPECS = {
    "mdeberta-v3-base": "microsoft/mdeberta-v3-base",
    "xlm-roberta-large": "FacebookAI/xlm-roberta-large",
}
MAX_LENGTH = 512
STRIDE = 64
SEED = 42


@dataclass(frozen=True)
class NEREntity:
    entity_type: str
    text: str
    start: int
    end: int
    score: float


@dataclass(frozen=True)
class Example:
    stem: str
    filename: str
    text: str
    tokens: list[str]
    word_spans: list[tuple[int, int]]
    labels: list[int]
    expected: dict[str, str]
    matched_fields: tuple[str, ...]


def normalize_token(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def tokenize_with_spans(text: str) -> tuple[list[str], list[tuple[int, int]]]:
    matches = list(re.finditer(r"\S+", text))
    return [match.group() for match in matches], [(match.start(), match.end()) for match in matches]


def find_token_span(tokens: list[str], value: str) -> tuple[int, int] | None:
    needle = normalize_token(value)
    if not needle:
        return None
    normalized_tokens = [normalize_token(token) for token in tokens]
    flattened = "".join(normalized_tokens)
    start = flattened.find(needle)
    if start < 0:
        return None
    end = start + len(needle)
    positions: list[int] = []
    for index, token in enumerate(normalized_tokens):
        positions.extend([index] * len(token))
    if end > len(positions):
        return None
    return positions[start], positions[end - 1] + 1


def _read_tesseract_text(path: Path) -> str:
    return "\n".join(line for line in path.read_text().splitlines() if not line.startswith("#")).strip()


def _load_gt_rows(csv_path: Path) -> dict[str, dict[str, str]]:
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    output: dict[str, dict[str, str]] = {}
    for row in rows:
        normalized = {key.strip().lower().replace(" ", "_"): value for key, value in row.items()}
        filename = normalized.get("nama_file", "")
        if filename:
            output[Path(filename).stem] = normalized
    return output


def build_examples(csv_path: Path = GT_CSV, texts_dir: Path = TESSERACT_TEXTS) -> tuple[list[Example], dict[str, int]]:
    rows = _load_gt_rows(csv_path)
    examples: list[Example] = []
    stats = {"documents": 0, "fields_expected": 0, "fields_matched": 0, "fields_unmatched": 0}
    for text_path in sorted(texts_dir.glob("*.txt")):
        stem = text_path.stem
        expected = rows.get(stem)
        if expected is None:
            continue
        text = _read_tesseract_text(text_path)
        tokens, word_spans = tokenize_with_spans(text)
        if not tokens:
            continue
        labels = [LABEL2ID["O"]] * len(tokens)
        matched_fields: list[str] = []
        for field, entity_type in FIELD_TO_ENTITY.items():
            value = (expected.get(field) or "").strip()
            if not value or value == "-":
                continue
            stats["fields_expected"] += 1
            span = find_token_span(tokens, value)
            if span is None:
                stats["fields_unmatched"] += 1
                continue
            start, end = span
            labels[start] = LABEL2ID[f"B-{entity_type}"]
            for index in range(start + 1, end):
                labels[index] = LABEL2ID[f"I-{entity_type}"]
            matched_fields.append(field)
            stats["fields_matched"] += 1
        examples.append(Example(
            stem=stem,
            filename=expected.get("nama_file", stem),
            text=text,
            tokens=tokens,
            word_spans=word_spans,
            labels=labels,
            expected=expected,
            matched_fields=tuple(matched_fields),
        ))
    stats["documents"] = len(examples)
    return examples, stats


def stratified_folds(examples: list[Example], folds: int, seed: int = SEED) -> list[list[Example]]:
    if folds < 2:
        raise ValueError("folds minimal 2")
    if len(examples) < folds:
        raise ValueError("jumlah dokumen lebih kecil dari jumlah fold")
    buckets: dict[tuple[tuple[str, ...], int], list[Example]] = defaultdict(list)
    for example in examples:
        entity_types = tuple(sorted({LABEL_LIST[label].split("-", 1)[-1] for label in example.labels if label}))
        buckets[(entity_types, min(len(example.matched_fields), 5))].append(example)
    output: list[list[Example]] = [[] for _ in range(folds)]
    rng = random.Random(seed)
    for bucket in buckets.values():
        rng.shuffle(bucket)
        for index, example in enumerate(bucket):
            output[index % folds].append(example)
    if any(not fold for fold in output):
        raise AssertionError("stratifikasi menghasilkan fold kosong")
    return output


def tokenize_and_align(tokenizer, batch: dict[str, list[list[str]]]) -> dict:
    encoded = tokenizer(
        batch["tokens"],
        is_split_into_words=True,
        truncation=True,
        max_length=MAX_LENGTH,
        stride=STRIDE,
        return_overflowing_tokens=True,
    )
    sample_mapping = encoded.pop("overflow_to_sample_mapping")
    aligned_labels: list[list[int]] = []
    for encoding_index, source_index in enumerate(sample_mapping):
        source_labels = batch["labels"][source_index]
        previous_word_id = None
        aligned: list[int] = []
        for word_id in encoded.word_ids(batch_index=encoding_index):
            if word_id is None:
                aligned.append(-100)
            elif word_id != previous_word_id:
                aligned.append(source_labels[word_id])
            else:
                label = source_labels[word_id]
                aligned.append(label if label == LABEL2ID["O"] or label % 2 == 0 else label + 1)
            previous_word_id = word_id
        aligned_labels.append(aligned)
    encoded["labels"] = aligned_labels
    return encoded


def make_training_dataset(examples: list[Example], tokenizer) -> Dataset:
    raw = Dataset.from_dict({
        "tokens": [example.tokens for example in examples],
        "labels": [example.labels for example in examples],
    })
    return raw.map(
        lambda batch: tokenize_and_align(tokenizer, batch),
        batched=True,
        remove_columns=raw.column_names,
    )
def inverse_frequency_weights(dataset: Dataset) -> torch.Tensor:
    counts: Counter = Counter(label for row in dataset["labels"] for label in row if label != -100)
    largest = max(counts.values(), default=1)
    return torch.tensor(
        [min(math.sqrt(largest / counts.get(label, largest)), 10.0) for label in range(len(LABEL_LIST))],
        dtype=torch.float,
    )


class WeightedTokenTrainer(Trainer):
    def __init__(self, *args, class_weights: torch.Tensor, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights
        self.loss_calls = 0
        self.last_non_o_labels = 0

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs["labels"]
        self.loss_calls += 1
        self.last_non_o_labels = int(((labels != -100) & (labels != LABEL2ID["O"])).sum().item())
        outputs = model(**inputs)
        logits = outputs.logits
        if not torch.isfinite(logits).all():
            raise RuntimeError("logit non-finite selama training")
        loss = F.cross_entropy(
            logits.float().view(-1, logits.shape[-1]),
            labels.view(-1),
            weight=self.class_weights.to(logits.device),
            ignore_index=-100,
        )
        if not torch.isfinite(loss):
            raise RuntimeError("loss non-finite selama training")
        return (loss, outputs) if return_outputs else loss




def decode_entities(example: Example, word_predictions: dict[int, tuple[int, float]]) -> list[NEREntity]:
    entities: list[NEREntity] = []
    active_type: str | None = None
    active_start: int | None = None
    active_end: int | None = None
    active_scores: list[float] = []

    def close_active() -> None:
        nonlocal active_type, active_start, active_end, active_scores
        if active_type is not None and active_start is not None and active_end is not None:
            start = example.word_spans[active_start][0]
            end = example.word_spans[active_end - 1][1]
            entities.append(NEREntity(active_type, example.text[start:end], start, end, max(active_scores)))
        active_type = None
        active_start = None
        active_end = None
        active_scores = []

    for word_index in range(len(example.tokens)):
        label_id, score = word_predictions.get(word_index, (LABEL2ID["O"], 0.0))
        label = ID2LABEL[label_id]
        if label == "O":
            close_active()
            continue
        prefix, entity_type = label.split("-", 1)
        if prefix == "B" or active_type != entity_type:
            close_active()
            active_type = entity_type
            active_start = word_index
            active_end = word_index + 1
            active_scores = [score]
        else:
            active_end = word_index + 1
            active_scores.append(score)
    close_active()
    return entities


def predict_word_labels(model, tokenizer, example: Example) -> dict[int, tuple[int, float]]:
    encoded = tokenizer(
        example.tokens,
        is_split_into_words=True,
        truncation=True,
        max_length=MAX_LENGTH,
        stride=STRIDE,
        return_overflowing_tokens=True,
        return_tensors="pt",
        padding=True,
    )
    model.eval()
    device = next(model.parameters()).device
    encoded.pop("overflow_to_sample_mapping", None)
    model_inputs = {name: value.to(device) for name, value in encoded.items()}
    with torch.inference_mode():
        probabilities = torch.softmax(model(**model_inputs).logits, dim=-1)
    word_predictions: dict[int, tuple[int, float]] = {}
    for chunk_index in range(probabilities.shape[0]):
        previous_word_id = None
        for token_index, word_id in enumerate(encoded.word_ids(batch_index=chunk_index)):
            if word_id is None or word_id == previous_word_id:
                previous_word_id = word_id
                continue
            predicted_id = int(probabilities[chunk_index, token_index].argmax().item())
            predicted_score = float(probabilities[chunk_index, token_index, predicted_id].item())
            previous = word_predictions.get(word_id)
            if previous is None or predicted_score > previous[1]:
                word_predictions[word_id] = (predicted_id, predicted_score)
            previous_word_id = word_id
    return word_predictions


def predict_entities(model, tokenizer, example: Example) -> list[NEREntity]:
    return decode_entities(example, predict_word_labels(model, tokenizer, example))


def _merge_consecutive(entities: list[NEREntity]) -> list[NEREntity]:
    if not entities:
        return []
    merged: list[NEREntity] = []
    current = sorted(entities, key=lambda entity: entity.start)[0]
    for entity in sorted(entities, key=lambda entity: entity.start)[1:]:
        if 0 <= entity.start - current.end <= 3:
            current = NEREntity(
                current.entity_type,
                current.text + (" " if current.text[-1:].isalpha() and entity.text[:1].isalpha() else "") + entity.text,
                current.start,
                entity.end,
                max(current.score, entity.score),
            )
        else:
            merged.append(current)
            current = entity
    merged.append(current)
    return merged


def map_entities_to_fields(entities: list[NEREntity], full_text: str, source: str) -> dict[str, ExtractedValue]:
    fields: dict[str, ExtractedValue] = {}
    for entity_type, field in (("ORG", "penyelenggara_kegiatan"), ("EVT", "nama_kegiatan_sertifikasi"), ("NUM", "nomor_bukti_fisik_nomor_sertifikasi")):
        candidates = _merge_consecutive([entity for entity in entities if entity.entity_type == entity_type])
        if candidates:
            best = max(candidates, key=lambda entity: score_entity_for_field(entity, full_text))
            fields[field] = ExtractedValue(best.text, round(score_entity_for_field(best, full_text), 2), source)
    dates = _merge_consecutive([entity for entity in entities if entity.entity_type == "DAT"])
    if dates:
        start = dates[0]
        end = dates[-1]
        fields["waktu_mulai_pelaksanaan"] = ExtractedValue(start.text, round(start.score, 2), source)
        fields["waktu_selesai_pelaksanaan"] = ExtractedValue(end.text, round(end.score, 2), source)
    return fields


def _free_field_exact(row_result: dict) -> tuple[int, int]:
    selected = [result for field, result in row_result.items() if field in FREE_INSTITUTION_FIELDS]
    return sum(1 for result in selected if result["exact"]), len(selected)


def _mutate_institution(text: str) -> str:
    replacements = (("Universitas Airlangga", "Universitas Negeri Semarang"), ("UNAIR", "UNS"), ("FTMM", "FST"))
    for source, target in replacements:
        text = re.sub(re.escape(source), target, text, flags=re.IGNORECASE)
    return text


def _inject_ocr_noise(text: str, rate: float, rng: random.Random) -> str:
    substitutions = {"5": "S", "S": "5", "8": "B", "B": "8", "0": "O", "O": "0", "1": "I", "I": "1"}
    return "".join(substitutions.get(char, char) if char.upper() in substitutions and rng.random() < rate else char for char in text)


def _replace_text(example: Example, transform: Callable[[str], str]) -> Example:
    text = transform(example.text)
    tokens, word_spans = tokenize_with_spans(text)
    return Example(example.stem, example.filename, text, tokens, word_spans, example.labels, example.expected, example.matched_fields)


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
    return {"iterations": iterations, "mean": sum(values) / len(values), "lower_95": values[int(0.025 * (len(values) - 1))], "upper_95": values[int(0.975 * (len(values) - 1))]}


def _evaluate_fold(model, tokenizer, held_out: list[Example], source: str, include_ood: bool) -> tuple[list[dict], dict]:
    clean_results: list[dict] = []
    ood = {"mutation": [], "noise_10": [], "noise_25": [], "noise_50": []}
    for example in held_out:
        entities = predict_entities(model, tokenizer, example)
        mapped = map_entities_to_fields(entities, example.text, source)
        clean = evaluate_row(mapped, example.expected)
        clean_results.append(clean)
        if not include_ood:
            continue
        variants = {
            "mutation": _replace_text(example, _mutate_institution),
            "noise_10": _replace_text(example, lambda text: _inject_ocr_noise(text, 0.10, random.Random(f"{SEED}:{example.stem}:10"))),
            "noise_25": _replace_text(example, lambda text: _inject_ocr_noise(text, 0.25, random.Random(f"{SEED}:{example.stem}:25"))),
            "noise_50": _replace_text(example, lambda text: _inject_ocr_noise(text, 0.50, random.Random(f"{SEED}:{example.stem}:50"))),
        }
        for name, variant in variants.items():
            variant_entities = predict_entities(model, tokenizer, variant)
            variant_mapped = map_entities_to_fields(variant_entities, variant.text, source)
            ood[name].append(evaluate_row(variant_mapped, example.expected))
    return clean_results, ood


def _summarize_ood(clean: list[dict], ood: dict[str, list[dict]]) -> dict[str, dict[str, float]]:
    clean_exact, clean_total = map(sum, zip(*(_free_field_exact(row) for row in clean)))
    clean_acc = clean_exact / clean_total if clean_total else 0.0
    summary: dict[str, dict[str, float]] = {"clean": {"exact": clean_acc, "count": clean_total}}
    for name, rows in ood.items():
        exact, total = map(sum, zip(*(_free_field_exact(row) for row in rows))) if rows else (0, 0)
        acc = exact / total if total else 0.0
        summary[name] = {"exact": acc, "count": total, "drop_points": (clean_acc - acc) * 100}
    return summary


def _model_slug(model_name: str) -> str:
    return model_name.replace("/", "_").replace("-", "_").lower()


def _smoke_inference(model, tokenizer) -> None:
    for text in ("Sertifikat kegiatan DataQuest 4.0.", " ".join(["sertifikat"] * (MAX_LENGTH + 16))):
        tokens, word_spans = tokenize_with_spans(text)
        example = Example("_smoke", "_smoke.pdf", text, tokens, word_spans, [LABEL2ID["O"]] * len(tokens), {}, ())
        predict_entities(model, tokenizer, example)


def run_model(model_name: str, examples: list[Example], label_stats: dict[str, int], args: argparse.Namespace) -> Path:
    slug = _model_slug(model_name)
    run_dir = RUNS_DIR / f"ner_encoder_{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "labels_v9_tesseract.json").write_text(json.dumps({
        "source_gt": str(GT_CSV),
        "source_texts": str(TESSERACT_TEXTS),
        "label_list": LABEL_LIST,
        "stats": label_stats,
        "examples": [{"stem": example.stem, "tokens": example.tokens, "labels": [ID2LABEL[label] for label in example.labels], "matched_fields": example.matched_fields} for example in examples],
    }, indent=2))
    config = {
        "experiment": "NER-ENCODER-001",
        "model": model_name,
        "csv_path": str(GT_CSV),
        "gt_version": "v9",
        "ocr_corpus": str(TESSERACT_TEXTS),
        "folds": args.folds,
        "loss_variant": "sqrt_inverse_frequency_weighted" if args.class_weighted else "unweighted",
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "loss_variant": "inverse_frequency_weighted" if args.class_weighted else "unweighted",
        "max_length": MAX_LENGTH,
        "stride": STRIDE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gate": "valid OOF only; compare to NER v1 12.8% and direct Gemini reference 63.24% framework exact; no production promotion",
    }
    (run_dir / "config.json").write_text(json.dumps(config, indent=2))
    folds = stratified_folds(examples, args.folds)
    all_clean: list[dict] = []
    all_ood = {"mutation": [], "noise_10": [], "noise_25": [], "noise_50": []}
    fold_summaries: list[dict] = []
    total_started = time.perf_counter()
    for fold_index, held_out in enumerate(folds):
        train_examples = [example for index, fold in enumerate(folds) if index != fold_index for example in fold]
        fold_dir = run_dir / f"fold_{fold_index + 1}"
        fold_dir.mkdir()
        set_seed(SEED + fold_index)
        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        model = AutoModelForTokenClassification.from_pretrained(
            model_name,
            num_labels=len(LABEL_LIST),
            id2label=ID2LABEL,
            label2id=LABEL2ID,
            ignore_mismatched_sizes=True,
        )
        model.float()
        model.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
        model.config.use_cache = False
        if hasattr(model, "gradient_checkpointing_enable"):
            model.gradient_checkpointing_enable()
        if fold_index == 0:
            _smoke_inference(model, tokenizer)
        train_dataset = make_training_dataset(train_examples, tokenizer)
        class_weights = inverse_frequency_weights(train_dataset)
        use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
        training_args = TrainingArguments(
            output_dir=str(fold_dir / "checkpoint"),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.gradient_accumulation_steps,
            learning_rate=args.learning_rate,
            weight_decay=0.01,
            optim="adafactor",
            eval_strategy="no",
            save_strategy="no",
            logging_strategy="steps",
            logging_steps=50,
            report_to="none",
            seed=SEED + fold_index,
            data_seed=SEED + fold_index,
            fp16=torch.cuda.is_available() and not use_bf16,
            bf16=use_bf16,
            dataloader_num_workers=0,
        )
        trainer_kwargs = {
            "model": model,
            "args": training_args,
            "train_dataset": train_dataset,
            "data_collator": DataCollatorForTokenClassification(tokenizer),
        }
        trainer = (
            WeightedTokenTrainer(**trainer_kwargs, class_weights=class_weights)
            if args.class_weighted
            else Trainer(**trainer_kwargs)
        )
        started = time.perf_counter()
        trainer.train()
        clean, ood = _evaluate_fold(model, tokenizer, held_out, f"ner:{model_name}", not args.skip_ood)
        all_clean.extend(clean)
        for name, values in ood.items():
            all_ood[name].extend(values)
        fold_summary = aggregate_results(clean)
        fold_summaries.append({"fold": fold_index + 1, "train_documents": len(train_examples), "held_out_documents": len(held_out), "seconds": time.perf_counter() - started, "summary": fold_summary})
        del trainer, model, tokenizer, train_dataset
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    summary = aggregate_results(all_clean)
    ood_summary = _summarize_ood(all_clean, all_ood) if not args.skip_ood else {}
    bootstrap = _bootstrap_ci(all_clean)
    payload = {
        "config": config,
        "label_stats": label_stats,
        "summary": summary,
        "bootstrap_macro_exact": bootstrap,
        "folds": fold_summaries,
        "ood_free_institution_fields": ood_summary,
        "runtime_seconds": time.perf_counter() - total_started,
        "n_out_of_fold_documents": len(all_clean),
        "per_cert_results": all_clean,
    }
    (run_dir / "results.json").write_text(json.dumps(payload, indent=2, default=str))
    (run_dir / "summary_oof.json").write_text(json.dumps(summary, indent=2))
    (run_dir / "folds.json").write_text(json.dumps(fold_summaries, indent=2, default=str))
    return run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="5-fold OOF benchmark encoder NER pada OCR Tesseract + GT v9")
    parser.add_argument("--models", nargs="+", choices=sorted(MODEL_SPECS), default=sorted(MODEL_SPECS))
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--sanity-overfit", action="store_true")
    parser.add_argument("--class-weighted", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--skip-ood", action="store_true")
    return parser.parse_args()

def run_sanity_overfit(model_name: str, examples: list[Example], args: argparse.Namespace) -> dict[str, object]:
    selected = sorted(examples, key=lambda example: len(example.matched_fields), reverse=True)[:2]
    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    model = AutoModelForTokenClassification.from_pretrained(
        model_name,
        num_labels=len(LABEL_LIST),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        ignore_mismatched_sizes=True,
    )
    model.float()
    model.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    if hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()
    train_dataset = make_training_dataset(selected, tokenizer)
    class_weights = inverse_frequency_weights(train_dataset)
    trainer_kwargs = {
        "model": model,
        "args": TrainingArguments(
            output_dir=str(RUNS_DIR / "_ner_encoder_sanity"),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=1,
            learning_rate=args.learning_rate,
            max_grad_norm=1.0,
            optim="adafactor",
            eval_strategy="no",
            save_strategy="no",
            report_to="none",
            fp16=False,
            bf16=False,
        ),
        "train_dataset": train_dataset,
        "data_collator": DataCollatorForTokenClassification(tokenizer),
    }
    classifier_before = model.classifier.weight.detach().clone()
    trainer = (
        WeightedTokenTrainer(**trainer_kwargs, class_weights=class_weights)
        if args.class_weighted
        else Trainer(**trainer_kwargs)
    )
    trainer.train()
    if not torch.isfinite(model.classifier.weight).all():
        raise RuntimeError("classifier menjadi non-finite selama sanity")
    classifier_delta = float((model.classifier.weight.detach() - classifier_before).abs().max().item())
    non_o = correct = 0
    gold_hist: Counter = Counter()
    predicted_hist: Counter = Counter()
    for example in selected:
        prediction = predict_word_labels(model, tokenizer, example)
        for index, gold_label in enumerate(example.labels):
            predicted_label = prediction.get(index, (LABEL2ID["O"], 0.0))[0]
            gold_hist[ID2LABEL[gold_label]] += 1
            predicted_hist[ID2LABEL[predicted_label]] += 1
            if gold_label == LABEL2ID["O"]:
                continue
            non_o += 1
            correct += predicted_label == gold_label
    result = {
        "documents": len(selected),
        "non_o_tokens": non_o,
        "non_o_recall": correct / non_o if non_o else 0.0,
        "gold_histogram": dict(gold_hist),
        "predicted_histogram": dict(predicted_hist),
        "class_weighted": args.class_weighted,
        "class_weights": class_weights.tolist(),
        "trainer_global_step": trainer.state.global_step,
        "weighted_loss_calls": getattr(trainer, "loss_calls", 0),
        "last_non_o_labels": getattr(trainer, "last_non_o_labels", 0),
        "classifier_max_delta": classifier_delta,
    }
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return result




def smoke_model(model_name: str) -> None:
    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    model = AutoModelForTokenClassification.from_pretrained(
        model_name,
        num_labels=len(LABEL_LIST),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        ignore_mismatched_sizes=True,
    )
    model.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    _smoke_inference(model, tokenizer)
    del model, tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

def main() -> None:
    args = parse_args()
    if args.sanity_overfit:
        examples, _ = build_examples()
        for name in args.models:
            result = run_sanity_overfit(MODEL_SPECS[name], examples, args)
            print(json.dumps({"model": name, "sanity_overfit": result}, indent=2))
            if result["non_o_recall"] < 0.95:
                raise RuntimeError(f"sanity overfit gagal untuk {name}: {result['non_o_recall']:.2%}")
        return
    if args.smoke_only:
        for name in args.models:
            smoke_model(MODEL_SPECS[name])
            print(f"Smoke inference sukses: {name}")
        return
    examples, label_stats = build_examples()
    if label_stats["documents"] != 74:
        raise RuntimeError(f"korpus Tesseract harus 74 dokumen, ditemukan {label_stats['documents']}")
    if label_stats["fields_matched"] == 0:
        raise RuntimeError("tidak ada label BIO yang cocok pada korpus Tesseract")
    print(json.dumps({"label_stats": label_stats, "models": args.models, "folds": args.folds}, indent=2))
    for name in args.models:
        run_dir = run_model(MODEL_SPECS[name], examples, label_stats, args)
        result = json.loads((run_dir / "results.json").read_text())
        print(f"\nModel: {name}\nOutput: {run_dir}")
        print_report(result["summary"])
        print(json.dumps({"bootstrap_macro_exact": result["bootstrap_macro_exact"], "ood_free_institution_fields": result["ood_free_institution_fields"]}, indent=2))


if __name__ == "__main__":
    main()
