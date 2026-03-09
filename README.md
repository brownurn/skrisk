# SK Risk

SK Risk is a Melurna risk-intelligence platform for collecting, snapshotting, and analyzing AI agent skills.

## What It Does

- Collects registry intelligence from `skills.sh`
- Collects registry intelligence from `skillsmp.com` through authenticated API search plus browser-capable discovery
- Enumerates the live `skills.sh` directory through its paginated JSON API instead of relying on the partial sitemap
- Mirrors linked GitHub skill repositories into local checkouts
- Discovers skills across common agent directories and Claude plugin manifests
- Preserves multi-registry provenance so a single canonical skill can be shown as discovered in `skills.sh`, `skillsmp`, or both
- Scans a canonical skill once even when it is listed in multiple registries
- Snapshots repo and skill observations for repeated 72-hour rescans
- Tracks `skills.sh` weekly installs as hybrid current-plus-history telemetry
- Combines installs across registries into canonical `total installs` while keeping a per-registry install breakdown
- Preserves install provenance from `registry_sync_runs` and `skill_registry_observations`
- Runs static analysis for prompt injection, remote execution, exfiltration, obfuscation, and change drift
- Separates risk severity from install-derived impact and triage priority
- Archives immutable Abuse.ch feed snapshots under `archive_root`
- Falls back to the live Abuse.ch recent APIs when the full URLhaus or ThreatFox exports are malformed
- Normalizes URLs, domains, IPs, and hashes into canonical indicators with per-provider observations
- Queues selective VirusTotal enrichment for the highest-risk indicators only
- Projects canonical skill search documents into `OpenSearch`
- Projects canonical skill, repo, registry, and indicator relationships into `Neo4j`
- Exposes a FastAPI JSON API and a SvelteKit analyst frontend

## Current Commands

```bash
. .venv/bin/activate
skrisk init-db
skrisk init-dirs
skrisk seed-registry
skrisk seed-registry --source skillsmp --query security --page 1
skrisk sync-skillsmp-discovery https://skillsmp.com/categories/security
skrisk scan-due --limit-repos 100
skrisk sync-intel --provider abusech
skrisk sync-registry
skrisk sync-registry --source skillsmp --query security --page 1
skrisk enrich-vt --limit 25
skrisk check-runtime
skrisk index-search --limit 100
skrisk project-graph --limit 50
skrisk serve --host 127.0.0.1 --port 8080

docker compose up -d opensearch neo4j
docker compose ps

cd frontend
npm install
npm run build
PUBLIC_SKRISK_API_BASE_URL=http://127.0.0.1:8080 npm run dev
```

## Environment

SK Risk reads backend settings from the local shell environment or `.envrc`.

- `ABUSECH_AUTH_KEY`: used for `URLhaus` and `ThreatFox` bulk feed downloads
- `VT_APIKEY`: used for selective VirusTotal enrichment
- `SKILLSMP_API_KEY`: used for authenticated `skillsmp.com` search requests
- `SKRISK_VT_DAILY_BUDGET`: optional override for the daily VT call budget
- `SKRISK_OPENSEARCH_URL`: optional override for the OpenSearch endpoint, default `http://127.0.0.1:9200`
- `SKRISK_OPENSEARCH_INDEX_NAME`: optional override for the OpenSearch index name
- `SKRISK_REQUIRE_OPENSEARCH`: set to `1` to fail fast when OpenSearch is unavailable
- `SKRISK_NEO4J_HTTP_URL`: optional override for the Neo4j HTTP endpoint, default `http://127.0.0.1:7474`
- `SKRISK_NEO4J_DATABASE`: optional override for the Neo4j database, default `neo4j`
- `SKRISK_NEO4J_USER`: optional override for the Neo4j username
- `SKRISK_NEO4J_PASSWORD`: optional override for the Neo4j password
- `SKRISK_REQUIRE_NEO4J`: set to `1` to fail fast when Neo4j is unavailable
- `PUBLIC_SKRISK_API_BASE_URL`: frontend-only base URL for the FastAPI API

## Frontend

The analyst UI now lives in [`frontend/`](frontend) as a SvelteKit application. `skrisk serve` serves the built SPA from `frontend/build`, while `npm run dev` is available for local UI work. The current routes are:

- `/`: overview and feed activity
- `/skills`: searchable evidence queue
- `/skills/[publisher]/[repo]/[skill_slug]`: skill dossier and snapshot evidence
- `/indicators/[indicator_type]/[indicator_value]`: indicator sightings, enrichments, and linked skills
- `/queue/vt`: VT budget and queue state

Install telemetry now surfaces through both the API and the frontend:

- `/api/skills` returns `current_weekly_installs`, `current_weekly_installs_observed_at`, `peak_weekly_installs`, `weekly_installs_delta`, `impact_score`, and `priority_score`; it also accepts `min_weekly_installs`, `max_weekly_installs`, and `sort=priority|risk|installs|growth`
- `/api/skills/{publisher}/{repo}/{skill_slug}` adds append-only `install_history` rows plus source-entry provenance so analysts can compare `directory_fetch` provenance with `scan_attribution`
- `/skills` loads priority-first ordering by default, keeps `Registries` and `Total Installs` as dedicated columns, and supports local severity, install-bucket, and search filters plus priority/install sorting
- `/skills/[publisher]/[repo]/[skill_slug]` shows combined installs, per-registry install breakdown, source-entry provenance, impact, priority, and the recorded install history for that skill

Current install metrics are derived from `directory_fetch` observations. Canonical totals are the sum of the latest observed installs across registries, while detail-page history preserves both `directory_fetch` and `scan_attribution` rows so analysts can see the install footprint attached to a scanned snapshot without overwriting the registry crawl baseline.

Multi-registry provenance is now visible throughout the UI and API:

- list rows expose `sources`, `source_count`, `current_total_installs`, and per-source `install_breakdown`
- homepage critical rows show registry badges plus canonical total installs
- skill detail pages show a `Seen in registries` section with per-source URLs, native IDs, installs, ranks, and timestamps
- a skill that appears in both `skills.sh` and `skillsmp` is displayed once in canonical lists and scanned once in the backend

## SkillsMP

`skillsmp.com` is now treated as a first-class registry alongside `skills.sh`, but its coverage model is different:

- API enumeration is authenticated and search-based rather than bulk-export based
- the current API exposes bearer-authenticated `search` responses with repo URLs, authors, stars, and update timestamps
- browser-capable discovery is used to expand public coverage from category and detail pages
- SK Risk deduplicates `skills.sh` and `skillsmp` entries into one canonical skill when they resolve to the same repo and logical skill path

Use these two collection paths together:

- `skrisk seed-registry --source skillsmp --query security`
- `skrisk sync-skillsmp-discovery https://skillsmp.com/categories/security`

The first path gives structured API metadata. The second path archives HTML and widens discovery through public pages.

## Search And Graph Runtime

`OpenSearch` and `Neo4j` are now part of the local runtime and are defined in [`docker-compose.yml`](docker-compose.yml).

Start them with:

```bash
docker compose up -d opensearch neo4j
skrisk check-runtime
```

If those default ports are already occupied on your machine, override them at startup and point SK Risk at the alternate endpoints:

```bash
SKRISK_OPENSEARCH_PORT=19200 \
SKRISK_NEO4J_HTTP_PORT=17474 \
SKRISK_NEO4J_BOLT_PORT=17687 \
docker compose up -d opensearch neo4j

SKRISK_OPENSEARCH_URL=http://127.0.0.1:19200 \
SKRISK_NEO4J_HTTP_URL=http://127.0.0.1:17474 \
skrisk check-runtime
```

Then project current canonical state:

```bash
skrisk index-search --limit 100
skrisk project-graph --limit 50
```

Current defaults:

- OpenSearch: `http://127.0.0.1:9200`
- Neo4j HTTP: `http://127.0.0.1:7474`
- Neo4j credentials: `neo4j` / `skriskneo4j`

`SQLite` remains the system of record. `OpenSearch` and `Neo4j` are read-optimized projections of canonical SK Risk data.

## Project Structure

- `src/skrisk/collectors`: registry parsing, GitHub mirroring, skill discovery
- `src/skrisk/analysis`: deobfuscation and heuristic risk analysis
- `src/skrisk/storage`: async SQLAlchemy models and repository helpers
- `src/skrisk/services`: registry sync, intelligence sync, VT triage, and local checkout ingestion
- `src/skrisk/api`: JSON API and backend application surface
- `frontend`: SvelteKit analyst console
- `tests`: regression coverage for collectors, rescans, sync, API, VT, scoring, and CLI

## Documentation

- [Implementation plan](docs/plans/2026-03-06-skrisk-v1.md)
- [Kickoff notes and discussion decisions](docs/discussions/2026-03-06-kickoff.md)
- [skills.sh crawl findings](docs/discussions/2026-03-07-skills-sh-crawl-findings.md)
- [Threat intel and frontend design](docs/plans/2026-03-06-intel-enrichment-design.md)
- [Threat intel implementation plan](docs/plans/2026-03-06-intel-enrichment-implementation.md)
- [Install impact telemetry design](docs/plans/2026-03-07-install-impact-design.md)
- [Risk and intelligence model](docs/architecture/risk-and-intel-model.md)
- [skills.sh discovery and crawl model](docs/architecture/skills-sh-discovery-and-crawl.md)
- [Vendor and enrichment decisions](docs/discussions/2026-03-06-threat-intel-vendors.md)
- [SkillsMP integration notes](docs/discussions/2026-03-08-skillsmp-integration.md)
- [SkillsMP multi-registry design](docs/plans/2026-03-08-skillsmp-multiregistry-design.md)
- [SkillsMP multi-registry implementation plan](docs/plans/2026-03-08-skillsmp-multiregistry-implementation.md)

## Current Gaps

- Real source-repo URL resolution still assumes `https://github.com/{publisher}/{repo}` where registry metadata is missing
- `mewhois`, `meip`, and later enrichment layers such as Merklemap are not wired yet
- The current storage path is optimized for local bootstrap; the production Postgres/Timescale rollout is documented but not implemented

## Maintainer

- Sam Jadali `<sam@melurna.com>`
