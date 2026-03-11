# Neo4j Bulk Import Design

## Goal

Replace the current transactional Neo4j graph rebuild with an offline bulk import path that can rebuild the full SK Risk graph from the Postgres corpus in hours instead of days.

## Problem

The current graph projector is structurally too slow for the live corpus:

- it loads one skill detail at a time from Postgres
- it expands that skill into many `MERGE` statements
- it sends those statements over Neo4j's HTTP transaction endpoint
- it repeats that loop for `224k+` skills

Even after statement chunking and process-level sharding, the runtime remains dominated by Python-side per-skill expansion and per-request transaction overhead. The live estimate was still on the order of weeks, which is not acceptable.

## Chosen Approach

Use a two-phase offline rebuild:

1. Export the canonical graph as CSV files directly from Postgres.
2. Stop the Neo4j service and run `neo4j-admin database import full` against those CSV files.

This uses Neo4j's native bulk loader instead of transactional Cypher writes.

## Why This Approach

This is the fastest practical change that fits the current repo and runtime:

- Postgres already contains the fully normalized graph source of truth.
- Neo4j is already running in Docker and includes `neo4j-admin`.
- `neo4j-admin database import full` is built for high-throughput initial loads.
- We only need a full rebuild after a completed analysis wave, so an offline import window is acceptable.

Alternatives rejected:

- More HTTP transaction parallelism:
  still pays per-skill query and per-transaction costs.
- Bolt-only rewrite:
  better than HTTP, but still keeps the same per-skill transactional shape.
- Leaving the current projector as-is:
  empirically too slow on the live corpus.

## Data Shape

The bulk import should preserve the existing graph model, based on the latest snapshot for each skill:

### Node sets

- `Skill`
- `Repo`
- `Registry`
- `Indicator`
- `ASN`
- `Registrar`
- `Organization`
- `Nameserver`

### Relationship sets

- `HOSTED_IN`
- `SEEN_IN`
- `EMITS`
- `RESOLVES_TO`
- `ANNOUNCED_BY`
- `REGISTERED_WITH`
- `REGISTERED_TO`
- `USES_NAMESERVER`

The bulk importer should continue using the latest snapshot only, not all historical snapshots, because that is what the current graph UI and graph projection semantics represent.

## Export Strategy

Create a new bulk graph export service that writes one CSV per node or relationship type into a timestamped bundle under:

- `data/archive/graph-import/<timestamp>/`

Implementation details:

- use `asyncpg.copy_from_query()` for fast CSV export direct from Postgres
- write deterministic CSV bundles with headers
- keep node IDs globally unique by prefixing them, for example:
  - `skill:publisher/repo/skill`
  - `repo:publisher/repo`
  - `registry:skills.sh`
  - `indicator:domain:example.com`
  - `asn:AS13335`

This avoids the need for multiple Neo4j ID groups.

## Import Strategy

Use a new CLI/runtime path that:

1. Exports the CSV bundle.
2. Stops `neo4j`.
3. Runs a one-shot `docker compose run --rm --no-deps neo4j ... neo4j-admin database import full`.
4. Restarts `neo4j`.
5. Verifies that the service is healthy and the graph is populated.

The import should mount the chosen bundle directory into the container at a stable path such as `/import/graph`.

## Operational Behavior

This becomes the default full graph rebuild path after major analysis waves.

The existing transactional `project-graph` command can remain for:

- very small batches
- debugging
- incremental experiments

But it should no longer be the recommended way to rebuild the full corpus.

## Error Handling

The bulk rebuild should fail fast on:

- missing export files
- Postgres export failures
- Neo4j stop/start failures
- `neo4j-admin` import errors
- post-import health-check failures

The service must not silently leave Neo4j stopped. If the import fails after the stop step, it should still attempt to bring Neo4j back up before surfacing the failure.

## Verification

The implementation should verify:

- every expected CSV file exists after export
- the import command includes all node and relationship files
- Neo4j is reachable after restart
- node count is nonzero after import

## Success Criteria

The new path is successful when:

- OpenSearch remains unchanged
- the full Neo4j rebuild no longer depends on the per-skill HTTP projector
- a full rebuild can be launched from one command
- the runtime ETA drops from the current multi-day estimate to an operationally acceptable bulk-import window
