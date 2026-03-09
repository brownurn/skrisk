# SkillsMP Live Rollout Checkpoint

Date: March 9, 2026

## Scope

This checkpoint covered:

- enabling first-class `skillsmp` ingestion in the shared SK Risk database
- validating the Scrapling-backed public-page discovery lane
- widening the authenticated SkillsMP API search lane to `100` results per page
- wiring `mewhois` and `meip` into SK Risk indicator enrichment
- repairing the production `meip` service on `162.254.118.94`
- starting the first SkillsMP-targeted scan batch against newly seeded repos

## Production Service Status

The production enrichment services were verified on the shared Melurna host:

- `mewhois` healthy at `http://10.23.94.13:8191`
- `meip` was initially down because the `postgres` container in `/opt/meip` was not running
- root cause: `meip-api` was crash-looping on `lookup postgres on 127.0.0.11:53: no such host`
- recovery action: `docker compose up -d postgres api` followed by `docker compose up -d --force-recreate api`
- post-recovery health:
  - `{"service":"meip","status":"ok","ipinfo":true,"cacheTtlDays":14}`
  - `{"service":"mewhois","status":"ok","lookup":true,"cacheTtlDays":32}`

## SkillsMP Ingestion Results

Shared database checkpoint after the first live SkillsMP pass:

- `registry_sources`: `2`
- `skills_total`: `89,916`
- `repos_total`: `12,603`
- `skillsmp_source_entries`: `3,826`
- `skillsmp_repos`: `1,307`
- `overlap_skills`: `282`

Interpretation:

- SK Risk is no longer `skills.sh`-only in live data
- `skillsmp` entries are being attached to canonical skills instead of creating duplicate scans by default
- at least `282` canonical skills are currently seen in more than one registry

## Analysis Checkpoint

Analysis state at the same checkpoint:

- `repo_snapshots`: `1,730`
- `skill_snapshots`: `9,403`
- `indicators`: `85,294`
- `skill_indicator_links`: `170,661`
- `indicator_enrichments`: `5`

Notes:

- the first live SkillsMP-targeted scan batch did start landing new snapshots
- the first infrastructure enrichment batch completed low-volume local DNS enrichment first
- WHOIS/IP enrichment is wired and reachable, but the currently scanned corpus is still dominated by documentation/common-platform domains, so enrichment prioritization remains conservative

## Operational Lessons

- the broad browser crawl is useful for validating discovery and archiving real public pages, but it is not the primary bulk-ingestion path for SkillsMP
- the authenticated API is the correct write path for incremental SkillsMP seeding because it writes page by page and does not require a full browser crawl to finish before persisting results
- SkillsMP corpus growth still needs repeated API sweeps because the API is search-based and quota-limited rather than a true bulk export
- targeted repo scans should prefer smaller due SkillsMP repos first, because a few larger repos can dominate runtime even when the registry only showed one public skill entry

## Recommended Next Runbook

1. continue paged SkillsMP API sweeps in bounded batches
2. keep SkillsMP scans targeted to smaller due repos first, then widen
3. rerun `skrisk enrich-infra` after more SkillsMP-derived snapshots land
4. reproject search/graph indexes after the next scan checkpoint
