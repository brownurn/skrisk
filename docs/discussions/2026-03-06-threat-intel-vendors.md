# Threat Intel Vendor Decisions

Date: 2026-03-06

## Decisions Captured

- V1 stores immutable raw provider artifacts on local disk under `archive_root`.
- `data/` remains gitignored and is treated as runtime evidence, not source.
- Abuse.ch `URLhaus` and `ThreatFox` are the first bulk intelligence providers.
- `ABUSECH_AUTH_KEY` in `.envrc` is the shared auth token for both feeds.
- `VT_APIKEY` is available in `.envrc`, but VT is used selectively because the key is capped at `490` lookups per day.
- Merklemap is explicitly deferred to phase 2 for DNS and certificate pivots.

## Why Abuse.ch First

`URLhaus` and `ThreatFox` are a strong first fit for SK Risk because they directly help with:

- suspicious download URLs
- malicious domains and IPs
- malware-family context
- IOC corroboration for skills that appear to download payloads or exfiltrate data

The feeds are also available as full exports, which fits the SK Risk archive-and-normalize model better than lookup-only APIs.

## VirusTotal Policy

VT is valuable, but the quota is limited enough that it must be treated as a triage layer, not a background bulk feed.

Use VT for:

- indicators extracted from `critical` skills
- downloader, exfiltration, or binary-delivery infrastructure
- newly introduced URLs, domains, or hashes with strong local evidence

Do not use VT for:

- full backfills of the registry
- repeated fresh lookups when a cached result exists
- low-signal documentation or benign infrastructure

## Merklemap Position

Merklemap is a good future provider for:

- certificate-transparency pivots
- sibling domain discovery
- DNS history and certificate reuse analysis
- infrastructure clustering around suspicious endpoints

It is not the right v1 replacement for the current IOC stack. SK Risk first needs:

- canonical indicators
- feed provenance
- historical skill diffs
- selective enrichment

Once those are stable, Merklemap becomes much more valuable as a phase-2 pivot layer.
