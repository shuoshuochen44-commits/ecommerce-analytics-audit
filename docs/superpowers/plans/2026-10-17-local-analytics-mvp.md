# Local Analytics MVP Implementation Plan

> **For agentic workers:** Execute inline in this session, preserving the user's continuous collaboration preference. Work through the checklist and verify each data contract before proceeding.

**Goal:** Deliver a reproducible local dashboard with validated modeling, quality results and atomic snapshot publication.

**Architecture:** SQL owns modeled tables; Python owns rule execution, snapshots and fixed read-only queries. A dependency-free local HTTP server serves a Chinese dashboard. Each successful run is immutable and published through an atomic latest.json pointer.

**Tech Stack:** Python 3.11, DuckDB, pytest, HTML/CSS/JS, standard-library HTTP.

## Tasks

- [x] Add failing model tests in tests/test_modeling.py: grain, one-to-many totals, orphan preservation and zero denominator. Run with `.\.venv\Scripts\python.exe -m pytest tests/test_modeling.py -v`.
- [x] Implement sql/model/*.sql, quality.py and modeling.py. Validate raw keys/types before model SQL; compare four modeled KPIs to raw baselines, preserve missing detail/payment states and build dws_daily_state.
- [x] Add failing rule tests covering pass/fail for all eight required rules. Run targeted tests, implement fixed rule catalog with failures, sample keys, affected metrics and blocking policy.
- [x] Add failing pipeline tests for successful publication, repeat runs, changed snapshot and failure preserving latest. Implement pipeline.py with file hashing, per-run database, manifests, error log and atomic pointer. Never mutate prior successful runs.
- [x] Add failing query tests for date/state filters, uniqueness across groups, empty scope, invalid parameters and category reconciliation. Implement analytics.py with bound parameters, read-only snapshot access, fixed SQL and money serialization.
- [x] Add HTTP tests for response validation and safe routing. Implement server.py and web/dashboard.html, scoped parameters and explicit global quality scope.
- [x] Run complete tests and full real-data pipeline twice. Compare semantic reports, cross-check baseline totals, exercise HTTP endpoints and inspect dashboard with browser tools.
- [x] Update README, model/metric documentation and outputs/ local delivery report and launch scripts. Commit the verified milestone and preserve it for user review.

## Completion evidence

Record actual test count, real pipeline totals, input fingerprint, repeat-run equality and browser verification. A failed step is fixed and rerun before claiming completion. No external publication, invented business effect or unsupported financial metrics.
