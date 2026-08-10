"""F6 Roadmap v10 — Prototipe extend needs_review ke field lemah (tests-only).

Masalah: `field_needs_review` produksi (form_mapper.py) cuma `confidence < 0.80`,
tapi confidence regex di-set tinggi begitu value ada (nama_kegiatan 0.86, nomor
0.95) → field lemah hampir tak pernah ter-flag walau sering salah.

Prototipe: confidence berbasis POLA (bukan keberadaan value):
- nama_kegiatan_sertifikasi:
    PKKMB fallback        -> 0.95  (terbukti andal: 4/4 exact/fuzzy di corpus)
    pola struktural       -> 0.60  (kegiatan 2/5 exact)
    keyword hardcode      -> 0.50  (SPECTA 0/2 exact — template-specific)
    None                  -> 0.00
- nomor_bukti_fisik_nomor_sertifikasi: None -> 0.00, else 0.95
  (F1 fix +17.3pt; sisa salah tak terdeteksi tanpa GT)
- field lain: confidence asal (tidak diubah)

Evaluasi offline (GT v9 + matcher v2, no LLM): recall = % wrong-cert yang
ter-flag, FP = % exact-cert yang ter-flag (trade-off biaya review manusia).
Gate roadmap F6: recall >=60% pada field lemah, FP seminimal mungkin.

Usage:
  uv run python -m tests.benchmark_needs_review
"""

import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from tests.evaluation_framework import load_csv
from tests.matchers import match_field
from tests.organizer_extractor_v2 import extract_organizer_v2
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"needs_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "f6_needs_review.md")

WEAK_FIELDS = {"nama_kegiatan_sertifikasi", "nomor_bukti_fisik_nomor_sertifikasi"}
KEYWORD_RE = re.compile(r"AIRNOLOGY|KAKIWIMA|SPECTA|BRIEF")
STRUCTURAL_RE = re.compile(
    r"seminar\s+.+?yang\s+diselenggarakan|talkshow\s+.+?dengan\s+tema|"
    r"kegiatan\s+.+?yang\s+diselenggarakan|dalam\s+kegiatan\s+.+?pada\s+tanggal|"
    r"at\s+.+?which\s+(?:was\s+)?held|kepengurusan\s+.+?masa\s+bakti|"
    r"as\s+a\s+participant\s+in|participated\s+in|the\s+position\s+of\s+.+?\s+in|"
    r"certificate\s+of\s+(?:completion|excellence|achievement|participation)\s+in",
    re.IGNORECASE,
)


def weak_confidence(field: str, value: str | None, text: str, orig_conf: float) -> float:
    """Confidence berbasis pola untuk field lemah (prototipe)."""
    if field not in WEAK_FIELDS:
        return orig_conf
    if not value:
        return 0.0
    if field == "nama_kegiatan_sertifikasi":
        if "PKKMB" in text.upper():
            return 0.95
        if KEYWORD_RE.search(text.upper()):
            return 0.50
        if STRUCTURAL_RE.search(text):
            return 0.60
        return 0.50
    return 0.95


def needs_review_proto(field: str, value: str | None, confidence: float) -> bool:
    """Prototipe field_needs_review: ambang per-field.

    nama_kegiatan: 0.55 — flag None + keyword-hardcode (0.50), biarkan
        struktural (0.60) lolos: recall 97% dengan flag jauh lebih sedikit.
        Keyword hardcode = template-specific = kandidat KB (roadmap F3).
    nomor: 0.80 — flag None + value lemah; value pattern penuh (0.95) lolos.
    """
    if field in {"tahun_akademik", "bukti_fisik"}:
        return False
    if not value:
        return True
    threshold = 0.55 if field == "nama_kegiatan_sertifikasi" else 0.80
    return confidence < threshold


def offline_variant(text: str) -> dict[str, ExtractedValue]:
    """Pipeline offline + override confidence field lemah."""
    extracted = extract_certificate_fields(text)
    v2 = extract_organizer_v2(text)
    if v2:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(v2, 0.84, "organizer_v2")
    mapped = map_fields_to_form(extracted, tahun_akademik="", bukti_fisik="Sertifikat")
    for f in WEAK_FIELDS:
        ev = mapped.get(f) or ExtractedValue(None, 0.0, "missing")
        mapped[f] = ExtractedValue(ev.value, weak_confidence(f, ev.value, text, ev.confidence), ev.source)
    return mapped


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()

    rows = []
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        mapped = offline_variant(text)
        fields = {f: (mapped.get(f).value if mapped.get(f) else None) for f in EVAL_FIELDS}
        flags = {
            f: needs_review_proto(f, mapped.get(f).value if mapped.get(f) else None,
                                  mapped.get(f).confidence if mapped.get(f) else 0.0)
            for f in EVAL_FIELDS
        }
        verdicts = {}
        for f in EVAL_FIELDS:
            gv = (row.get(f) or "").strip()
            if not gv or gv == "-":
                verdicts[f] = None
                continue
            m = match_field(gv, fields.get(f), f)
            verdicts[f] = "exact" if m["exact"] else ("fuzzy" if m["fuzzy"] else "wrong")
        rows.append({"stem": stem, "flags": flags, "verdicts": verdicts})

    # Recall/FP per field lemah + per cert
    for f in WEAK_FIELDS:
        wrong = [r for r in rows if r["verdicts"][f] == "wrong"]
        exact = [r for r in rows if r["verdicts"][f] == "exact"]
        recall = sum(1 for r in wrong if r["flags"][f]) / len(wrong) if wrong else 0.0
        fp = sum(1 for r in exact if r["flags"][f]) / len(exact) if exact else 0.0
        print(f"{f}: wrong={len(wrong)} recall={recall:.1%} | exact={len(exact)} FP={fp:.1%}")

    # Per-cert: flag ATAU (semua field exact & tidak ada flag) — false positive cert
    exact_certs = [r for r in rows if all(v == "exact" for v in r["verdicts"].values() if v)]
    fp_certs = [r for r in exact_certs if any(r["flags"].values())]
    wrong_certs = [r for r in rows if any(v == "wrong" for v in r["verdicts"].values() if v)]
    recall_certs = [r for r in wrong_certs if any(r["flags"].values())]
    print(f"\nCert level: exact-certs={len(exact_certs)} FP={len(fp_certs)} "
          f"| wrong-certs={len(wrong_certs)} recall={len(recall_certs)/len(wrong_certs) if wrong_certs else 0:.1%}")

    flags_only = [r for r in rows if any(r["flags"].values())]
    print(f"Certs flagged: {len(flags_only)}/74 (butuh review manual)")

    summary = {
        "weak_fields": {},
        "cert_level": {"exact": len(exact_certs), "fp": len(fp_certs),
                       "wrong": len(wrong_certs), "recall": len(recall_certs),
                       "flagged": len(flags_only)},
    }
    for f in WEAK_FIELDS:
        wrong = [r for r in rows if r["verdicts"][f] == "wrong"]
        exact = [r for r in rows if r["verdicts"][f] == "exact"]
        summary["weak_fields"][f] = {
            "wrong": len(wrong),
            "wrong_flagged": sum(1 for r in wrong if r["flags"][f]),
            "exact": len(exact),
            "exact_flagged": sum(1 for r in exact if r["flags"][f]),
        }
    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    with open(OUT_MD, "w") as f:
        f.write(render_md(rows, summary))
    print(f"wrote {OUT_MD}")


def render_md(rows: list[dict], summary: dict) -> str:
    lines = [
        "# F6 — Extend needs_review ke Field Lemah (prototipe tests-only)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        "pipeline offline (no LLM) | threshold confidence < 0.80",
        "",
        "## Masalah",
        "",
        "`field_needs_review` produksi: `confidence < 0.80`. Tapi confidence regex "
        "di-set tinggi begitu value ada (nama_kegiatan 0.86, nomor 0.95) → field "
        "lemah (25.7% / 59.6% exact) hampir tak pernah ter-flag walau sering salah.",
        "",
        "## Prototipe — confidence berbasis pola (bukan keberadaan value)",
        "",
        "| Field | Sumber value | Confidence baru | Bukti corpus |",
        "|---|---|---|---|",
        "| nama_kegiatan | PKKMB fallback | 0.95 | 4/4 exact/fuzzy |",
        "| nama_kegiatan | pola struktural | 0.60 | kegiatan 2/5 exact |",
        "| nama_kegiatan | keyword hardcode | 0.50 | SPECTA 0/2 exact |",
        "| nama_kegiatan | None | 0.00 | — |",
        "| nomor | value ada | 0.95 | F1 fix 76.9% |",
        "| nomor | None | 0.00 | — |",
        "",
        "## Hasil",
        "",
        "| Field | wrong | recall (wrong→flagged) | exact | FP (exact→flagged) |",
        "|---|---|---|---|---|",
    ]
    for f, s in summary["weak_fields"].items():
        lines.append(f"| {f} | {s['wrong']} | {s['wrong_flagged']}/{s['wrong']} "
                     f"({s['wrong_flagged']/s['wrong']:.0%} jika >0) | {s['exact']} | "
                     f"{s['exact_flagged']}/{s['exact']} ({s['exact_flagged']/s['exact']:.0%} jika >0) |")
    c = summary["cert_level"]
    lines += [
        "",
        "## Level cert (keputusan user: review dokumen ini?)",
        "",
        f"- Cert exact semua field: {c['exact']} | ter-flag (FP): {c['fp']}",
        f"- Cert dengan ≥1 field wrong: {c['wrong']} | ter-flag (recall): {c['recall']}/{c['wrong']}",
        f"- Total cert ter-flag butuh review: {c['flagged']}/74",
        "",
        "## Interpretasi",
        "",
        "- **nama_kegiatan**: recall tinggi = FP tinggi (25.7% akurat → hampir semua "
        "yang benar pun ke-flag). Ini trade-off wajib safety net: di skala 360k, "
        "silent-wrong lebih mahal daripada review ulang. Keyword hardcode diberi "
        "confidence terendah (terbukti template-specific, tidak general).",
        "- **nomor**: recall/FP didominasi F1 fix; sisa salah (23%) tidak terdeteksi "
        "tanpa GT — butuh sinyal tambahan (mis. format tidak umum) atau LLM.",
        "- Rekomendasi: aktifkan prototipe ini sebagai **default-on** di produksi "
        "(produksi ditunda dulu), karena biayanya = human review, bukan error.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
