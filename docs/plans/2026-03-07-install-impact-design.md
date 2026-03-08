# Install Impact Telemetry Design

**Date:** March 7, 2026

**Goal:** Track `skills.sh` weekly install counts as a first-class impact signal, preserve their history over time, attach install footprint to scanned skill snapshots, and expose that data in the SK Risk API and Svelte frontend.

## Implementation Status

The implementation on `feat/install-impact-telemetry` now matches this design in the main repo surfaces:

- `skills` caches the latest directory-derived install metrics while `registry_sync_runs` and `skill_registry_observations` retain append-only provenance
- `directory_fetch` remains the source of truth for current install metrics and scoring inputs; `scan_attribution` preserves scan-time context in detail history without replacing the registry baseline
- `/api/skills` and `/api/skills/{publisher}/{repo}/{skill_slug}` expose installs, impact, priority, and install history
- the Svelte `/skills` route loads priority ordering by default, exposes install-bucket filtering, and keeps dedicated `Priority` and `Weekly Installs` columns
- history begins with the first install-aware sync forward; there is no retroactive backfill for older snapshots

## Problem

SK Risk currently treats the `skills.sh` directory as a discovery source and stores skill identity, ranking, and scan results, but it does not preserve the `Weekly Installs` value shown on `skills.sh`. That leaves a major gap in analyst context:

- SK Risk can tell us whether a skill looks risky.
- SK Risk cannot yet tell us how many users are likely exposed.
- SK Risk cannot show whether a risky skill is growing quickly.

The install signal should inform triage priority, but it must not contaminate the underlying malware severity judgment.

## Options Considered

### Option 1: Current value only

Add a single `current_weekly_installs` field on `skills` and overwrite it on each directory sync.

Pros:

- simple schema change
- fast list filtering and sorting

Cons:

- destroys history
- prevents trend analysis
- cannot attribute install footprint to a specific scan point

### Option 2: Historical table only

Store installs only in an append-only observation table.

Pros:

- preserves history cleanly
- supports trend analysis

Cons:

- slower for common UI queries
- every list view needs aggregation logic

### Option 3: Hybrid current plus historical

Store the latest install value on `skills` and append every observation into a separate historical table.

Pros:

- fast analyst UX
- complete historical trend data
- supports scan-time impact attribution

Cons:

- slightly more schema surface
- requires keeping current-value and historical writes consistent

**Recommendation:** Option 3.

## Architecture

The install telemetry model extends the existing registry sync and scan flows rather than creating a separate crawler.

- `seed-registry` and `sync-registry` will parse the `installs` field already present in the `skills.sh` directory payload.
- The latest observed weekly installs will be stored directly on `skills` for fast queries.
- Every registry fetch will append immutable install observations into a new history table.
- Every scan will also write a scan-attribution observation so analysts can see the known install footprint at the time a risky snapshot was analyzed.

This keeps adoption telemetry aligned with the existing snapshot model:

- registry sync captures public distribution metadata
- repo scans capture code and behavior snapshots
- scan attribution binds impact to analysis time

## Data Model

### `skills`

Add current-value fields for fast reads:

- `current_weekly_installs`
- `current_weekly_installs_observed_at`
- `current_registry_rank`
- `current_registry_sync_run_id` optional foreign key to the latest registry crawl

These fields support:

- sorting the `/skills` table by reach
- filtering high-risk skills by install volume
- rendering install counts without expensive history aggregation

### `registry_sync_runs`

Create one row per `skills.sh` directory crawl:

- `id`
- `source`
- `view`
- `fetched_at`
- `total_skills_reported`
- `pages_fetched`
- `success`
- `error_summary` optional

This gives provenance for every install observation and lets us reason about crawl completeness.

### `skill_registry_observations`

Create an immutable history table:

- `id`
- `skill_id`
- `registry_sync_run_id` nullable
- `repo_snapshot_id` nullable
- `observed_at`
- `weekly_installs`
- `registry_rank`
- `observation_kind`
- `raw_payload` optional JSON

`observation_kind` values:

- `directory_fetch`
- `scan_attribution`

Rules:

- `directory_fetch` rows are written on every directory crawl.
- `scan_attribution` rows are written when a repo/skill snapshot is analyzed.
- rows are append-only
- current-value fields on `skills` are derived from the newest `directory_fetch`

## Collection Flow

### Registry sync

When SK Risk fetches `skills.sh` directory pages:

1. parse `installs`
2. upsert the skill record
3. update `skills.current_weekly_installs`
4. append a `directory_fetch` observation row
5. record the crawl in `registry_sync_runs`

This starts the install history as soon as the next registry seed runs, without rebuilding old scan data.

### Scan flow

When `scan-due` analyzes a repo:

1. use the latest known install value already stored on `skills`
2. write a `scan_attribution` observation tied to the `repo_snapshot_id`
3. carry that install data into the skill list/detail API payloads

The scan flow should not re-fetch `skills.sh` just to get installs. That would slow scanning and blur responsibilities between registry sync and repo analysis.

## Risk, Impact, and Priority

Install volume must not be folded into malware severity.

Keep three separate concepts:

- `risk`: how suspicious or malicious the skill behavior appears
- `impact`: how many users are likely exposed
- `priority`: how urgently analysts should look at it

### Risk

Risk remains the existing SK Risk model:

- behavior score
- intel corroboration
- change amplification
- confidence

### Impact

Impact is derived from install reach and trend:

- `current reach`: latest weekly installs
- `peak reach`: highest observed weekly installs
- `growth velocity`: change versus the previous directory observation
- `scan-time reach`: known installs at the time a snapshot was analyzed

Recommended impact ladder:

- `<10 installs`: `5`
- `10-99`: `15`
- `100-999`: `30`
- `1,000-9,999`: `50`
- `10,000-49,999`: `70`
- `50,000+`: `90`

Momentum adjustment:

- falling materially: `-10`
- flat: `0`
- moderate growth: `+10`
- sharp spike: `+20`

Cap `impact_score` at `100`.

### Priority

`priority_score` should combine risk and impact without changing severity labels.

Recommended behavior:

- a severe but low-install skill stays dangerous but lower reach
- a medium-risk skill with very high installs moves up the queue
- a severe skill with high installs becomes top priority

The exact formula can evolve, but priority should be derived from:

- base risk score
- confidence multiplier
- impact multiplier

The UI should always display all three explicitly:

- `Risk`
- `Impact`
- `Priority`

## API Changes

Extend list and detail payloads with:

- `current_weekly_installs`
- `current_weekly_installs_observed_at`
- `peak_weekly_installs`
- `weekly_installs_delta`
- `impact_score`
- `priority_score`

Add install-aware filters and sorting:

- `min_weekly_installs`
- `max_weekly_installs`
- `sort=priority|risk|installs|growth`

Skill detail responses should also expose:

- recent install history
- scan-attribution rows
- install context for each scanned snapshot

## Frontend Changes

The Svelte UI should expose impact directly in triage views.

### `/skills`

Add:

- `Weekly Installs` column
- `Priority` column
- default sort by `priority_score desc`, then installs descending
- install filters by bucket:
  - `0-9`
  - `10-99`
  - `100-999`
  - `1k-9.9k`
  - `10k+`

Trend indicators should be visible inline:

- up for growth
- down for decline
- flat for unchanged

### Skill detail

Show:

- latest weekly installs
- peak observed installs
- last observed timestamp
- install history chart or table
- install count associated with scan-time observations

The install count should remain a dedicated field or column, not be merged into the severity badge.

## Migration And Backfill

This change should not reset the current crawl.

Rollout:

1. add new schema
2. start recording install observations immediately
3. populate current install fields on the next registry seed
4. write scan-attribution rows for future scans only

Backfill policy:

- do not attempt to reconstruct old install history
- do not mutate historical skill snapshots
- begin accurate history from the first install-aware registry sync forward

That is good enough for v1 and gets analyst value immediately.

## Testing

Required coverage:

- parser tests for `installs` extraction
- repository tests for current-value and append-only history writes
- registry sync tests for `directory_fetch` observation creation
- scan flow tests for `scan_attribution` observation creation
- API tests for install filters, sorting, and skill detail history
- Svelte UI tests for the new installs column and detail-page impact rendering

## Non-Goals

This phase does not include:

- full Git commit history ingestion
- retroactive install reconstruction for already-scanned snapshots
- changes to the malware severity thresholds
- vendor enrichment changes

## Decision

Proceed with the hybrid install telemetry model:

- latest value on `skills`
- append-only historical observations
- scan-time attribution during repo analysis
- impact separated from risk
- priority derived from both
