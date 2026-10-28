"""Generative & AUCC evaluation metrics module for certificate extraction."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from tests.date_normalizer import ALL_MONTHS, normalize_date
from tests.matchers import _levenshtein


BASE_6_FIELDS: tuple[str, ...] = (
    "nama_kegiatan_sertifikasi",
    "nomor_bukti_fisik_nomor_sertifikasi",
    "penyelenggara_kegiatan",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "tingkat",
)

AUCC_3_FIELDS: tuple[str, ...] = (
    "kelompok_kegiatan",
    "jenis_kegiatan",
    "prestasi_partisipasi_jabatan",
)

ALL_EVAL_FIELDS: tuple[str, ...] = BASE_6_FIELDS + AUCC_3_FIELDS + ("jenis_penyelenggara",)

VALID_TINGKAT_CLASSES: tuple[str, ...] = (
    "Internasional",
    "Nasional",
    "Universitas",
    "Fakultas",
    "Departemen",
    "Lainnya",
)


def normalize_text_tokens(text: str | None) -> list[str]:
    """Tokenize and normalize text by splitting on non-alphanumeric characters."""
    if not text:
        return []
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", str(text).lower())
    return [t for t in cleaned.split() if t]


def score_token_f1(pred: str | None, gold: str | None) -> tuple[float, float, float]:
    """Compute SQuAD-style token precision, recall, and harmonic F1."""
    pred_toks = normalize_text_tokens(pred)
    gold_toks = normalize_text_tokens(gold)

    if not pred_toks and not gold_toks:
        return 1.0, 1.0, 1.0
    if not pred_toks or not gold_toks:
        return 0.0, 0.0, 0.0

    common = Counter(pred_toks) & Counter(gold_toks)
    num_same = sum(common.values())

    if num_same == 0:
        return 0.0, 0.0, 0.0

    precision = num_same / len(pred_toks)
    recall = num_same / len(gold_toks)
    f1 = 2.0 * precision * recall / (precision + recall)
    return precision, recall, f1


def score_anls(pred: str | None, gold: str | None, threshold: float = 0.5) -> float:
    """Average Normalized Levenshtein Similarity (DocVQA standard)."""
    p_str = "" if pred is None else str(pred).strip().lower()
    g_str = "" if gold is None else str(gold).strip().lower()

    if not p_str and not g_str:
        return 1.0
    if not p_str or not g_str:
        return 0.0

    max_len = max(len(p_str), len(g_str))
    dist = _levenshtein(p_str, g_str)
    similarity = 1.0 - (dist / max_len)

    if similarity < threshold:
        return 0.0
    return max(0.0, min(1.0, similarity))


def _extract_date_components(raw: str | None) -> tuple[int | None, int | None, int | None]:
    """Extract day, month, year components from canonical or freeform date string."""
    if not raw or str(raw).strip() in ("-", ""):
        return None, None, None

    norm = normalize_date(str(raw))
    if norm:
        parts = norm.split("/")
        if len(parts) == 3:
            return int(parts[0]), int(parts[1]), int(parts[2])

    text = str(raw).lower()
    year_match = re.search(r"\b(19\d\d|20\d\d)\b", text)
    year = int(year_match.group(1)) if year_match else None

    month = None
    for m_name, m_num in ALL_MONTHS.items():
        if re.search(rf"\b{re.escape(m_name)}\b", text):
            month = int(m_num)
            break

    day_match = re.search(r"\b([0-2]?[1-9]|[12]0|3[01])\b", text)
    day = int(day_match.group(1)) if day_match else None

    return day, month, year


def score_date_field(pred: str | None, gold: str | None) -> tuple[bool, float]:
    """Evaluate date field using canonical equality and component partial credit."""
    p_str = "" if pred is None else str(pred).strip()
    g_str = "" if gold is None else str(gold).strip()

    if (not p_str or p_str == "-") and (not g_str or g_str == "-"):
        return True, 1.0
    if (not p_str or p_str == "-") or (not g_str or g_str == "-"):
        return False, 0.0

    p_norm = normalize_date(p_str)
    g_norm = normalize_date(g_str)
    if p_norm and g_norm and p_norm == g_norm:
        return True, 1.0

    p_d, p_m, p_y = _extract_date_components(p_str)
    g_d, g_m, g_y = _extract_date_components(g_str)

    # Component matching: 1/3 weight each
    y_match = 1.0 if (p_y and g_y and p_y == g_y) else 0.0
    m_match = 1.0 if (p_m and g_m and p_m == g_m) else 0.0
    d_match = 1.0 if (p_d and g_d and p_d == g_d) else 0.0

    comp_score = (y_match + m_match + d_match) / 3.0
    exact = (y_match == 1.0 and m_match == 1.0 and d_match == 1.0)
    return exact, comp_score


def normalize_cert_number(raw: str | None) -> str:
    """Normalize certificate number by removing non-alphanumeric delimiters."""
    if not raw:
        return ""
    return re.sub(r"[ .\-_\t/\\:;]+", "", str(raw).lower())


def score_cert_number_field(pred: str | None, gold: str | None) -> tuple[bool, float, float]:
    """Evaluate certificate ID: exact normalized equality, CharSim, and CER."""
    p_norm = normalize_cert_number(pred)
    g_norm = normalize_cert_number(gold)

    if not p_norm and not g_norm:
        return True, 1.0, 0.0
    if not p_norm or not g_norm:
        return False, 0.0, 1.0

    dist = _levenshtein(p_norm, g_norm)
    max_len = max(len(p_norm), len(g_norm))
    char_sim = max(0.0, 1.0 - (dist / max_len))
    cer = min(1.0, dist / len(g_norm))
    exact = (p_norm == g_norm)
    return exact, char_sim, cer


def canonicalize_tingkat(raw: str | None) -> str:
    """Map raw tingkat string to canonical KHP categories."""
    if not raw:
        return ""
    val = str(raw).strip().lower()
    for cat in VALID_TINGKAT_CLASSES:
        if cat.lower() == val or cat.lower() in val:
            return cat
    return str(raw).strip().title()


def score_tingkat_field(pred: str | None, gold: str | None) -> tuple[bool, str, str]:
    """Evaluate categorical tingkat against canonical classes."""
    p_canon = canonicalize_tingkat(pred)
    g_canon = canonicalize_tingkat(gold)
    if not p_canon and not g_canon:
        return True, "", ""
    return (p_canon == g_canon), p_canon, g_canon


def score_categorical_text(pred: str | None, gold: str | None) -> bool:
    """Evaluate exact categorical label agreement."""
    p_str = "" if pred is None else str(pred).strip().casefold()
    g_str = "" if gold is None else str(gold).strip().casefold()
    if not p_str and not g_str:
        return True
    return p_str == g_str


@dataclass(frozen=True, slots=True)
class FieldEvaluationResult:
    field: str
    pred: str | None
    gt: str | None
    exact: bool
    token_p: float = 0.0
    token_r: float = 0.0
    token_f1: float = 0.0
    char_sim: float = 0.0
    component_score: float = 0.0


@dataclass(frozen=True, slots=True)
class CertificateEvaluationResult:
    filename: str
    folder: str
    fields: dict[str, FieldEvaluationResult]
    record_exact_6f: bool
    record_exact_all: bool
    aucc_triplet_exact: bool


def evaluate_certificate_fields(
    filename: str,
    folder: str,
    predictions: Mapping[str, Any],
    ground_truth: Mapping[str, Any],
) -> CertificateEvaluationResult:
    """Evaluate all extracted fields of a single certificate using domain-appropriate metrics."""
    field_results: dict[str, FieldEvaluationResult] = {}

    for f_name in ALL_EVAL_FIELDS:
        p_val = predictions.get(f_name)
        g_val = ground_truth.get(f_name)

        if f_name in ("nama_kegiatan_sertifikasi", "penyelenggara_kegiatan"):
            p, r, f1 = score_token_f1(p_val, g_val)
            anls = score_anls(p_val, g_val)
            exact = (f1 == 1.0)
            field_results[f_name] = FieldEvaluationResult(
                field=f_name,
                pred=p_val,
                gt=g_val,
                exact=exact,
                token_p=p,
                token_r=r,
                token_f1=f1,
                char_sim=anls,
                component_score=f1,
            )
        elif f_name in ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"):
            exact, comp = score_date_field(p_val, g_val)
            field_results[f_name] = FieldEvaluationResult(
                field=f_name,
                pred=p_val,
                gt=g_val,
                exact=exact,
                component_score=comp,
                char_sim=comp,
                token_f1=1.0 if exact else comp,
            )
        elif f_name == "nomor_bukti_fisik_nomor_sertifikasi":
            exact, sim, _ = score_cert_number_field(p_val, g_val)
            field_results[f_name] = FieldEvaluationResult(
                field=f_name,
                pred=p_val,
                gt=g_val,
                exact=exact,
                char_sim=sim,
                component_score=sim,
                token_f1=1.0 if exact else sim,
            )
        elif f_name == "tingkat":
            exact, p_c, g_c = score_tingkat_field(p_val, g_val)
            field_results[f_name] = FieldEvaluationResult(
                field=f_name,
                pred=p_val,
                gt=g_val,
                exact=exact,
                token_f1=1.0 if exact else 0.0,
                component_score=1.0 if exact else 0.0,
                char_sim=1.0 if exact else 0.0,
            )
        else:
            # AUCC master taxonomy fields and jenis_penyelenggara
            exact = score_categorical_text(p_val, g_val)
            field_results[f_name] = FieldEvaluationResult(
                field=f_name,
                pred=p_val,
                gt=g_val,
                exact=exact,
                token_f1=1.0 if exact else 0.0,
                component_score=1.0 if exact else 0.0,
                char_sim=1.0 if exact else 0.0,
            )

    rec_6f = all(field_results[f].exact for f in BASE_6_FIELDS if f in field_results)
    aucc_triplet = all(field_results[f].exact for f in AUCC_3_FIELDS if f in field_results)
    rec_all = rec_6f and aucc_triplet and field_results.get("jenis_penyelenggara", FieldEvaluationResult("", None, None, True)).exact

    return CertificateEvaluationResult(
        filename=filename,
        folder=folder,
        fields=field_results,
        record_exact_6f=rec_6f,
        record_exact_all=rec_all,
        aucc_triplet_exact=aucc_triplet,
    )


@dataclass
class CorpusEvaluationSummary:
    total_docs: int = 0
    record_exact_6f_count: int = 0
    record_exact_all_count: int = 0
    aucc_triplet_exact_count: int = 0
    per_field_stats: dict[str, dict[str, float]] = field(default_factory=dict)
    tingkat_confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    tingkat_macro_f1: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_docs": self.total_docs,
            "record_exact_6f_pct": (self.record_exact_6f_count / max(1, self.total_docs)) * 100.0,
            "record_exact_all_pct": (self.record_exact_all_count / max(1, self.total_docs)) * 100.0,
            "aucc_triplet_pct": (self.aucc_triplet_exact_count / max(1, self.total_docs)) * 100.0,
            "per_field_stats": self.per_field_stats,
            "tingkat_macro_f1": self.tingkat_macro_f1,
            "tingkat_confusion": self.tingkat_confusion,
        }


def summarize_corpus_evaluations(
    results: Sequence[CertificateEvaluationResult],
) -> CorpusEvaluationSummary:
    """Aggregate per-certificate results into corpus summary statistics."""
    summary = CorpusEvaluationSummary(total_docs=len(results))
    if not results:
        return summary

    field_accumulators: dict[str, dict[str, float]] = {
        f: {"exact": 0.0, "token_f1": 0.0, "char_sim": 0.0, "component": 0.0, "count": 0.0}
        for f in ALL_EVAL_FIELDS
    }

    # Confusion matrix for Tingkat
    tingkat_conf: dict[str, dict[str, int]] = {
        c: {p: 0 for p in VALID_TINGKAT_CLASSES} for c in VALID_TINGKAT_CLASSES
    }

    for res in results:
        if res.record_exact_6f:
            summary.record_exact_6f_count += 1
        if res.record_exact_all:
            summary.record_exact_all_count += 1
        if res.aucc_triplet_exact:
            summary.aucc_triplet_exact_count += 1

        for f_name, f_res in res.fields.items():
            if f_name not in field_accumulators:
                field_accumulators[f_name] = {
                    "exact": 0.0,
                    "token_f1": 0.0,
                    "char_sim": 0.0,
                    "component": 0.0,
                    "count": 0.0,
                }
            acc = field_accumulators[f_name]
            acc["count"] += 1.0
            acc["exact"] += 1.0 if f_res.exact else 0.0
            acc["token_f1"] += f_res.token_f1
            acc["char_sim"] += f_res.char_sim
            acc["component"] += f_res.component_score

            if f_name == "tingkat":
                _, p_c, g_c = score_tingkat_field(f_res.pred, f_res.gt)
                if g_c in tingkat_conf and p_c in tingkat_conf[g_c]:
                    tingkat_conf[g_c][p_c] += 1

    summary.tingkat_confusion = tingkat_conf

    # Multiclass Macro-F1 for Tingkat
    class_f1s: list[float] = []
    for cls in VALID_TINGKAT_CLASSES:
        tp = tingkat_conf[cls].get(cls, 0)
        fp = sum(tingkat_conf[other].get(cls, 0) for other in VALID_TINGKAT_CLASSES if other != cls)
        fn = sum(tingkat_conf[cls].get(other, 0) for other in VALID_TINGKAT_CLASSES if other != cls)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2.0 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        if (tp + fn) > 0:  # only include classes present in ground truth
            class_f1s.append(f1)

    summary.tingkat_macro_f1 = (sum(class_f1s) / len(class_f1s)) if class_f1s else 0.0

    for f_name, acc in field_accumulators.items():
        n = max(1.0, acc["count"])
        summary.per_field_stats[f_name] = {
            "exact_pct": (acc["exact"] / n) * 100.0,
            "token_f1": acc["token_f1"] / n,
            "char_sim": acc["char_sim"] / n,
            "component_score": acc["component"] / n,
        }

    return summary
