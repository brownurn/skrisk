# SkillsMP Multi-Registry Design

**Date:** 2026-03-08

## Goal

Add `skillsmp.com` as a first-class registry beside `skills.sh`, while preserving a single canonical SK Risk scan per logical skill, exposing source provenance in the UI, combining installs across registries, and preparing the platform for required `OpenSearch` and `Neo4j` services.

## Problem

- SK Risk currently treats `skills.sh` as the only registry source.
- Registry identity and canonical scan identity are conflated today, so a second registry would overwrite provenance instead of preserving it.
- The current system cannot show that a skill was discovered in multiple registries.
- Install telemetry is single-source and cannot express per-registry totals or canonical cross-registry totals.
- `skillsmp.com` exposes a useful authenticated API, but it is search-oriented and rate-limited instead of providing a bulk export.
- Raw terminal HTTP requests to `skillsmp.com` are blocked by Cloudflare, so browser-capable discovery is required.
- Search and relationship queries are still backed only by SQLite, which is sufficient for the current corpus but not the desired multi-source analyst workflow.

## Live SkillsMP Findings

- Authenticated `skillsmp` API requests work with a bearer key against:
  - `https://skillsmp.com/api/v1/skills/search`
  - `https://skillsmp.com/api/v1/skills/ai-search`
- The `search` endpoint returns structured fields including:
  - source-native skill `id`
  - `name`
  - `author`
  - `description`
  - `githubUrl`
  - `skillUrl`
  - `stars`
  - `updatedAt`
- The `search` endpoint is rate limited to:
  - `500` requests per day
  - `30` requests per minute
- The API is search-based rather than bulk-list based:
  - `q=*` returns `400`
  - `/api/v1/skills` returns `404`
  - `/api/v1/categories` returns `404`
- Search pagination exposes `hasNext`, but `totalIsExact` is not guaranteed to be true.
- `ai-search` is useful for analyst discovery, but should not be used as the bulk crawl primitive.
- Direct non-browser requests to the HTML site are blocked by Cloudflare from this environment.

## Approved Design

### Multi-Registry Identity

- Add a first-class source model rather than treating source as incidental metadata on a crawl run.
- Keep one canonical `skill_repos` row per normalized GitHub repo.
- Keep one canonical `skills` row per logical skill.
- Add source-specific rows that represent how a skill was discovered in each registry.
- Canonical scan identity and registry discovery identity remain separate.

### Dedupe Model

- A skill discovered in both `skills.sh` and `skillsmp` should map to the same canonical SK Risk skill when:
  - the normalized GitHub repo is the same, and
  - the discovered skill folder or slug resolves to the same canonical skill in the mirrored repo
- That canonical skill is scanned once.
- All source entries remain attached for provenance, install history, and UI display.
- Registry presence must never create duplicate scan jobs or duplicate risk reports.

### Collection Strategy

- Add `skillsmp` as a first-class source adapter.
- Use a hybrid collection model for `skillsmp`:
  - `Scrapling` browser-backed discovery for category, timeline, and skill detail pages
  - authenticated `skillsmp` API lookups for structured enrichment
- Use browser discovery to expand coverage despite Cloudflare and the lack of a bulk-list endpoint.
- Use the API to fill high-quality structured fields such as source-native IDs, GitHub URLs, author, stars, and updated timestamps.
- Keep `ai-search` out of the bulk crawl path; reserve it for targeted analyst workflows later.

### Scrapling Role

- Use `D4Vinci/Scrapling` as the discovery-layer fetcher for `skillsmp`.
- Treat `Scrapling` as a complement to Playwright-style browser automation, not as a replacement for SK Risk’s analysis pipeline.
- `Scrapling` handles:
  - browser-capable fetching
  - anti-bot-aware discovery
  - persistent sessions/cookies
  - structured HTML extraction for source pages
- SK Risk still owns:
  - repo mirroring
  - canonical skill discovery inside repos
  - deep static analysis
  - IOC extraction
  - risk scoring
  - historical tracking

### Storage Model

- Add `registry_sources`:
  - one row per source such as `skills.sh` and `skillsmp`
- Add `skill_source_entries`:
  - one row per skill as seen in a specific registry
  - fields include source-native IDs, source URLs, author, stars, source installs/rank, last seen timestamps, and raw source payload
- Keep existing canonical tables:
  - `skill_repos`
  - `skills`
  - `skill_repo_snapshots`
  - `skill_snapshots`
- Extend install telemetry to support both:
  - per-registry observations
  - canonical total installs across registries

### Install Policy

- Canonical install totals shown in the main UI should be the sum of installs across registries.
- Per-registry install counts remain visible and queryable.
- Each observation must retain source attribution.
- The system should store both:
  - `current_total_installs`
  - per-source install history
- This is the right default because each registry is presumed to count installs initiated through that registry’s own flow.
- If future evidence suggests double-counting across registries, the source-attributed history will make it possible to revise the canonical policy without losing evidence.

### Frontend And API

- Keep one canonical skill row in list views.
- Add a `Registries` column/badge group to list pages and homepage summaries.
- Skill detail pages must show a `Seen In Registries` panel with:
  - registry name
  - source URL
  - source-native ID
  - per-source installs
  - per-source rank
  - first/last seen timestamps
  - source metadata such as author and stars
- Canonical list endpoints should return:
  - `sources`
  - `source_count`
  - `current_total_installs`
  - `install_breakdown`
- Canonical detail endpoints should return full source-entry provenance.

### Search And Graph Services

- `OpenSearch` is required for fast skill, repo, source, and indicator search.
- `Neo4j` is required for relationship pivots across:
  - registry source
  - source entry
  - canonical skill
  - repo
  - indicators
  - external feed observations
- `SQLite` remains the system of record in this phase.
- `OpenSearch` and `Neo4j` are projections of canonical SK Risk state, not independent sources of truth.

### Docker Runtime

- Add Docker Compose services for:
  - `opensearch`
  - `neo4j`
- Keep the SK Risk app itself running locally in this phase; Docker Compose is only for the required backing services.
- SK Risk startup should verify required service connectivity and fail fast if `OpenSearch` or `Neo4j` are configured as required but unavailable.
- Add background/projector services for:
  - search indexing
  - graph projection
  - source crawling
- `opensearch-dashboards` is deferred; the current implementation target is the runtime pair that directly improves SK Risk search and graph pivots.

### Coverage Expectations

- `skills.sh` remains fully crawlable through its current paginated API.
- `skillsmp` should be treated as a first-class registry, but its coverage must still be described honestly.
- The hybrid collector should maximize real coverage without claiming perfect completeness unless the source later provides a full enumeration surface.

## Testing Strategy

- Add collector tests for `skillsmp` API normalization and URL canonicalization.
- Add storage tests for source-aware skill provenance and cross-registry install aggregation.
- Add dedupe tests proving one canonical skill is scanned once even when multiple registries point to it.
- Add API tests for source lists, source detail payloads, and canonical total installs.
- Add frontend tests for:
  - registry badges/columns
  - per-registry install breakdowns
  - canonical combined installs
- Add integration tests for search indexing and graph projection from canonical records.

## Rollout Plan

- Introduce source-aware schema additions without resetting current canonical scan history.
- Backfill `skills.sh` into the new source-entry model.
- Add `skillsmp` discovery and enrichment.
- Extend API and Svelte UI to display source provenance and combined installs.
- Add `OpenSearch` and `Neo4j` as required Dockerized services.
- Preserve the current repo-scan pipeline so existing analysis work continues while the multi-registry layer is added.
