# Repo Timeout Design

Date: 2026-03-09

## Problem

The AST repo-first runtime can stall for hours when a single mirrored repository is unusually large or triggers extremely expensive parsing or persistence work. This blocks queue drain and makes ETAs meaningless.

## Decision

Apply a repo-level timeout policy with an Anthropic override:

- default repo analysis timeout: `45 minutes`
- Anthropic repo analysis timeout: `5 hours`

The timeout must cover both phases of repo processing:

1. worker-side static analysis
2. database persistence of that repo's analysis artifact

## Design

### Analysis timeout

- Resolve timeout from repo identity:
  - if publisher or repo name contains `anthropic`, use `5 hours`
  - otherwise use `45 minutes`
- Enforce the worker-side limit inside the worker process with a real alarm, not only a parent-side await timeout.
- Use a process-local alarm so the repo task raises and unwinds instead of sitting in a worker indefinitely.

### Persistence timeout

- Pass the resolved repo timeout into the persistence path.
- On Postgres, apply `SET LOCAL statement_timeout` for the transaction that persists a single repo analysis.
- This bounds large `skill_indicator_links` merges and other expensive repo-sized writes.

## Scope

- `produce-analysis-spool`
- `analyze-mirrors`
- repo ingestion/persistence helpers

## Expected result

- one pathological repo no longer holds a worker forever
- oversized repo artifacts cannot run unbounded in Postgres
- the continuous scan remains productive even when the corpus contains huge monorepos
