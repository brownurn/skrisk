# Deep Analysis Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add repo-first deep static analysis with CPU-bound parallel execution and richer hidden-domain discovery across the mirrored SK Risk corpus.

**Architecture:** Extend the current analyzer into a layered decoding and language-aware extraction pipeline, promote mirrored repositories to the primary analysis unit, and add a process-pool runner that analyzes discovered skills from local mirrors using about `80%` of host CPU cores. Persist results through the existing repository model, then rerun infrastructure enrichment and graph/search projection.

**Tech Stack:** Python 3.12, Click, SQLAlchemy asyncio, SQLite, `ast`, `shlex`, regex-based shell reconstruction, `ProcessPoolExecutor`, pytest

---

### Task 1: Add Failing Tests For Hidden Indicator Extraction

**Files:**
- Modify: `tests/test_analysis.py`

**Step 1: Write the failing tests**

Add tests for:
- bare-domain extraction from text without `http://`
- percent-decoded URLs
- unicode-escaped URLs/domains
- JavaScript `String.fromCharCode(...)` domain reconstruction
- Python string concatenation that yields a URL

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_analysis.py -q`

Expected: FAIL in the new deep-analysis test cases.

**Step 3: Write minimal implementation**

Extend the analyzer/deobfuscator code only enough to make the new extraction tests pass.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_analysis.py -q`

Expected: PASS for the updated analysis tests.

### Task 2: Add Language-Aware Structural Extraction

**Files:**
- Modify: `src/skrisk/analysis/analyzer.py`
- Create: `src/skrisk/analysis/language_extractors.py`
- Modify: `tests/test_analysis.py`

**Step 1: Write the failing tests**

Add targeted tests for:
- shell variable concatenation into a URL or domain
- Python callsites such as `requests.post(BASE + "/upload")`
- JS concatenation into `fetch("https://" + host + "/api")`

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_analysis.py -q`

Expected: FAIL for the new structural extraction tests.

**Step 3: Write minimal implementation**

Implement best-effort structural extraction helpers and integrate them into the analyzer output.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_analysis.py -q`

Expected: PASS.

### Task 3: Add Repo-First Analysis Service

**Files:**
- Create: `src/skrisk/services/repo_analysis.py`
- Modify: `src/skrisk/services/ingestion.py`
- Modify: `tests/test_ingestion.py`
- Modify: `tests/test_indicator_linking.py`

**Step 1: Write the failing tests**

Add tests proving a mirrored repo with multiple discovered skills:
- records one repo snapshot
- analyzes every discovered skill
- persists snapshots for unlisted repo-discovered skills

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_ingestion.py tests/test_indicator_linking.py -q`

Expected: FAIL because repo-first analysis of all discovered skills does not exist yet.

**Step 3: Write minimal implementation**

Add a repo analysis service that uses a local checkout to persist all discovered skills from one repo snapshot.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_ingestion.py tests/test_indicator_linking.py -q`

Expected: PASS.

### Task 4: Add Continuous CPU-Bound Analysis CLI

**Files:**
- Modify: `src/skrisk/cli.py`
- Create: `tests/test_cli_repo_analysis.py`

**Step 1: Write the failing tests**

Add CLI tests for a new command that:
- analyzes mirrored repos instead of recloning
- accepts a worker count or auto-computes `80%` of CPU cores
- supports bounded repo limits for incremental runs

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_cli_repo_analysis.py -q`

Expected: FAIL because the command does not exist yet.

**Step 3: Write minimal implementation**

Add the repo-analysis CLI and process-pool scheduling logic.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_cli_repo_analysis.py -q`

Expected: PASS.

### Task 5: Integrate Discovery Status And Unlisted Skill Handling

**Files:**
- Modify: `src/skrisk/storage/repository.py`
- Modify: `src/skrisk/api/routes.py`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `tests/test_api.py`

**Step 1: Write the failing tests**

Add API tests proving unlisted repo-discovered skills surface with:
- discovery status
- unknown impact status
- no fabricated install counts

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_api.py -q`

Expected: FAIL for the new discovery-status assertions.

**Step 3: Write minimal implementation**

Surface discovery status and unknown impact state without breaking existing listed-skill paths.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_api.py -q`

Expected: PASS.

### Task 6: Run Enrichment And Projection Over The Expanded Output

**Files:**
- Modify: `README.md`
- Modify: `docs/discussions/2026-03-09-skillsmp-live-rollout.md`

**Step 1: Run the deep analysis runtime**

Run the new repo-analysis command against the current mirrored corpus using the auto-computed worker count.

**Step 2: Run infrastructure enrichment**

Run: `skrisk enrich-infra --limit 1000`

**Step 3: Run search and graph projection**

Run:
- `skrisk index-search --limit 1000`
- `skrisk project-graph --limit 1000`

**Step 4: Document the live checkpoint**

Record:
- repos analyzed
- skills analyzed
- new indicators
- enrichment counts
- OpenSearch and Neo4j refresh status

### Task 7: Full Verification

**Files:**
- Modify: `docs/plans/2026-03-09-deep-analysis-runtime-design.md`
- Modify: `docs/plans/2026-03-09-deep-analysis-runtime-implementation.md`

**Step 1: Run targeted test suites**

Run:
- `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_analysis.py tests/test_ingestion.py tests/test_indicator_linking.py tests/test_api.py tests/test_cli_repo_analysis.py -q`

**Step 2: Run the full suite**

Run:
- `PYTHONPATH=src ../../.venv/bin/python -m pytest -q`

Expected: note any baseline pre-existing failures separately from feature regressions.

**Step 3: Run compile/build verification**

Run:
- `PYTHONPATH=src ../../.venv/bin/python -m compileall src`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run check`
- `cd frontend && npm run build`

**Step 4: Commit**

Commit the implementation once the new work is verified and the status is accurately documented.
