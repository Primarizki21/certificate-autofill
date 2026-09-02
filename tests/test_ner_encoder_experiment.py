import torch

from tests.benchmark_ner_encoders import (
    LABEL2ID,
    Example,
    NEREntity,
    _mutate_institution,
    find_token_span,
    map_entities_to_fields,
    stratified_folds,
    tokenize_with_spans,
)


def _example(stem: str) -> Example:
    text = "Sertifikat Festival Data oleh BEM FTMM nomor 123/ABC/2024 pada 12 Mei 2024"
    tokens, spans = tokenize_with_spans(text)
    return Example(
        stem=stem,
        filename=f"{stem}.pdf",
        text=text,
        tokens=tokens,
        word_spans=spans,
        labels=[LABEL2ID["O"]] * len(tokens),
        expected={},
        matched_fields=(),
    )


def test_find_token_span_ignores_punctuation_and_case():
    tokens, _ = tokenize_with_spans("Nomor: ABC/123-XY, diterbitkan")

    assert find_token_span(tokens, "abc 123 xy") == (1, 2)


def test_token_spans_round_trip_original_text():
    text = "Acara\nDataQuest 4.0"
    tokens, spans = tokenize_with_spans(text)

    assert tokens == [text[start:end] for start, end in spans]


def test_mapper_uses_num_label_and_full_text():
    text = "Nomor sertifikat 123/ABC/2024"
    entity = NEREntity("NUM", "123/ABC/2024", 18, 30, 0.91)

    fields = map_entities_to_fields([entity], text, "ner:test")

    assert fields["nomor_bukti_fisik_nomor_sertifikasi"].value == "123/ABC/2024"
    assert fields["nomor_bukti_fisik_nomor_sertifikasi"].source == "ner:test"


def test_stratified_folds_hold_every_example_once():
    examples = [_example(f"cert-{index}") for index in range(10)]

    folds = stratified_folds(examples, folds=5)

    assert sorted(example.stem for fold in folds for example in fold) == [f"cert-{index}" for index in range(10)]
    assert all(len(fold) == 2 for fold in folds)

class _FakeEncoding(dict):
    def word_ids(self, batch_index: int):
        return [None, 0, 1, None]


class _FakeTokenizer:
    def __call__(self, *args, **kwargs):
        return _FakeEncoding(
            input_ids=torch.tensor([[0, 1, 2, 3]]),
            attention_mask=torch.tensor([[1, 1, 1, 1]]),
            overflow_to_sample_mapping=torch.tensor([0]),
        )


class _FakeModel:
    def __init__(self):
        self.eval_called = False
        self.parameter = torch.nn.Parameter(torch.zeros(1))
        self.forward_keys: set[str] | None = None

    def parameters(self):
        return iter([self.parameter])

    def eval(self):
        self.eval_called = True
        return self

    def __call__(self, **kwargs):
        self.forward_keys = set(kwargs)
        return type("Output", (), {"logits": torch.zeros((1, 4, 9))})()


def test_predict_entities_sets_eval_mode_before_forward():
    from tests.benchmark_ner_encoders import predict_entities

    model = _FakeModel()
    tokens, spans = tokenize_with_spans("Acara Data")
    example = Example("cert", "cert.pdf", "Acara Data", tokens, spans, [0, 0], {}, ())

    predict_entities(model, _FakeTokenizer(), example)

    assert model.eval_called
    assert "overflow_to_sample_mapping" not in model.forward_keys


def test_institution_mutation_preserves_non_institution_text():
    text = "Festival Data FTMM Universitas Airlangga 12 Mei 2024"

    mutated = _mutate_institution(text)

    assert "Festival Data" in mutated
    assert "12 Mei 2024" in mutated
    assert "Universitas Airlangga" not in mutated
