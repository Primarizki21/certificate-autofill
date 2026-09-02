# Watchdog Notes — Certificate Autofill Prototype

## Review Priorities

Especially watch for:

### Pipeline Integrity (highest priority)
- Changes to `extraction_pipeline.py`, `combined_extractor.py`, `form_mapper.py`, `field_extractor.py` — these are production-critical. Any edit must preserve the current MACRO exact baseline (87.42% framework).
- Staging flags (`ENABLE_COMBINED_V4_2` and similar) must default to `False`. Never flip to `True` without explicit user approval — this is a safety gate.
- The 4-layer empirical proof (cross-validation, OOD stress, semantic anchors, calibrated confidence) must not be weakened. Any rule/router change needs all 4 layers re-verified.

### Frozen Baselines
- `Ground_Truth_Sertifikat_v9.csv` and `tests/matchers.py` (matcher v2) are **frozen**. Any modification requires explicit user approval.
- `Ground_Truth_Sertifikat_v8.csv` is frozen as historical reference. Do not modify.
- Run benchmarks with `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv` only.

### Production Promotion Safety
- Pipeline promotion from staging → production requires: QA/QC pipeline → user review → **explicit user approval** → toggle flag → smoke test → commit.
- Never silently promote. No assume-approval.

### Experiment Discipline
- Test code lives in `tests/`. Production code in `backend/app/services/` must not be modified by experiments without approval.
- Every experiment entry in `docs/experiments_ledger.md` must be atomic (hipotesis, hasil, verdict, re-try condition).
- Handoff updates (`docs/handoff_v*.md`) required after 5-10 ledger entries or major milestones.
- Failed trials = knowledge. Do not delete or hide failures.

### ExtractedValue Invariant
- All parsing/mapping output must be wrapped in `ExtractedValue(value, confidence, source)`. No raw strings.
- `needs_review = True` when confidence < 0.85, unrouted/ambiguous, or missing fields. Target recall review ≥ 95%.

### Rule Priority in form_mapper.py
- Rules have strict priority order. Do not rearrange:
  - `PKKMB` checked before `panitia`
  - `Panitia` checked before `pengurus organisasi`
  - Seminar/workshop with participant status cannot become "Pengurus Organisasi"
  - `DIREKTUR KEMAHASISWAAN` checked before HIMA rules
  - HIMA signature mapping requires explicit Airlangga context

### OCR Gotchas
- `pytesseract` requires system-level Tesseract installation — not pip-installable.
- `rapidocr-onnxruntime` downloads models on first run.
- Docling first call is slow (model download).
- OCR errors have known aliases in `field_extractor.py` (AGUSTU5→AGUSTUS, SEPTEM8ER→SEPTEMBER, etc.)

### Database Safety
- PDFs stored as `BYTEA` in `document_files.pdf_data`.
- No migration tool — `Base.metadata.create_all()` in `init_db()`. Schema changes require manual coordination.
- PostgreSQL runs on port 5434, database `certautofill`.

### Code Conventions
- Python: snake_case, type hints on every function, dataclasses for value objects.
- Comments and UI labels in **Bahasa Indonesia**.
- Frontend: vanilla HTML/CSS/JS, no framework, no build step.
- Import order: stdlib → third-party → local, no blank lines between groups.

### Anti-Patterns to Reject
- Hardcoded event names in regex — use structural semantic anchors instead.
- Regex matching titles instead of grammatical patterns (e.g., `sebagai [Role] pada [Kegiatan] yang diselenggarakan oleh [Penyelenggara]`).
- Bypassing the pipeline orchestrator to call parsers directly.
- Adding LLM calls to the offline pipeline without justification (Combined v4.x is designed for 0 LLM).
