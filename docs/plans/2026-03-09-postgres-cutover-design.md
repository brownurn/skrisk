# Postgres Cutover Design

## Goal

Move SK Risk's source-of-truth database from SQLite to Postgres so the deep-analysis spool runtime can scale past the current single-writer ingest ceiling.

## Problem

The current producer/consumer analysis runtime solved the CPU-side bottleneck, but the SQLite ingester remains serialized behind a single writer. Producers are now faster than persistence, so the spool backlog grows instead of draining. That blocks the broader repo-first analysis rollout.

## Recommended Approach

Use Postgres as the primary database, keep OpenSearch and Neo4j as projections, and keep local disk under `archive_root` as the immutable artifact store.

Why Postgres:

- concurrent writers and better transaction behavior for the spool ingester
- native support for `ON CONFLICT`, row claims, and future `SKIP LOCKED` queue semantics
- a good fit for JSON-heavy snapshot data
- cleaner long-term path than trying to push SQLite further

We are not changing the archive layout or the producer spool format in this phase. The cutover only changes the system of record and the runtime wiring around it.

## Architecture

### Runtime shape

- producers keep analyzing mirrored repos and writing compact spool artifacts to disk
- one ingester continues draining artifacts during this phase
- Postgres becomes the canonical metadata store
- SQLite remains only as the migration source

### Database access

- replace SQLite-only session factory usage with a generic async SQLAlchemy session factory
- normalize database URLs so operators can provide either `sqlite:///...` or `postgresql://...`
- keep SQLite-specific additive schema migration helpers guarded behind the SQLite dialect

### Migration

- add a CLI command to copy the existing SQLite corpus into Postgres
- initialize the Postgres schema before copying data
- preserve primary keys during migration
- reset Postgres ID sequences after copy so future inserts continue cleanly

### Deployment

- add Postgres to `docker-compose.yml`
- document `SKRISK_DATABASE_URL`
- verify that the API and CLI commands run unchanged once the environment points at Postgres

## Portability Changes

The repository layer currently uses expressions that must work on both SQLite and Postgres. This phase standardizes the remaining JSON and scalar-clamp expressions so list pages, scoring, and infrastructure candidate queries behave consistently on both backends.

## Scope

In scope:

- generic async database factory
- Postgres driver dependency
- Docker Compose Postgres service
- SQLite-to-Postgres migration command
- repository portability fixes
- runtime documentation and local cutover steps

Out of scope for this phase:

- rewriting the spool queue into a DB-backed claim system
- running multiple ingesters in parallel
- object storage migration for archives
- Timescale or partitioning work

## Verification

The cutover is complete when:

- targeted database/runtime tests pass
- the broader API/repository test slice still passes
- `skrisk init-db` succeeds against Postgres
- the SQLite corpus copies into Postgres successfully
- the SK Risk API starts against Postgres
- the spool runtime can be relaunched with `SKRISK_DATABASE_URL` pointing at Postgres
