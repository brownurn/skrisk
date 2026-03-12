# SK Risk Implementation Status

Date: 2026-03-11

## Summary

SK Risk has moved from a bootstrap scanner into a working multi-registry analysis platform with a Postgres system of record, OpenSearch projection, Neo4j relationship graph, local mirror corpus, and evidence-first skill detail pages.

The most recent work tightened outbound-evidence explanations and country-risk classification so the UI can explain *why* a skill is concerning, not just that it received a high score.

## Major Steps Completed

### Corpus Collection

- enumerated the live `skills.sh` directory through its paginated JSON API
- added first-class `skillsmp.com` support through authenticated API search plus browser-backed discovery
- deduplicated multi-registry skills into one canonical skill record
- mirrored the tracked GitHub repo corpus locally under `data/mirrors`

### Persistence And Scale

- bootstrapped with SQLite
- migrated the system of record to Postgres
- added a spooled repo-analysis runtime so producers and ingesters could run safely in parallel
- rebuilt the graph via offline Neo4j bulk import instead of slow per-skill transactional projection

### Analysis

- moved to repo-first analysis so a repo is downloaded once and every discovered skill in that checkout is analyzed
- expanded static extraction beyond simple URL regexes with AST and language-aware passes
- hardened indicator extraction against:
  - overlong badge URLs
  - malformed Unicode
  - NUL/control-byte URL tricks
  - code/member-access tokens being mistaken for domains

### Intel And Infrastructure

- wired Abuse.ch `URLhaus` and `ThreatFox`
- wired `mewhois` and `meip` through the production microservices
- added local DNS enrichment so domains can be resolved into IP profiles and geography
- preserved all feed and enrichment artifacts under `archive_root`

### Search And Graph

- projected canonical skill summaries into OpenSearch
- bulk rebuilt the Neo4j graph for skill, repo, registry, and indicator relationships

### Frontend

- shipped the Svelte analyst UI
- added install telemetry, registry provenance, repo drilldowns, and skill dossier pages
- added explicit `Outbound evidence` rendering on the skill detail page

## Current Corpus Snapshot

Current live counts on this machine:

- tracked repos: `13,665`
- canonical skills: `224,385`
- repo snapshots: `50,196`
- skill snapshots: `693,067`
- indicators: `1,961,567`
- skill-indicator links: `33,118,678`
- registry sources: `2`
- `skillsmp` source entries: `7,030`

Current projections:

- OpenSearch indexed skills: `224,385`
- Neo4j nodes: `1,510,238`
- Neo4j relationships: `3,090,083`
- Neo4j `Skill` nodes: `224,385`

## Current Local Runtime

- UI/API: `http://127.0.0.1:8080`
- LAN UI/API: `http://192.168.94.13:8080`
- Postgres: `127.0.0.1:15432`
- OpenSearch: `127.0.0.1:19200`
- Neo4j HTTP: `127.0.0.1:17474`
- Neo4j Bolt: `127.0.0.1:17687`

## Evidence Model Update

The current UI/API now distinguishes three different situations:

- `reference_example`
  - documentation or example snippets only
- `credential_transmission`
  - operational code sending a token/API credential to a remote service
- `data_exfiltration`
  - operational code sending a concrete sensitive source to a remote sink

The skill detail page now exposes:

- source kind and source values
- sink URL/host
- transport detail
- resolved IP destinations
- country and ASN
- whether a destination falls into the `primary cyber concern` set

## Example Review

### False Positive Cleanup

`ccheney/robust-skills/clean-ddd-hexagonal`

- current severity: `none`
- current score: `0`
- outbound evidence: none

This was the wrong template for exfiltration. The earlier finding came from reference docs and sample code, not a real sensitive-source-to-remote-sink path.

### Better Template

`176336109/.openclaw/bocha-web-search`

- current severity: `medium`
- current score: `18`
- finding category: `credential_transmission`
- observed source: `BOCHA_API_KEY`
- sink: `https://api.bocha.cn/v1/web-search`
- resolved IPs:
  - `123.57.128.210`
  - `8.147.108.53`
- resolved country: `China`
- ASN: `Hangzhou Alibaba Advertising Co.,Ltd.`
- primary cyber concern: `true`

Important nuance: this is a good example of outbound credential transmission to a high-risk-country service, but it is not automatically the same as local secret theft/exfiltration.

## Current Gaps

- `skillsmp.com` still needs additional live ingestion work to approach full public coverage because its authenticated API is search-based rather than bulk-export based
- not every skill has had its infrastructure fully enriched yet
- country risk is now surfaced, but severity escalation rules for foreign/high-risk destinations can still be tightened further
- the next deeper phase is improving exact sensitive-source tracking so exfiltration findings can say not just that a secret-like value moved, but exactly which local source was read
