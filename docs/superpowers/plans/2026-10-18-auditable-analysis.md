# Auditable Analysis Implementation Plan

> **For agentic workers:** Execute inline with TDD and review checkpoints. User approved this milestone on 2026-10-18. The original repository's pending import changes are independent.

**Goal:** Deliver 30 offline Chinese question templates with bounded SQL execution, independent verification and replayable manifests.

**Architecture:** `query_gateway.py` owns parser and execution policy; `question_catalog.py` owns question definitions and SQL; `answer_verifier.py` independently computes from raw tables; `analysis.py` orchestrates pinned snapshots and manifests; `analysis_cli.py` exposes listing, execution and replay.

**Tech Stack:** Python 3.11, DuckDB 1.5.6, SQLGlot 28.10.1, pytest 9.1.1.

## Execution result

All five tasks completed. Final clean-environment regression: 127 tests passed. Fixture and 12,000-order China-demo template acceptance: 30/30 each; pinned replays matched. See `docs/analysis-acceptance.md`. Implementation uses one declared order-to-item join rather than two arbitrary joins. Independent raw date parsing uses primitive DuckDB CAST for source-format compatibility, while business aggregation uses Python/Decimal. Added explicit synthetic fixture metadata to preserve truthful provenance.

## Task 1: Safe SQL gateway

- [x] Create `tests/test_query_gateway.py` before `src/zhishu_inspection/query_gateway.py`. Test a SELECT, CTE with parameters, unknown columns, write/DDL, multi-statements, filesystem/table functions, recursive CTE, cross join, source-row/output-row limits and timeout. Check database contents remain unchanged.
- [x] Run `python -m pytest tests/test_query_gateway.py -q`; verify missing feature fails.
- [x] Implement AST whitelist, qualification, read-only settings, preflight source counts, interrupt timer, complete bounded fetch and typed values.
- [x] Repeat targeted tests; review policy and error boundaries.

## Task 2: Thirty definitions and raw-data verifier

- [x] Create `tests/test_question_catalog.py` and `tests/test_answer_verifier.py`. Assert 30 unique IDs/texts, unknown question refusal, fixture amounts 230.00/orders 2/customers 1/AOV 115.00, repeat buyers 1, cancellation 1, and complete per-question expected tables. Include filtered and empty results.
- [x] Verify missing-feature failures with targeted pytest.
- [x] Implement `question_catalog.py` with explicit dependencies/citations and parameterized SQL. Implement `answer_verifier.py` using only raw reads and independent Python Decimal grouping, distinct counts and rankings.
- [x] Run targeted tests; verify unknown category behavior, null sums, ties and customer deduplication.

## Task 3: Orchestration and immutable records

- [x] Create `tests/test_analysis.py` for all directory entries, quality impact, mismatch fail-closed, malformed input, pinned replay, simultaneous run IDs and JSON round-trip.
- [x] Run tests red; implement `analysis.py` structured responses, dependency-specific warnings, result comparisons, immutable records and replay.
- [x] Run tests green. Logs must exclude free-text questions, customer IDs and arbitrary exception details.

## Task 4: CLI and reproducible local acceptance

- [x] Create `tests/test_analysis_cli.py` for question listing, analysis, replay and nonzero error exits. Verify failures.
- [x] Implement `analysis_cli.py`, register `zhishu-analyze`, pin new dependency, and implement `scripts/verify_analysis.py` with checked-in manual fixture expectations rather than generated reference answers.
- [x] Document runnable commands and explicitly label template-only coverage. Do not present results as LLM evaluation.

## Task 5: Validation and delivery

- [x] Run all tests in the isolated source tree with a dedicated temporary directory. Existing committed baseline: 68 passed.
- [x] Run one-command fixture acceptance and China demo acceptance. Read output JSON and manifests.
- [x] Review changes, resolve material findings, commit this feature branch and provide a patch plus source path. Do not push or merge into the original repository while its other development is pending.

## Verification environment

During this session the existing project's interpreter supplies DuckDB/pytest; only SQLGlot is installed into ignored `.deps/`. Set `PYTHONPATH` to this checkout's `src` and `.deps`, so imports never fall back to the other checkout's editable package. Document normal clean installation via pyproject and requirements-lock for users.
