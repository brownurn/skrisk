# Postgres Runtime Scaling Design

Date: 2026-03-09

## Goal

Keep the Postgres-backed deep-analysis runtime progressing continuously by fixing two operational gaps:

- repos that cannot be analyzed must not remain permanently due
- multiple spool ingesters must be able to run safely in parallel

## Problem

After the SQLite-to-Postgres cutover, the system of record was no longer the bottleneck, but the runtime still had two queue-shape problems:

1. repos with missing mirrors or repeated analysis failures stayed due forever because only successful persistence advanced `next_scan_at`
2. the file spool only supported one ingester because every ingester read the same `pending/` directory without an exclusive claim step

The result was wasted producer work and a slower backlog drain than Postgres could actually support.

## Design

### Repo defer semantics

Add an explicit repository-level defer path that updates only `next_scan_at`.

Rules:

- missing mirror: defer `24` hours
- analysis failure: defer `6` hours
- successful ingest: keep the normal `72` hour rescan path

This preserves the meaning of `last_scanned_at`: only successful analysis should count as a completed scan.

### Multi-ingester spool claims

Keep the raw analysis spool on local disk, but split artifact handling into:

- `pending/`
- `ingesting/`

Each ingester atomically claims artifacts by moving them from `pending/` to `ingesting/`. That makes parallel ingesters safe without introducing a new DB queue.

Failure handling:

- successful ingest deletes the claimed artifact and releases the repo claim
- failed ingest requeues the artifact back to `pending/`
- stale `ingesting/` artifacts are automatically requeued on the next claim cycle

### Continuous producer behavior

Continuous producers should not exit just because the current due set is temporarily unclaimable. If repos are still due, the producer should sleep briefly and retry.

That matters for:

- repos already claimed by other producers
- due repos being deferred out of the window
- mixed batches where only a few repos are immediately analyzable

## Expected outcome

- bad repos stop cycling immediately
- parallel ingesters can drain the spool backlog materially faster
- Postgres remains the source of truth
- local disk remains the raw artifact archive
