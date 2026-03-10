# Repo Timeout Implementation

Date: 2026-03-09

## Implemented

- added timeout policy helpers in `src/skrisk/services/repo_analysis.py`
- added `RepoAnalysisTimeoutError`
- enforced worker-side repo deadlines with `SIGALRM` / `ITIMER_REAL`
- applied the resolved timeout in:
  - `MirroredRepoAnalysisService._analyze_candidate`
  - `AnalysisSpoolProducerService._analyze_candidate`
- threaded the same repo timeout into persistence
- applied Postgres `SET LOCAL statement_timeout` in `SkillRepository.persist_repo_analysis`

## Defaults

- normal repos: `45 minutes`
- Anthropic repos: `5 hours`

## Verification

- targeted runtime tests: timeout resolution and timeout argument propagation
- full suite: `145 passed`
- bytecode compilation: passed

## Operational follow-up

- reinstalled the editable package
- stopped the old producer and ingesters
- requeued in-flight ingest artifacts
- cleared stale spool claims
- restarted the AST producer and five ingesters on the timeout-aware code path
