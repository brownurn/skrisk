# SkillsMP Enrichment Rollout Design

**Date:** 2026-03-09

## Goal

Run the first real `skillsmp` ingestion into SK Risk, wire infrastructure enrichment through the production `mewhois` and `meip` services, and preserve enough provenance to explain which domains, IPs, and registrants are tied to each skill snapshot.

## Current State

- `skills.sh` is fully represented in the live SK Risk corpus through `registry_sources` and `skill_source_entries`.
- `skillsmp` support exists in code, but the live database still contains only `skills.sh` source entries.
- `mewhois` and `meip` are documented as shared Melurna services, but they are not yet integrated into SK Risk.
- OpenSearch and Neo4j are already running locally and can project canonical SK Risk state.

## Live Production Findings

### SkillsMP

- The authenticated `skillsmp` API is available through bearer auth and remains limited to `500/day` and `30/minute`.
- The API is search-oriented, not a bulk export.
- Browser-capable discovery still matters because not every skill is reachable through a single API enumeration path.

### mewhois

- Production host: `root@162.254.118.94`
- Service endpoint on the private interface: `http://10.23.94.13:8191`
- Health probe is healthy:
  - `GET /health`
- Core API surface:
  - `GET /api/v1/whois/{domain}`
  - `POST /api/v1/whois/batch`
  - `POST /api/v1/whois/{domain}/refresh`
  - `GET /api/v1/whois/{domain}/history?limit=50`
- Live response fields include registrar, dates, nameservers, DNSSEC, privacy flags, and raw WHOIS payload.

### meip

- Production host: `root@162.254.118.94`
- Intended service endpoint on the private interface: `http://10.23.94.13:8190`
- Expected API surface:
  - `GET /api/v1/ip/{ip}`
  - `POST /api/v1/ip/batch`
  - `GET /api/v1/ip/{ip}/history?limit=50`
- Live production status is currently unhealthy.
- The `meip-api` container is crash-looping because it cannot resolve its `postgres` database host inside `/opt/meip`.
- This is an operational blocker for live IP enrichment, not a SK Risk code-path issue.

## Approved Rollout

### 1. SkillsMP Live Ingestion

- Treat `skillsmp` as a first-class live source now, not just an implemented adapter.
- Use two collection lanes:
  - authenticated API seeding for structured search results
  - Scrapling-backed discovery on category/detail pages
- Record all `skillsmp` source entries into the existing canonical source-entry model.
- Keep dedupe rules unchanged:
  - same canonical repo + same logical skill means one canonical skill
  - a skill is scanned once even if listed in both registries

### 2. Infrastructure Enrichment Model

- Resolve hostnames locally first to derive candidate IPs.
- Send domains to `mewhois`.
- Send resolved IPs to `meip` when it is available.
- Archive the raw infrastructure responses under `archive_root`.
- Normalize the most relevant fields back into SK Risk so later search, graph, and UI work can pivot on:
  - domain
  - resolved hostname
  - IP
  - registrar
  - registrant country
  - nameservers
  - ASN
  - geo
  - hosting / VPN / proxy / Tor flags

### 3. Runtime Access Pattern

- Do not hardcode direct private-network access from the local SK Risk machine.
- For local rollout, use SSH port-forwarding to the production host:
  - local `18191 -> 10.23.94.13:8191` for `mewhois`
  - local `18190 -> 10.23.94.13:8190` for `meip`
- Add SK Risk config for explicit `mewhois` and `meip` base URLs.
- Add graceful failure handling:
  - `mewhois` success should not be blocked by `meip` outage
  - `meip` failure should be recorded as provider-unavailable, not crash the enrichment job

### 4. Storage Model

- Keep the existing indicator tables as the canonical IOC layer.
- Add infrastructure-enrichment storage beside them rather than overloading raw risk reports.
- Store:
  - enrichment provider
  - lookup key
  - requested at
  - status
  - archive path
  - summarized verdict / normalized fields
- Link enrichment back to indicators and skills through the already-normalized indicator relationships.

### 5. Operational Scope

- First priority is a real `skillsmp` corpus entrypoint and live `mewhois` enrichment.
- `meip` should be wired in code now, but the live pass must tolerate the current production outage.
- The rollout is successful if SK Risk can truthfully say:
  - `skillsmp` is present in the live corpus
  - overlaps with `skills.sh` are deduped
  - domains extracted from scanned skills can be enriched with production WHOIS data
  - IP enrichment is attempted and explicitly surfaced as unavailable while `meip` remains down

## Testing Strategy

- Add config and client tests for `mewhois` / `meip` base URLs and response normalization.
- Add service tests proving:
  - hostname resolution creates domain-to-IP lookup candidates
  - enrichment archives raw payloads
  - `mewhois` success and `meip` failure can coexist in one run
- Add CLI tests for any new enrichment command.
- Add regression tests that a `skillsmp` seed plus discovery pass creates `skillsmp` source entries without duplicating canonical skills.

## Rollout Notes

- This design intentionally does not hide the live `meip` outage.
- SK Risk should degrade gracefully and preserve evidence of the outage so later runs can backfill IP context once `meip` is repaired.
