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

## Follow-Up Checkpoint

After the first checkpoint, a broader authenticated SkillsMP API sweep was run across `65` bounded search pages using the live query set:

- `security`
- `tools`
- `shell`
- `network`
- `browser`
- `github`
- `deploy`
- `data`
- `api`
- `auth`
- `agent`
- `coding`
- `terminal`

That sweep produced:

- `3,098` additional seeded SkillsMP page hits
- `2,357` seeded repo hits before canonical dedupe

Shared database checkpoint after the broader sweep:

- `registry_sources`: `2`
- `skills_total`: `92,526`
- `repos_total`: `13,665`
- `skillsmp_source_entries`: `7,030`
- `skillsmp_only_skills`: `6,000`
- `overlap_skills`: `667`

Interpretation:

- the live corpus now contains materially more SkillsMP coverage than the first rollout checkpoint
- overlap with `skills.sh` is increasing, which confirms the canonical source-entry dedupe model is working
- a large majority of currently seeded SkillsMP skills remain unique to SkillsMP in the live corpus

## Scan Strategy Adjustment

The first attempt to target the largest unscanned SkillsMP-only repos was intentionally stopped after `NeverSight/learn-skills.dev` started dominating the batch. Even with shallow clone flags, that repo produced an outsized clone and checkout cost relative to the rest of the queue.

Operational adjustment:

- drop giant monorepos from the front of the queue
- prioritize moderate SkillsMP-only repos first
- let those scans land more snapshots and indicators per unit time before returning to the largest repos

This was the right change. The next targeted scan batch was re-launched against moderate-size SkillsMP-only repos instead of the largest monorepo outliers.

## Live Analysis Delta

While the corrected moderate-size batch was running, the shared analysis counters had already advanced to:

- `repo_snapshots`: `1,735`
- `skill_snapshots`: `9,483`
- `indicators`: `85,333`
- `skill_indicator_links`: `170,877`
- `indicator_enrichments`: `5`

Interpretation:

- the SkillsMP rollout is now producing real additional scan artifacts, not only registry metadata
- new indicators and skill-to-indicator relationships are landing as the moderate-size batch progresses
- the next enrichment pass should be run after this batch clears, so the `mewhois` / `meip` layer works against the larger post-SkillsMP indicator set

## Scrapling Review Summary

`D4Vinci/Scrapling` remains the right browser-capable tool for the SkillsMP discovery lane, but not for the primary write path. Current recommendation:

- keep the authenticated SkillsMP API as the main incremental ingestion path
- use Scrapling as a narrower session-based discovery and archive lane
- prefer persistent session use rather than one-off fetches when Cloudflare or dynamic content requires it
- keep browser discovery targeted to specific discovery gaps, not full-corpus ingestion by default
