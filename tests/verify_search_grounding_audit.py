"""Automated cross-check, arithmetic, and metadata validator for EXP-SEARCH-GROUNDING-001 artifacts."""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = REPO_ROOT / "docs/experiments/EXP-SEARCH-GROUNDING-001/run_C_scaled_audit"
CHECKPOINT_PATH = RUN_DIR / "checkpoint_run_C_scaled.jsonl"
METRICS_PATH = RUN_DIR / "comparative_metrics.json"
RUN_C_MD_PATH = RUN_DIR / "run_c_summary.md"
SUMMARY_MD_PATH = REPO_ROOT / "docs/experiments/EXP-SEARCH-GROUNDING-001/comparative_summary.md"


def test_verify_run_c_artifacts() -> None:
    assert CHECKPOINT_PATH.exists(), f"Missing checkpoint: {CHECKPOINT_PATH}"
    assert METRICS_PATH.exists(), f"Missing metrics: {METRICS_PATH}"
    assert RUN_C_MD_PATH.exists(), f"Missing run c summary: {RUN_C_MD_PATH}"
    assert SUMMARY_MD_PATH.exists(), f"Missing main summary: {SUMMARY_MD_PATH}"

    with open(CHECKPOINT_PATH, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    assert len(records) == 30, f"Expected 30 records, got {len(records)}"

    ctrl_recs = [r for r in records if r["variant"] == "v3_text_control"]
    srch_recs = [r for r in records if r["variant"] == "v3_search_cot"]

    assert len(ctrl_recs) == 15
    assert len(srch_recs) == 15

    # 1. Per-record arithmetic verification: total == token + search
    for r in records:
        expected_total = round(r["token_cost_idr"] + r["search_grounding_cost_idr"], 2)
        actual_total = round(r["total_effective_cost_idr"], 2)
        assert expected_total == actual_total, (
            f"Arithmetic mismatch in {r['variant']} for {r['nama_file']}: "
            f"token={r['token_cost_idr']} + search={r['search_grounding_cost_idr']} "
            f"= {expected_total} != {actual_total}"
        )

    # 2. Check accuracy
    tkt_c = sum(1 for r in ctrl_recs if r["eval"]["tingkat"]["exact"])
    tkt_s = sum(1 for r in srch_recs if r["eval"]["tingkat"]["exact"])
    assert tkt_c == 11 and tkt_s == 11, f"Tingkat count mismatch: {tkt_c}, {tkt_s}"

    # 3. Check queries
    q_c = sum(r["web_queries_count"] for r in ctrl_recs)
    q_s = sum(r["web_queries_count"] for r in srch_recs)
    assert q_c == 0 and q_s == 5, f"Queries mismatch: {q_c}, {q_s}"

    # 4. Check grounded documents
    grounded_docs = [r for r in srch_recs if r["web_queries_count"] > 0]
    assert len(grounded_docs) == 3, f"Expected 3 grounded docs, got {len(grounded_docs)}"
    assert sorted(r["web_queries_count"] for r in grounded_docs) == [1, 2, 2]

    # 5. Check aggregate costs
    tot_c_tok = round(sum(r["token_cost_idr"] for r in ctrl_recs), 2)
    tot_c_cost = round(sum(r["total_effective_cost_idr"] for r in ctrl_recs), 2)
    assert tot_c_tok == 186.52
    assert tot_c_cost == 186.52

    tot_s_tok = round(sum(r["token_cost_idr"] for r in srch_recs), 2)
    tot_s_fee = round(sum(r["search_grounding_cost_idr"] for r in srch_recs), 2)
    tot_s_cost = round(sum(r["total_effective_cost_idr"] for r in srch_recs), 2)

    assert tot_s_tok == 187.86, f"Search token sum mismatch: {tot_s_tok}"
    assert tot_s_fee == 1243.05, f"Search fee sum mismatch: {tot_s_fee}"
    assert tot_s_cost == 1430.91, f"Search total cost mismatch: {tot_s_cost}"
    assert round(tot_s_tok + tot_s_fee, 2) == tot_s_cost

    # 6. Verify metrics JSON
    with open(METRICS_PATH, encoding="utf-8") as f:
        mj = json.load(f)
    assert mj["results"]["v3_text_control"]["costs_idr"]["total_effective_cost_idr"] == 186.52
    assert mj["results"]["v3_search_cot"]["costs_idr"]["total_effective_cost_idr"] == 1430.91
    assert mj["results"]["v3_search_cot"]["search_grounding"]["total_web_queries"] == 5

    # 7. Verify Markdown Tables row-by-row for BOTH comparative_summary.md AND run_c_summary.md
    summary_md = SUMMARY_MD_PATH.read_text(encoding="utf-8")
    run_c_md = RUN_C_MD_PATH.read_text(encoding="utf-8")

    # Assert metadata phrasing in both files
    for name, text in [("comparative_summary.md", summary_md), ("run_c_summary.md", run_c_md)]:
        assert "cached_tokens dan thoughts_tokens: tidak dicatat oleh runner ini (missing / not recorded)" in text, (
            f"Missing required metadata disclaimer in {name}"
        )
        assert "1.430,91" in text, f"Missing 1.430,91 in {name}"
        assert "1.430,92" not in text, f"Stale 1.430,92 found in {name}"

        # Assert aggregate summary table rows
        m_agg_total = re.search(
            r"\|\s*\*\*Total Biaya Efektif Keseluruhan\*\*\s*\|\s*\*\*Rp\s*186,52\*\*\s*\|\s*\*\*Rp\s*1\.430,91\*\*",
            text,
        )
        assert m_agg_total, f"Aggregate total cost row missing or mismatched in {name}"

        m_agg_tkt = re.search(
            r"\|\s*\*\*Akurasi Tingkat \(Exact %\)\*\*\s*\|\s*\*\*73\.33%\*\*\s*\(11/15\)\s*\|\s*\*\*73\.33%\*\*\s*\(11/15\)",
            text,
        )
        assert m_agg_tkt, f"Aggregate tingkat accuracy row missing or mismatched in {name}"

    files_in_order = [r["nama_file"] for r in ctrl_recs]
    ctrl_map = {r["nama_file"]: r for r in ctrl_recs}
    srch_map = {r["nama_file"]: r for r in srch_recs}

    for idx, fname in enumerate(files_in_order, 1):
        pattern = (
            rf"^\|\s*{idx}\s*\|\s*`([^`]+)`[^|]*\|\s*([^|]+)\|\s*(\d+)\s*\/\s*(\d+)\s*\|"
            rf"\s*Rp\s*([\d\.]+)\s*\|\s*([^|]+)\|\s*(\d+)\s*\/\s*(\d+)\s*\|\s*(\d+)\s*Q\s*\|"
            rf"\s*Rp\s*([\d\.]+)\s*\|\s*Rp\s*([\d\.]+)\s*\|"
        )
        m_sum = re.search(pattern, summary_md, re.MULTILINE)
        m_runc = re.search(pattern, run_c_md, re.MULTILINE)
        assert m_sum, f"Row {idx} missing in comparative_summary.md"
        assert m_runc, f"Row {idx} missing in run_c_summary.md"

        c = ctrl_map[fname]
        s = srch_map[fname]

        # Check values in comparative_summary.md
        _, _, cp_s, cc_s, c_cost_s, _, sp_s, sc_s, sq_s, sfee_s, s_cost_s = m_sum.groups()
        assert int(cp_s) == c["prompt_tokens"]
        assert int(cc_s) == c["candidates_tokens"]
        assert float(c_cost_s) == c["total_effective_cost_idr"]
        assert int(sp_s) == s["prompt_tokens"]
        assert int(sc_s) == s["candidates_tokens"]
        assert int(sq_s) == s["web_queries_count"]
        assert float(sfee_s) == s["search_grounding_cost_idr"]
        assert float(s_cost_s) == s["total_effective_cost_idr"]

        # Check values in run_c_summary.md
        _, _, cp_r, cc_r, c_cost_r, _, sp_r, sc_r, sq_r, sfee_r, s_cost_r = m_runc.groups()
        assert int(cp_r) == c["prompt_tokens"]
        assert int(cc_r) == c["candidates_tokens"]
        assert float(c_cost_r) == c["total_effective_cost_idr"]
        assert int(sp_r) == s["prompt_tokens"]
        assert int(sc_r) == s["candidates_tokens"]
        assert int(sq_r) == s["web_queries_count"]
        assert float(sfee_r) == s["search_grounding_cost_idr"]
        assert float(s_cost_r) == s["total_effective_cost_idr"]


if __name__ == "__main__":
    test_verify_run_c_artifacts()
    print("Verification successfully passed! All 30 records, arithmetic invariants, metrics JSON, and tables are in 100% agreement.")
