# Dashboard Performance And Accuracy

## Date
- March 10, 2026

## Problem
- The homepage overview and `/skills` page were slow against the live Postgres corpus.
- The right-side `Flagged Repos` table was not clickable.
- `Top Domain` was surfacing placeholders and code-like tokens such as `0.0.0.0`, `${okta_domain}`, and `--collector.filesystem`.
- The critical list still contained likely false positives, especially for broad guide or catalog skills.

## Root Cause
- Summary endpoints were recomputing the latest snapshot per skill on every request from `skill_snapshots`, then grouping and sorting across the full snapshot table.
- Summary payloads were also serializing full `risk_report` structures, including heavy `indicator_matches` arrays, even though list views only need summary fields.
- Domain display was using the first extracted token without filtering placeholders, loopback values, or code tokens.

## Decision
- Do not add a Postgres materialized view for the current hot path.
- Persist latest-snapshot summary fields directly on `skills`:
  - `latest_snapshot_id`
  - `latest_severity`
  - `latest_risk_score`
  - `latest_confidence`
  - `latest_indicator_match_count`
- Keep full evidence only on skill detail pages.
- Add a repo drill-down page and API endpoint instead of leaving homepage repo rows as dead text.

## Implementation
- Added additive schema migrations and a guarded backfill for latest-summary fields.
- Updated ingest paths so new snapshots keep the latest-summary fields in sync.
- Rewrote summary queries to use `skills` latest-summary fields instead of recomputing latest snapshot IDs from `skill_snapshots`.
- Added `/api/repos/{publisher}/{repo}` and `/repos/[publisher]/[repo]`.
- Made `Flagged Repos` rows on the homepage clickable.
- Tightened bare-domain extraction and added frontend representative-domain filtering.
- Trimmed summary payloads so overview and paged skill lists no longer ship full `indicator_matches` and `findings`.

## Live Results
- Postgres flagged-repo aggregate query dropped to about `146 ms`.
- Top-100 skills ordering query dropped to about `34 ms`.
- Cold `/api/overview` after restart dropped from about `18 s` to about `0.52 s`.
- Warm `/api/overview` is about `0.36 s`.
- Warm `/api/repos/ypyt1/all-skills` is about `0.01 s`.

## Verifier Review
- Likely overstated:
  - `github/awesome-copilot/create-web-form`
  - `mcp-use/mcp-use/mcp-apps-builder`
  - `resend/resend-skills/resend` looks inflated, though not as clearly wrong
- Partly credible but probably still overstated at `critical`:
  - `github/awesome-copilot/aspire`
- Credible high-risk infrastructure skills:
  - `cloudflare/skills/cloudflare`
  - `jeffallan/claude-skills/kubernetes-specialist`

## Follow-Up
- The next scoring pass should distinguish:
  - navigation/catalog skills
  - product reference skills
  - direct admin or infrastructure-operation skills
- That is a scoring-accuracy task, not a dashboard-query task.
