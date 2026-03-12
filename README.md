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

## Current Status

Current local corpus snapshot on `2026-03-11`:

- `13,665` tracked repos
- `224,385` canonical skills
- `50,196` repo snapshots
- `693,067` skill snapshots
- `1,961,567` indicators
- `33,118,678` skill-indicator links
- `2` registry sources (`skills.sh`, `skillsmp`)
- `7,030` `skillsmp` source entries

Current projection/runtime snapshot:

- OpenSearch documents: `224,385`
- Neo4j nodes: `1,510,238`
- Neo4j relationships: `3,090,083`
- Neo4j `Skill` nodes: `224,385`

Current local access points:

- analyst UI: `http://127.0.0.1:8080`
- analyst UI on LAN: `http://192.168.94.13:8080`
- Postgres: `127.0.0.1:15432`
- OpenSearch: `127.0.0.1:19200`
- Neo4j HTTP: `127.0.0.1:17474`
- Neo4j Bolt: `127.0.0.1:17687`
- `mewhois`: `127.0.0.1:18191` via SSH tunnel
- `meip`: `127.0.0.1:18190` via SSH tunnel

## Evidence Model

SK Risk now distinguishes between reference content, operational outbound behavior, and true exfiltration.

- `credential_transmission`
  - observed token or API credential sent to a remote service as part of operational code
  - example: `Authorization: Bearer $BOCHA_API_KEY`
- `data_exfiltration`
  - requires a concrete sensitive source plus an operational remote sink
  - examples include local secret files, env secrets, or explicit secret variables sent out
- `reference_example`
  - documentation or examples are retained as lower-confidence context and should not drive the same severity as operational code

Skill detail pages now include an `Outbound evidence` section that shows:

- what data/token/path was observed
- how it was transmitted
- the sink URL/host
- resolved destination IPs
- country and ASN context
- whether any destination is in the `primary cyber concern` set

Current primary-cyber-concern set includes:

- Afghanistan
- Algeria
- Belarus
- China
- Congo (both Republic of the Congo and Democratic Republic of the Congo)
- Cuba
- Haiti
- Iran
- Kenya
- Laos
- Lebanon
- Monaco
- Myanmar
- Namibia
- Nigeria
- North Korea
- Romania
- Russia
- South Sudan
- Syria
- Tanzania
- Ukraine
- Venezuela
- Vietnam
- Yemen

## Current Commands

```bash
. .venv/bin/activate
skrisk init-db
skrisk init-dirs
skrisk migrate-sqlite-to-postgres --source-sqlite-path ./skrisk.db --reset-target
skrisk seed-registry
skrisk seed-registry --source skillsmp --query security --page 1
skrisk sync-skillsmp-discovery https://skillsmp.com/categories/security
skrisk scan-due --limit-repos 100
skrisk sync-intel --provider abusech
skrisk sync-registry
skrisk sync-registry --source skillsmp --query security --page 1
skrisk enrich-infra --limit 100
skrisk enrich-vt --limit 25
skrisk check-runtime
skrisk index-search --limit 100
skrisk project-graph --limit 50
skrisk serve --host 127.0.0.1 --port 8080

docker compose up -d postgres opensearch neo4j
docker compose ps

cd frontend
npm install
npm run build
PUBLIC_SKRISK_API_BASE_URL=http://127.0.0.1:8080 npm run dev

# needed for browser-backed SkillsMP discovery
pip install -e .
scrapling install
```

## Environment

SK Risk reads backend settings from the local shell environment or `.envrc`.

- `ABUSECH_AUTH_KEY`: used for `URLhaus` and `ThreatFox` bulk feed downloads
- `VT_APIKEY`: used for selective VirusTotal enrichment
- `SKILLSMP_API_KEY`: used for authenticated `skillsmp.com` search requests
- `SKRISK_VT_DAILY_BUDGET`: optional override for the daily VT call budget
- `SKRISK_DATABASE_URL`: optional override for the system-of-record database. By default SK Risk uses the local Docker Postgres service at `postgresql://skrisk:skrisk@127.0.0.1:15432/skrisk`
- `SKRISK_POSTGRES_PORT`: optional Docker Compose host port override for the bundled Postgres service, default `15432`
- `SKRISK_MEWHOIS_URL`: optional override for the `mewhois` base URL
- `SKRISK_MEWHOIS_PORT`: optional tunnel/default port for `mewhois` when `SKRISK_MEWHOIS_URL` is not set
- `SKRISK_MEIP_URL`: optional override for the `meip` base URL
- `SKRISK_MEIP_PORT`: optional tunnel/default port for `meip` when `SKRISK_MEIP_URL` is not set
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

Browser-backed discovery uses Scrapling's fetcher runtime. Install project dependencies and run `scrapling install` before using `sync-skillsmp-discovery`.

## Infrastructure Enrichment

SK Risk can enrich extracted domains and IPs through `mewhois`, `meip`, and local DNS resolution:

- `skrisk enrich-infra --limit 100`
- domains get cached WHOIS context from `mewhois`
- domains also get local DNS resolution snapshots with resolved IPs
- resolved and directly extracted IPs get cached IP intelligence from `meip`
- indicator detail responses and Neo4j projections include those enrichments so skills can be pivoted into registrars, nameservers, resolved IPs, and ASNs

For production Melurna infrastructure, point SK Risk at the shared microservices:

```bash
SKRISK_MEWHOIS_URL=http://10.23.94.13:8191
SKRISK_MEIP_URL=http://10.23.94.13:8190
```

In the current local setup, SK Risk does not run `mewhois` or `meip` natively on this machine. It talks to local loopback ports that are SSH-forwarded to the production microservices through the shared jump host:

```bash
ssh -L 18191:10.23.94.13:8191 -L 18190:10.23.94.13:8190 root@162.254.118.94
```

That means:

- `http://127.0.0.1:18191` is the local tunnel endpoint for `mewhois`
- `http://127.0.0.1:18190` is the local tunnel endpoint for `meip`
- the backing services are hosted behind `162.254.118.94`, not on the SK Risk server itself

## Search And Graph Runtime

`Postgres`, `OpenSearch`, and `Neo4j` are now part of the local runtime and are defined in [`docker-compose.yml`](docker-compose.yml).

Start them with:

```bash
docker compose up -d postgres opensearch neo4j
SKRISK_DATABASE_URL=postgresql://skrisk:skrisk@127.0.0.1:15432/skrisk skrisk init-db
skrisk check-runtime
```

If those default ports are already occupied on your machine, override them at startup and point SK Risk at the alternate endpoints:

```bash
SKRISK_OPENSEARCH_PORT=19200 \
SKRISK_NEO4J_HTTP_PORT=17474 \
SKRISK_NEO4J_BOLT_PORT=17687 \
SKRISK_POSTGRES_PORT=15433 \
docker compose up -d postgres opensearch neo4j

SKRISK_DATABASE_URL=postgresql://skrisk:skrisk@127.0.0.1:15433/skrisk \
SKRISK_OPENSEARCH_URL=http://127.0.0.1:19200 \
SKRISK_NEO4J_HTTP_URL=http://127.0.0.1:17474 \
skrisk check-runtime
```

Then project current canonical state:

```bash
skrisk index-search --limit 100
skrisk project-graph --limit 50
```

For a full graph rebuild after a large analysis wave, use the offline bulk path instead of the transactional projector:

```bash
SKRISK_NEO4J_HTTP_PORT=17474 \
SKRISK_NEO4J_BOLT_PORT=17687 \
PYTHONPATH=src .venv/bin/skrisk rebuild-graph-bulk --threads 25 --max-off-heap-memory 70%
```

`project-graph` is still useful for small batches and debugging. `rebuild-graph-bulk` is the intended full-corpus rebuild path.

Current defaults:

- OpenSearch: `http://127.0.0.1:9200`
- Neo4j HTTP: `http://127.0.0.1:7474`
- Neo4j credentials: `neo4j` / `skriskneo4j`

`Postgres` is the system of record. `OpenSearch` and `Neo4j` are read-optimized projections of canonical SK Risk data.

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
- [SkillsMP live rollout checkpoint](docs/discussions/2026-03-09-skillsmp-live-rollout.md)
- [SkillsMP multi-registry design](docs/plans/2026-03-08-skillsmp-multiregistry-design.md)
- [SkillsMP multi-registry implementation plan](docs/plans/2026-03-08-skillsmp-multiregistry-implementation.md)
- [AST analysis design](docs/plans/2026-03-09-ast-analysis-design.md)
- [Postgres runtime scaling](docs/plans/2026-03-09-postgres-runtime-scaling-design.md)
- [Neo4j bulk import design](docs/plans/2026-03-11-neo4j-bulk-import-design.md)
- [Exfiltration and country-risk design](docs/plans/2026-03-11-exfil-evidence-country-risk-design.md)
- [Exfiltration example review](docs/discussions/2026-03-11-exfil-evidence-example-review.md)
- [Implementation status update](docs/discussions/2026-03-11-implementation-status.md)

## Current Gaps

- SkillsMP still needs ongoing live ingestion work to approach full public coverage because its authenticated API is search-based rather than a bulk export
- Real source-repo URL resolution still assumes `https://github.com/{publisher}/{repo}` where registry metadata is missing
- Multiple `ingest-analysis-spool` processes are safe on Postgres because pending artifacts are now claimed atomically through the file spool before they are persisted

## Maintainer

- Sam Jadali `<sam@melurna.com>`
