# Handoff v7 - Cost-Aware Hybrid Extraction

> Supersedes `docs/handoff_v6.md`. This handoff defines the next improvement
> cycle for LLM v3 Variant B. The target is higher accuracy with lower effective
> token use at production scale.

---

## Current Baseline

The latest completed experiment is LLM v3 Variant B: context plus minimized
certificate text for `tingkat`.

Source: `docs/handoff_v6.md`, final run `run_llm_v3_20260731_113402/`.

| Metric | Current Variant B |
|--------|------------------:|
| Tingkat exact | 39.2% |
| MACRO exact | 46.4% |
| Tokens per certificate | 479 |
| LLM calls per certificate | 1 |
| Text compression | 70% |
| Organizer exact accuracy | 13.5% |

At 100,000 certificate requests:

```text
479 tokens x 100,000 requests = 47.9M tokens
```

The goal is not to minimize tokens at any cost. The goal is the best accuracy
and cost Pareto point.

### Baseline Rules

- Use the v6 final numbers as the baseline.
- Do not use the older `tests/benchmark_results.json` as the v7 baseline.
- Normalize `Departemen/Prodi` to `Departemen/Program Studi` before comparison.
- Keep `tests/llm_extractor_v3.py` unchanged during experiments.
- Create new experiment files first. Merge only after a winner is confirmed.

---

## Main Decision

Use two improvement tracks, in this order:

```text
Better evidence -> fewer LLM calls -> shorter prompts -> smaller/faster model
```

Do not start with more aggressive prompt trimming. Current `minimize_text()`
already removes about 70% of raw text. Further trimming before fixing organizer
evidence is likely to reduce accuracy.

### Why Evidence Comes First

The largest current bottleneck is organizer extraction. The hybrid organizer
exact rate is only 13.5%. Incorrect or missing organizer information also makes
`tingkat` impossible to infer reliably.

The v6 error analysis found that many wrong `tingkat` results are caused by:

- `UNIVERSITAS AIRLANGGA` being selected instead of the event organizer.
- OCR lines containing merged or duplicated text.
- English certificates containing both `FACULTY` and `DEPT` signals.
- `Nasional` being required even when no national-scale evidence appears in the
  certificate.

---

## Phase 0 - Reproduce and Classify Errors

### Goal

Create a stable v7 benchmark and an error taxonomy before changing extraction.

### Work

Create:

```text
tests/benchmark_llm_v4.py
```

Run the same 74 certificates through:

1. Hybrid + post-processing.
2. LLM v3 Variant B.
3. New experiment variants as they are added.

Every run must produce:

```text
tests/benchmark_runs/run_llm_v4_*/
  summary.json
  report.md
  mismatches.csv
  mismatches.xlsx
  extracted_fields.csv
  results.xlsx
  token_usage.json
  config.json
```

Classify each mismatch as one or more of:

- Organizer missing or wrong.
- OCR garbled or duplicated.
- English `FACULTY` versus `DEPT` conflict.
- HIMA or BEM scope ambiguity.
- National or international scale ambiguity.
- Missing evidence in the certificate.
- Wrong LLM output or invalid output.

### Pass Criteria

- New baseline stays within 1 percentage point of v6.
- No skipped certificates.
- Token, latency, and error counts are logged for every LLM call.

### Failure Action

Fix the benchmark before changing extraction. Do not tune prompts against an
unstable evaluator.

---

## Phase 1 - Organizer Extraction

### Goal

Improve the evidence used by both the deterministic mapper and LLM v3.

### Approach

Test a phrase-anchored organizer extractor. Prefer organization text near:

- `diselenggarakan oleh`
- `yang diselenggarakan oleh`
- `organized by`
- `held by`
- `presented by`

Candidate ranking should:

- Prefer the nearest organization phrase.
- Prefer BEM, HIMA, faculty, department, rectorate, and directorate signals.
- Penalize signer roles such as `Dekan`, `Direktur`, `Ketua`, and `NIP`.
- Penalize institution-only values when a specific organizer exists.
- Keep NER as a candidate generator, not as the final decision.

### Files

- `backend/app/services/field_extractor.py`
- `tests/ner_to_fields.py`
- Optional experiment helper: `tests/organizer_extractor_v2.py`

### Metrics

- Organizer exact and fuzzy accuracy.
- `tingkat` exact accuracy after organizer replacement.
- Organizer null rate.
- Regression rate for dates and certificate numbers.

### Pass Criteria

- Organizer exact improves from 13.5% to at least 30%.
- `tingkat` improves by at least 5 percentage points, or organizer improves by
  at least 10 percentage points without `tingkat` regression.
- No regression in date or certificate-number accuracy.

### Failure Action

Keep the existing organizer extractor. Do not merge a rule set that improves
one template while damaging unrelated certificate layouts.

---

## Phase 2 - Targeted OCR Improvement

### Goal

Improve only the OCR evidence needed for failed or ambiguous fields.

### Approach

Do not rewrite the complete OCR pipeline first. Test small changes:

- Normalize duplicate OCR lines before merging.
- Preserve line order from each OCR engine.
- Keep original text for output, but deduplicate using normalized text.
- Run an extra preprocessing pass only when organizer or `tingkat` evidence is
  missing.
- Use organizer-phrase extraction on OCR output before sending text to the LLM.

Current OCR merging removes only exact duplicate lines in
`backend/app/services/ocr_fallback.py`. Similar lines with small OCR changes
remain duplicated and consume context.

### Files

- `backend/app/services/ocr_fallback.py`
- `backend/app/services/pdf_fast_path.py` only if targeted rendering is needed
- New benchmark helper if the production OCR file must remain untouched

### Pass Criteria

- Organizer-related OCR failures decrease by at least 20%.
- Prompt input contains fewer duplicate lines.
- OCR latency increases by less than 30% on the full dataset.

### Failure Action

Drop preprocessing changes that add latency without measurable extraction gain.

---

## Phase 3 - Evidence-Based LLM Routing

### Goal

Reduce LLM calls without reducing accuracy.

v6 removed arbitrary confidence gating. v7 may add routing only after measuring
explicit high-precision rules.

### Candidate Deterministic Rules

Skip the LLM when one strong signal exists:

| Evidence | Direct value |
|----------|--------------|
| `DEPARTMENT`, `DEPT`, or `STUDY PROGRAM` | `Departemen/Program Studi` |
| HIMA or Himpunan Mahasiswa | `Departemen/Program Studi` |
| BEM plus faculty identifier | `Fakultas` |
| BEM Universitas, Rektorat, or Direktorat Kemahasiswaan | `Universitas` |

Call the LLM when:

- Signals conflict.
- Organizer extraction is missing.
- National or international scale is ambiguous.
- OCR quality is poor.
- The certificate contains only institution-level text.

### Method

Run the router in shadow mode first. Log the rule decision and compare it with
ground truth. Enable the router only after the shadow metrics pass.

### Files

- New experiment file: `tests/llm_router_v4.py`
- New benchmark: `tests/benchmark_llm_v4.py`
- Do not modify v3 during the experiment.

### Pass Criteria

- LLM calls decrease by at least 40%.
- MACRO remains at least 46.4%.
- High-confidence deterministic rules reach at least 95% precision.
- Conflicting signals are routed to the LLM, never silently forced.

### Failure Action

Disable routing and keep Variant B for all certificates.

---

## Phase 4 - Adaptive Prompt Compression

### Goal

Reduce tokens after routing has removed easy cases.

### Approach

Replace one fixed 300-character budget with difficulty-based budgets:

| Certificate type | Text budget |
|------------------|------------:|
| Strong structured evidence | 100-160 chars |
| Normal ambiguity | 180-220 chars |
| Conflicting or poor OCR | Up to 300 chars |

Shorten repeated prompt instructions while preserving:

- Exact allowed values.
- English department rule.
- HIMA and BEM rules.
- Institution-versus-level rule.
- One-value output requirement.

Do not add JSON only for formatting. JSON increases input tokens and does not
improve the current classification problem. Constrained output can be tested
later for response validity.

### Files

- New experiment file: `tests/llm_extractor_v4.py`
- Reuse helpers from `tests/llm_extractor_v3.py`

### Pass Criteria

- Effective average tokens per document: 200 or less after routing.
- `tingkat` accuracy decreases by no more than 1 percentage point.
- MACRO accuracy decreases by no more than 1 percentage point.

At 100,000 requests, the target is:

```text
20M tokens or less
```

This is at least a 58% reduction from the current 47.9M-token estimate.

### Failure Action

Keep the larger prompt for the affected certificate category. Do not apply one
small budget globally.

---

## Phase 5 - Domain Knowledge for Scale Classification

### Goal

Handle `Nasional` cases where the certificate itself contains no explicit scale
signal.

### Approach

Create a small approved knowledge map:

```text
event or organizer -> tingkat
```

Possible entries:

- Known national competitions.
- Known international conferences.
- Repeated university event series.
- Approved organizer-level mappings.

Rules:

- Do not derive mappings from test labels.
- Keep the map versioned.
- Test on held-out certificates.
- Return `needs_review` when evidence remains absent.
- Do not force the nearest category when the certificate has no signal.

### Pass Criteria

- National/international recall improves by at least 10 percentage points on
  held-out examples.
- No increase in false university or faculty classifications.

### Failure Action

Keep ambiguous cases as LLM or human-review cases. Do not add speculative
knowledge entries.

---

## Phase 6 - Model and ML Experiments

### Model Experiments

Run only after routing and prompt size are stable:

- Compare `llama3.1:8b` with a smaller structured-output model.
- Test constrained output for exact option validity.
- Measure latency, completion tokens, and accuracy separately.

Important distinctions:

- Quantization reduces memory and latency, not token count.
- `keep_alive` reduces model reload latency, not billed token count.
- Constrained output reduces completion tokens and invalid responses, not prompt
  tokens.

### ML Decision

Do not repeat NER fine-tuning with the current dataset. The previous attempt
failed because only 59 labeled certificates were available.

Collect at least 200-500 corrected certificates before testing:

- A lightweight `tingkat` classifier.
- An organizer candidate ranker.
- Layout-aware NER.
- Fine-tuned IndoBERT.

Until then, use NER for candidate generation and deterministic ranking.

---

## Phase 7 - Production Scale Controls

### Content-Hash Reuse

Check whether the same certificate is uploaded more than once. If duplicate
traffic exists, reuse extraction results by content hash.

Cache keys must include:

- Certificate SHA-256.
- Parser version.
- Mapper version.
- Prompt version when an LLM result is cached.

Do not add a cache abstraction before measuring duplicate traffic.

### Throughput

After accuracy is stable:

- Measure Ollama concurrency on the RTX 5050.
- Check VRAM before increasing parallel requests.
- Add retry limits and a review state for permanent LLM failures.
- Add batch processing only when bulk upload is an actual requirement.

---

## Experiment Matrix

| ID | Experiment | Main metric | Ship condition |
|----|------------|-------------|----------------|
| E0 | Reproduce v6 baseline | Macro and token drift | Within 1pp |
| E1 | Organizer phrase ranking | Organizer exact | At least 30% |
| E2 | Targeted OCR cleanup | OCR-related errors | 20% reduction |
| E3 | Rule router shadow mode | Calls and rule precision | 40% fewer calls, 95% precision |
| E4 | Adaptive prompt budget | Effective tokens | 200 or less/document |
| E5 | Domain knowledge map | National/international recall | +10pp held-out |
| E6 | Smaller/constrained model | Accuracy and latency | Within 2pp, faster |
| E7 | Hash reuse and concurrency | Throughput | Measured before rollout |

Each experiment must record:

- Hypothesis.
- Files changed.
- Backup or new-file command.
- Benchmark command.
- Exact and fuzzy metrics.
- Token and latency metrics.
- Pass condition.
- Revert condition.

---

## Final Ship Gate

Merge v7 only if all required conditions pass:

| Metric | Target |
|--------|-------:|
| Tingkat exact | At least 45% |
| MACRO exact | At least 50% |
| Effective tokens per document | 200 or less |
| 100K-request token budget | 20M or less |
| LLM call reduction | At least 40% |
| High-confidence rule precision | At least 95% |
| Date and certificate-number regression | None |

If accuracy and cost targets conflict, preserve the accuracy floor first and
route only the ambiguous cases to the LLM.

---

## Execution Order

```text
1. Commit current work and reproduce v6 baseline.
2. Build error taxonomy and mismatch report.
3. Improve organizer extraction in experiment files.
4. Test targeted OCR cleanup.
5. Run router in shadow mode.
6. Enable routing only if precision and macro pass.
7. Tune adaptive prompt budgets.
8. Add domain knowledge only with held-out validation.
9. Compare smaller models and constrained output.
10. Measure hash reuse and Ollama concurrency.
11. Integrate the winning path into production code.
12. Run the full test suite and final benchmark.
13. Update this handoff with actual results.
```

---

## Aturan Main

1. Commit before each experiment.
2. Keep v3 files unchanged until a winner is confirmed.
3. Use new experiment files instead of overwriting production code.
4. Run the full 74-certificate benchmark after every meaningful change.
5. Log `prompt_eval_count`, `eval_count`, latency, model, and prompt version.
6. Do not tune against one certificate template.
7. Use grouped or held-out validation when domain knowledge is added.
8. Run `uv run python -m pytest tests/ -v` before integration.
9. Keep ambiguous results reviewable instead of forcing unsupported guesses.

### Commands

```bash
uv run python -m tests.llm_extractor_v3
uv run python -m tests.benchmark_llm_v3
uv run python -m tests.benchmark_llm_v3 --limit 10
uv run python -m tests.benchmark_llm_v2
uv run python -m tests.benchmark_llm
uv run python -m pytest tests/ -v
```

---

## Files of Interest

| File | Purpose |
|------|---------|
| `docs/handoff_v6.md` | Completed v3 token-minimization experiment |
| `tests/llm_extractor_v3.py` | Current Variant A and Variant B implementation |
| `tests/benchmark_llm_v3.py` | Current v3 benchmark runner |
| `tests/llm_extractor.py` | Ollama client, validation, token logging |
| `backend/app/services/field_extractor.py` | Regex field extraction and organizer fallback |
| `backend/app/services/ocr_fallback.py` | RapidOCR and Tesseract merge |
| `tests/ner_to_fields.py` | NER entity-to-field mapping |
| `tests/post_processors.py` | Entity filtering and signer handling |
| `tests/evaluation_framework.py` | Exact, fuzzy, WER, CER, and report generation |

## Expected Next Session Output

The next session should start with Phase 0 and produce:

- `tests/benchmark_llm_v4.py`.
- A reproducible v6 baseline report.
- A categorized `mismatches.csv`.
- A decision on whether organizer extraction or OCR is the first implementation
  target.

Do not integrate changes into `backend/app/services/extraction_pipeline.py`
until the final ship gate passes.
