# SkillsMP Integration Notes

**Date:** 2026-03-08

## Decisions

- `skillsmp.com` is treated as a first-class SK Risk registry beside `skills.sh`.
- Registry discovery identity is separate from canonical scan identity.
- A canonical skill is scanned once even when it appears in multiple registries.
- Canonical install totals are the sum of the latest installs observed across registries.
- Per-registry install counts, URLs, native IDs, ranks, and timestamps remain visible in the API and frontend.
- `skillsmp` collection uses two lanes:
  - authenticated API search for structured metadata
  - browser-capable HTML discovery for public category and detail pages
- `OpenSearch` and `Neo4j` are required local runtime services, but they remain projections of the canonical SQLite state.

## Why This Shape

- `skillsmp` does not expose a clean bulk export. Its authenticated API is search-based, rate-limited, and does not support wildcard enumeration.
- Browser-capable discovery is required because raw terminal HTTP requests encounter Cloudflare.
- The platform needs provenance without double-scanning. Source rows solve that cleanly while preserving one canonical repo/skill/snapshot model.
- Combined installs answer the impact question better than a single-source metric, while source-attributed history preserves reversibility if registry overlap assumptions change later.

## Implemented Runtime

- `skillsmp` API support through `SKILLSMP_API_KEY`
- `sync-registry --source skillsmp --query ...`
- `seed-registry --source skillsmp --query ...`
- `sync-skillsmp-discovery <url...>`
- source-aware schema with `registry_sources` and `skill_source_entries`
- canonical total installs and per-source install breakdowns in API responses
- Svelte UI registry badges, combined install counts, and source provenance panels
- Dockerized `OpenSearch` and `Neo4j`
- CLI runtime helpers:
  - `skrisk check-runtime`
  - `skrisk index-search`
  - `skrisk project-graph`

## Coverage Notes

- `skills.sh` remains the most complete source because its paginated API can be enumerated directly.
- `skillsmp` is first-class, but its coverage should still be described honestly as hybrid API plus browser discovery, not guaranteed full corpus enumeration.
- Canonical dedupe currently relies on normalized repo identity plus discovered logical skill identity inside the mirrored repo.

## Next Follow-Ups

- Expand `skillsmp` search-term seeding to increase coverage over time.
- Add additional registries using the same source-entry model.
- Layer `OpenSearch` search UI and Neo4j graph pivots more deeply into the analyst workflow.
- Revisit Merklemap later as a domain and certificate enrichment layer.
