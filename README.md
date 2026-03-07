# SK Risk

SK Risk is a Melurna risk-intelligence platform for collecting, snapshotting, and analyzing AI agent skills.

## What It Does

- Collects registry intelligence from `skills.sh`
- Mirrors linked GitHub skill repositories into local checkouts
- Discovers skills across common agent directories and Claude plugin manifests
- Snapshots repo and skill observations for repeated 72-hour rescans
- Runs a first-pass static analyzer for prompt injection, remote execution, exfiltration, and obfuscation
- Exposes a FastAPI JSON API and an HTML dashboard

## Current Commands

```bash
. .venv/bin/activate
skrisk init-db
skrisk init-dirs
skrisk sync-registry
skrisk serve --host 127.0.0.1 --port 8080
```

## Project Structure

- `src/skrisk/collectors`: registry parsing, GitHub mirroring, skill discovery
- `src/skrisk/analysis`: deobfuscation and heuristic risk analysis
- `src/skrisk/storage`: async SQLAlchemy models and repository helpers
- `src/skrisk/services`: registry sync and local checkout ingestion
- `src/skrisk/api`: JSON API, HTML dashboard, and templates
- `tests`: regression coverage for collectors, rescans, sync, API, dashboard, and CLI

## Documentation

- [Implementation plan](docs/plans/2026-03-06-skrisk-v1.md)
- [Kickoff notes and discussion decisions](docs/discussions/2026-03-06-kickoff.md)

## Current Gaps

- Real source-repo URL resolution still assumes `https://github.com/{publisher}/{repo}` where registry metadata is missing
- `mewhois`, `meip`, and third-party threat-intel adapters are not wired yet
- The current storage path is optimized for local bootstrap; the production Postgres/Timescale rollout is documented but not implemented

## Maintainer

- Sam Jadali `<sam@melurna.com>`
