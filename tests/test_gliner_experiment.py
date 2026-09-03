from argparse import Namespace
from types import SimpleNamespace

from tests.benchmark_gliner import (
    GlinerTrainingExample,
    GlinerTrainingSpan,
    GlinerTrainingWindow,
    _gliner2_entities,
    _gliner_v1_span_width,
    build_gliner_training_examples,
    finetune_manifest,
    to_gliner2_examples,
    to_gliner_v1_records,
    window_gliner_example,
)
from tests.benchmark_ner_encoders import build_examples, stratified_folds


class WordTokenizer:
    def __call__(self, tokens, **_kwargs):
        return {"input_ids": [0, *range(len(tokens)), 1]}


def test_gliner_v1_records_use_inclusive_end():
    window = GlinerTrainingWindow(
        "sample", "a b c", ["a", "b", "c"], 0, 5, 0, 3,
        (GlinerTrainingSpan(2, 3, "certificate number", "nomor_bukti_fisik_nomor_sertifikasi", "c"),),
    )
    assert to_gliner_v1_records([window]) == [{
        "tokenized_text": ["a", "b", "c"],
        "ner": [[2, 2, "certificate number"]],
    }]


def test_gliner2_keeps_two_date_mentions_and_validates():
    window = GlinerTrainingWindow(
        "sample", "1 Januari 2024 sampai 2 Januari 2024", ["1", "Januari", "2024", "sampai", "2", "Januari", "2024"],
        0, 38, 0, 7,
        (
            GlinerTrainingSpan(0, 3, "date", "waktu_mulai_pelaksanaan", "1 Januari 2024"),
            GlinerTrainingSpan(4, 7, "date", "waktu_selesai_pelaksanaan", "2 Januari 2024"),
        ),
    )
    records = to_gliner2_examples([window])
    assert records[0].entities == {"date": ["1 Januari 2024", "2 Januari 2024"]}
    assert records[0].validate() == []


def test_alignment_rejects_unmatched_and_ambiguous_labels():
    examples, _ = build_examples()
    _, audit = build_gliner_training_examples(examples)
    assert audit["candidate_found"] == 223
    assert audit["initial_unmatched"] == 87
    assert audit["first_hit_nonexact"] == 17
    assert audit["whole_token_ambiguous"] == 65
    assert audit["whole_token_unambiguous"] == 148
    assert audit["boundary_unmatched"] == 10
    assert audit["usable_label_tuples"] == 130

def test_manifest_contains_parity_contract():
    manifest = finetune_manifest(
        "gliner-multi-v2.1",
        Namespace(folds=5, epochs=10, batch_size=1, gradient_accumulation_steps=8, learning_rate=2e-5),
        {"usable_label_tuples": 130},
        "checkpoint-revision",
    )
    assert manifest["checkpoint_revision"] == "checkpoint-revision"
    assert manifest["effective_batch_size"] == 8
    assert manifest["max_length"] == 512
    assert manifest["stride"] == 64
    assert manifest["lora"] is False


def test_gliner_v1_width_reads_nested_span_head():
    model = SimpleNamespace(model=SimpleNamespace(span_rep_layer=SimpleNamespace(span_rep_layer=SimpleNamespace(max_width=64))))
    assert _gliner_v1_span_width(model) == 64

def test_window_moves_boundary_and_preserves_long_span():
    tokens = [f"w{index}" for index in range(768)]
    text = " ".join(tokens)
    positions = []
    cursor = 0
    for token in tokens:
        positions.append((cursor, cursor + len(token)))
        cursor += len(token) + 1
    span = GlinerTrainingSpan(470, 530, "event name", "nama_kegiatan_sertifikasi", " ".join(tokens[470:530]))
    example = GlinerTrainingExample("long", text, tokens, positions, {}, (span,))
    windows = window_gliner_example(example, WordTokenizer())
    assert any(window.word_start <= 470 and 530 <= window.word_end for window in windows)
    assert all(len(window.tokens) + 2 <= 512 for window in windows)


def test_folds_are_deterministic_disjoint_and_complete():
    examples, _ = build_examples()
    first = stratified_folds(examples, 5, seed=42)
    second = stratified_folds(examples, 5, seed=42)
    first_stems = [[example.stem for example in fold] for fold in first]
    assert first_stems == [[example.stem for example in fold] for fold in second]
    assert len(set().union(*(set(stems) for stems in first_stems))) == 74
    assert sum(len(stems) for stems in first_stems) == 74


def test_gliner2_response_keeps_api_confidence_and_spans():
    entities = _gliner2_entities({"entities": {"date": [{"text": "1 Januari 2024", "confidence": 0.75, "start": 2, "end": 16}]}}, 10)
    assert entities[0].score == 0.75
    assert (entities[0].start, entities[0].end) == (12, 26)
