# Postgres Runtime Scaling Implementation

Date: 2026-03-09

## Scope

This follow-up implements the first runtime scaling pass after the Postgres cutover.

## Changes

### Repository

- add `SkillRepository.defer_repo_scan(...)`
- update only `next_scan_at`
- do not mark deferred repos as successfully scanned

### Producer services

Apply the same defer behavior to both repo-first analysis paths:

- `src/skrisk/services/analysis_spool.py`
- `src/skrisk/services/repo_analysis.py`

Behavior:

- missing mirrors are collected and deferred for `24` hours
- analysis failures are deferred for `6` hours
- continuous mode sleeps and retries instead of exiting when the due set still exists but no candidate can be claimed immediately

### Spool ingestion

Extend `AnalysisSpool` with:

- `ingesting/` directory
- atomic `claim_pending_artifacts(...)`
- `requeue_artifact(...)`
- `requeue_stale_ingesting(...)`

Update `AnalysisSpoolIngestService` to ingest only claimed artifacts so multiple ingesters can run concurrently on Postgres.

## Verification

Required verification for this change:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_analysis_spool.py tests/test_repo_analysis.py tests/test_cli_repo_analysis.py tests/test_cli.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m compileall src
```

## Live rollout

1. stop old spool producer and ingester processes
2. preserve pending artifacts
3. remove only stale repo claim files that have no pending or ingesting artifact
4. restart:
   - `skrisk produce-analysis-spool --limit-repos 100 --workers 24 --continuous`
   - three `skrisk ingest-analysis-spool --limit-artifacts 100 --continuous` processes
5. verify that:
   - `pending/` shrinks over time
   - `ingesting/` is non-zero while ingesters are busy
   - `skill_repo_snapshots` and `skill_snapshots` continue increasing
   - `due_repos` continues dropping
