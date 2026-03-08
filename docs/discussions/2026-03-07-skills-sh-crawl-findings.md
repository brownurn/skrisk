# skills.sh Crawl Findings

Date: `2026-03-07`

## What Changed

We moved SK Risk off the `skills.sh` sitemap as the primary registry source.

Reason:

- the sitemap only exposed a small subset of the public ecosystem
- the live client bundle showed the real directory is paginated through `/api/skills/<view>/<page>`
- a full live crawl exposed an order-of-magnitude larger corpus than the sitemap-backed collector was seeing

## Decisions

- use `/api/skills/all-time/<page>` as the canonical v1 discovery source
- keep `/audits` as partner-verdict enrichment
- dedupe skills by `(publisher, repo, skill_slug)`
- treat site-reported totals as live metrics, not authoritative unique counts
- retry `429` responses with backoff because the public API rate-limits bulk enumeration
- seed repo and skill metadata before deep repo analysis so the system tracks the full directory immediately
- mirror each repo once per scan run and reuse the checkout across all skills in that repo

## Live Observations

During the live crawl on `2026-03-07`:

- the site was advertising roughly `86.6k` rows
- the deduplicated SK Risk coordinate count was lower than the site-reported total
- the distinct repo count was roughly `11.3k`
- the crawl hit public rate limiting and required cooldown/retry handling

## Implications

- full discovery and full deep analysis are separate operational concerns
- registry tracking can complete much earlier than repo mirroring and static analysis
- a resumable repo-scan queue is the right long-term execution model

## Follow-Up

- keep `sync-registry` seeding the full directory
- add a dedicated `scan-due` path so 72-hour rescans can progress incrementally across the repo set
