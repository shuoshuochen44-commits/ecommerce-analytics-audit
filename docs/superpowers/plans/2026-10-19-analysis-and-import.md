# Desktop analysis and import implementation plan

**Goal:** Expose the existing auditable question engine and make imports easier to diagnose without changing existing user data.

**Architecture:** Small HTTP adapter around the existing analysis engine; a separate browser script/style for question UX; structured tabular validation and conservative reusable mapping through SourceManager. Existing frozen desktop host stays in place.

**Tech Stack:** Python, DuckDB, existing HTTP server, plain JavaScript/CSS, pywebview, pytest.

## Task 1: Import validation and mapping reuse

- [x] Add failing behavior tests in tests/test_tabular_mapping.py, tests/test_source_manager.py and tests/test_connections_http.py for multi-error row/column diagnostics and unique remembered mapping suggestions.
- [x] Implement bounded structured validation in tabular_mapping.py, source_manager.py and source_http.py. Validate original row order before sorting canonical records; persist safe diagnostic errors; expose POST /api/sources/validate and remembered_mapping in preview responses.
- [x] Update connections.js/css with mapping progress, suggestion provenance and validation output; keep dashboard markup additions minimal and coordinated.
- [x] Run the import/source focused tests and inspect errors/restart compatibility.

## Task 2: Pinned analysis HTTP adapter

- [x] Create tests/test_analysis_http.py using a real temporary server. First assert GET /api/analysis/questions and POST /api/analysis/ask; confirm missing implementation fails.
- [x] Implement analysis_http.py: catalog; source resolution through handler.read_query; bounded same-origin JSON submission; mandatory snapshot_run_id; ask/run/replay routes; strict parameter validation and one shared analysis slot.
- [x] Connect adapter and analysis.js/css static routes in server.py.
- [x] Test known amount, filters, old snapshot after latest update, cross-source run lookup, replay, unknown input refusal, malicious/oversize request and server busy behavior.

## Task 3: Desktop question interface

- [x] Add analysis navigation/section and analysis.js/css assets. Use current.active_source, current.run_id and current.filters captured together at submit time.
- [x] Render grouped catalog and exact-text submission; state badges, numeric/table/chart results, full-snapshot quality warning scope and expandable SQL/parameters/citations/provenance. Hide numeric results on blocked responses.
- [x] Download the existing run record through a normal attachment route; replay the same pinned run; show stale scope/version notice and explicit rerun action after source/version/filter changes.
- [x] Check JavaScript syntax, then use the real desktop UI to verify analysis, refusal, result details and import diagnostics.

## Task 4: Verification and delivery

- [x] Run complete pytest suite, fix regressions and request independent review.
- [x] Update README and data/analysis docs to describe actual implemented behavior and limits.
- [x] Build desktop exe; verify frozen API behavior, open native window with independent workspace and capture a screenshot.
- [x] Hash Desktop workspace pointers and sample files; gracefully stop the existing own desktop app; replace only exe; relaunch and verify hashes/data retained.
- [x] Record acceptance evidence, commit changes and refresh source archive.
