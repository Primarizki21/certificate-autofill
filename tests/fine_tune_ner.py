import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import torch
from datasets import Dataset
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    Trainer,
    TrainingArguments,
)

MODEL_NAME = "indobenchmark/indobert-base-p1"
BIO_DIR = os.path.join(os.path.dirname(__file__), "bio_labels")
OUT_DIR = os.path.join(os.path.dirname(__file__), "ner_model")

LABEL_LIST = [
    "O",
    "B-ORG", "I-ORG",
    "B-EVT", "I-EVT",
    "B-DAT", "I-DAT",
    "B-NUM", "I-NUM",
    "B-PER", "I-PER",
]
LABEL2ID = {l: i for i, l in enumerate(LABEL_LIST)}
ID2LABEL = {i: l for l, i in LABEL2ID.items()}


def load_data():
    samples = []
    for fname in sorted(os.listdir(BIO_DIR)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        with open(os.path.join(BIO_DIR, fname)) as f:
            d = json.load(f)
        tokens = d["tokens"]
        labels = [LABEL2ID.get(l, 0) for l in d["labels"]]
        if len(tokens) != len(labels):
            continue
        samples.append({"tokens": tokens, "labels": labels, "filename": d["filename"]})
    return samples


def tokenize_and_align(tokenizer, examples):
    tokenized = tokenizer(
        examples["tokens"],
        is_split_into_words=True,
        max_length=512,
        truncation=True,
        padding="max_length",
    )
    aligned = []
    for i, labels in enumerate(examples["labels"]):
        word_ids = tokenized.word_ids(batch_index=i)
        previous = None
        row = []
        for word_id in word_ids:
            if word_id is None:
                row.append(-100)
            elif word_id != previous:
                row.append(labels[word_id])
            else:
                label = labels[word_id]
                row.append(label if label % 2 == 0 else label + 1)
            previous = word_id
        aligned.append(row)
    tokenized["labels"] = aligned
    return tokenized


def compute_metrics(pred):
    from seqeval.metrics import classification_report
    preds = pred.predictions.argmax(-1)
    true = pred.label_ids
    predictions, references = [], []
    for p, t in zip(preds, true):
        mask = [x != -100 for x in t]
        pred_labels = [ID2LABEL[x] for x, m in zip(p, mask) if m]
        true_labels = [ID2LABEL[x] for x, m in zip(t, mask) if m]
        predictions.append(pred_labels)
        references.append(true_labels)
    report = classification_report(references, predictions, output_dict=True, zero_division=0)
    return {
        "precision": report.get("micro avg", {}).get("precision", 0),
        "recall": report.get("micro avg", {}).get("recall", 0),
        "f1": report.get("micro avg", {}).get("f1-score", 0),
    }


def main():
    print("Loading data...")
    samples = load_data()
    print(f"Loaded {len(samples)} samples")

    split = int(len(samples) * 0.8)
    train_samples = samples[:split]
    val_samples = samples[split:]
    print(f"Train: {len(train_samples)}, Val: {len(val_samples)}")

    train_ds = Dataset.from_dict({
        "tokens": [s["tokens"] for s in train_samples],
        "labels": [s["labels"] for s in train_samples],
    })
    val_ds = Dataset.from_dict({
        "tokens": [s["tokens"] for s in val_samples],
        "labels": [s["labels"] for s in val_samples],
    })

    print("Loading tokenizer and model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForTokenClassification.from_pretrained(
        MODEL_NAME,
        num_labels=len(LABEL_LIST),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    print("Tokenizing...")
    train_ds = train_ds.map(
        lambda x: tokenize_and_align(tokenizer, x),
        batched=True,
        remove_columns=train_ds.column_names,
    )
    val_ds = val_ds.map(
        lambda x: tokenize_and_align(tokenizer, x),
        batched=True,
        remove_columns=val_ds.column_names,
    )

    data_collator = DataCollatorForTokenClassification(tokenizer)
    training_args = TrainingArguments(
        output_dir=OUT_DIR,
        num_train_epochs=5,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        learning_rate=2e-5,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        warmup_ratio=0.1,
        fp16=torch.cuda.is_available(),
        logging_steps=10,
        report_to="none",
        save_total_limit=2,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    print("Starting training...")
    trainer.train()

    print("Evaluating...")
    results = trainer.evaluate()
    print(f"Eval results: {results}")

    print("Saving model...")
    model.save_pretrained(OUT_DIR)
    tokenizer.save_pretrained(OUT_DIR)

    summary_path = os.path.join(OUT_DIR, "training_summary.json")
    with open(summary_path, "w") as f:
        json.dump({
            "model": MODEL_NAME,
            "method": "full_finetune",
            "epochs": 5,
            "lr": 2e-5,
            "train_samples": len(train_samples),
            "val_samples": len(val_samples),
            "eval_results": results,
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2)
    print(f"Model saved to {OUT_DIR}")
    print(f"Training complete. F1: {results.get('eval_f1', 'N/A')}")


if __name__ == "__main__":
    main()
