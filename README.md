# SK Risk

SK Risk is a Melurna risk-intelligence platform for collecting, snapshotting, and analyzing AI agent skills.

## What It Does

- Collects registry intelligence from `skills.sh`
- Mirrors linked GitHub skill repositories into local checkouts
- Discovers skills across common agent directories and Claude plugin manifests
- Snapshots repo and skill observations for repeated 72-hour rescans
- Tracks `skills.sh` weekly installs as hybrid current-plus-history telemetry
- Preserves install provenance from `registry_sync_runs` and `skill_registry_observations`
- Runs static analysis for prompt injection, remote execution, exfiltration, obfuscation, and change drift
- Separates risk severity from install-derived impact and triage priority
- Archives immutable Abuse.ch feed snapshots under `archive_root`
- Normalizes URLs, domains, IPs, and hashes into canonical indicators with per-provider observations
- Queues selective VirusTotal enrichment for the highest-risk indicators only
- Exposes a FastAPI JSON API and a SvelteKit analyst frontend

## Current Commands

```bash
. .venv/bin/activate
skrisk init-db
skrisk init-dirs
skrisk sync-intel --provider abusech
skrisk sync-registry
skrisk enrich-vt --limit 25
skrisk serve --host 127.0.0.1 --port 8080

cd frontend
npm install
npm run build
PUBLIC_SKRISK_API_BASE_URL=http://127.0.0.1:8080 npm run dev
```

## Environment

SK Risk reads backend settings from the local shell environment or `.envrc`.

- `ABUSECH_AUTH_KEY`: used for `URLhaus` and `ThreatFox` bulk feed downloads
- `VT_APIKEY`: used for selective VirusTotal enrichment
- `SKRISK_VT_DAILY_BUDGET`: optional override for the daily VT call budget
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
- `/api/skills/{publisher}/{repo}/{skill_slug}` adds append-only `install_history` rows so analysts can compare `directory_fetch` provenance with `scan_attribution`
- `/skills` loads priority-first ordering by default, keeps `Priority` and `Weekly Installs` as dedicated columns, and supports local severity, install-bucket, and search filters plus priority/install sorting
- `/skills/[publisher]/[repo]/[skill_slug]` shows latest installs, peak installs, install delta, impact, priority, and the recorded install history for that skill

Current install metrics are derived from `directory_fetch` observations. Detail-page history preserves both `directory_fetch` and `scan_attribution` rows so analysts can see the install footprint attached to a scanned snapshot without overwriting the registry crawl baseline.

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
- [Threat intel and frontend design](docs/plans/2026-03-06-intel-enrichment-design.md)
- [Threat intel implementation plan](docs/plans/2026-03-06-intel-enrichment-implementation.md)
- [Install impact telemetry design](docs/plans/2026-03-07-install-impact-design.md)
- [Risk and intelligence model](docs/architecture/risk-and-intel-model.md)
- [Vendor and enrichment decisions](docs/discussions/2026-03-06-threat-intel-vendors.md)

## Current Gaps

- Real source-repo URL resolution still assumes `https://github.com/{publisher}/{repo}` where registry metadata is missing
- `mewhois`, `meip`, and later enrichment layers such as Merklemap are not wired yet
- The current storage path is optimized for local bootstrap; the production Postgres/Timescale rollout is documented but not implemented

## Maintainer

- Sam Jadali `<sam@melurna.com>`
