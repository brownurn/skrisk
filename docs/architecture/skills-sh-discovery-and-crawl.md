# skills.sh Discovery And Crawl Model

This document describes how SK Risk discovers the `skills.sh` corpus, what the live registry surfaces actually provide, and the operational constraints we observed while wiring the first full-corpus crawl.

## Discovery Surfaces

SK Risk now treats `skills.sh` as three different discovery surfaces:

- `GET /api/skills/all-time/<page>`
- `GET /api/skills/trending/<page>`
- `GET /api/skills/hot/<page>`
- `GET /audits`
- `GET /sitemap.xml`

The important finding is that `sitemap.xml` is not the authoritative skill directory. It only exposes a small subset of skills. The real registry inventory is served through the paginated JSON API under `/api/skills/<view>/<page>`.

## Authoritative v1 Source

For corpus tracking, SK Risk uses:

- `all-time` as the canonical directory inventory
- `audits` as partner-verdict enrichment

`trending` and `hot` remain useful secondary views, but they are not required to enumerate the full registry.

## Pagination Model

The live client bundle on `skills.sh` shows that the frontend requests more results by calling:

```text
/api/skills/<view>/<page>
```

Observed client behavior:

- page size: `200`
- first page: `0`
- response shape: `skills`, `page`, `total`, `hasMore`

SK Risk follows that exact transport instead of trying to infer the corpus from HTML or the sitemap.

## Canonical Identity

SK Risk normalizes each registry row into the coordinate:

```text
(publisher, repo, skill_slug)
```

derived from:

- `source` → `publisher/repo`
- `skillId` → `skill_slug`

The registry URL is reconstructed as:

```text
https://skills.sh/<publisher>/<repo>/<skill_slug>
```

This coordinate is the stable identity we use for dedupe, repo grouping, snapshot history, and downstream repo analysis.

## Live-Crawl Findings

Observed during a live crawl on `2026-03-07`:

- the site reported roughly `86.6k` rows in the live payload
- the deduplicated coordinate set was lower than the reported total
- the distinct repo count was roughly `11.3k`

This means the reported `totalSkills` value should be treated as a live site metric, not an immutable count of unique skill coordinates. The directory can change while we crawl it, and the API can return duplicate coordinates across pages.

Operational rule:

- store both the site-reported total and the deduplicated SK Risk total
- treat the crawl as a time-stamped observation, not a permanent ground truth

## Rate Limiting

The public paginated API rate-limits aggressive crawls with `429 Too Many Requests`.

Observed behavior on `2026-03-07`:

- the API can return `429` without a `Retry-After` header
- a cooldown of about `30` seconds was sufficient for the crawl to resume

SK Risk now retries these requests with backoff instead of failing the entire crawl. Current policy:

- retry `429`, `500`, `502`, `503`, and `504`
- honor `Retry-After` when present
- otherwise wait `30` seconds before retrying

## Sync Architecture

The registry sync now works in two stages:

1. Discover and seed all repo/skill metadata from the paginated registry API.
2. Perform deeper repo mirroring and skill snapshot analysis.

That ordering matters. It guarantees that SK Risk can track the full registry immediately, even when full repo analysis takes much longer than discovery.

Current repo-analysis rules:

- group registry rows by `(publisher, repo)`
- mirror each repo once per sync run
- discover local skill directories once per repo
- load individual skill folders from the cached checkout

This avoids the previous failure mode where the same repo was mirrored once per skill.

## Incomplete Or Failed Repo Analysis

Repo analysis can fail even after registry discovery succeeds:

- repo moved or deleted
- skill path mismatch
- malformed content
- Git/network failure

SK Risk keeps the repo and skill rows anyway. A missing snapshot means:

- the skill is tracked in the registry
- deep static analysis has not completed yet

That distinction is important for long-running crawls and resumable scanning.

## Verification Rules

Because `data/mirrors/` contains third-party repositories, pytest must not recurse into mirrored test suites. SK Risk constrains pytest to the local `tests/` tree so verification remains about SK Risk itself, not arbitrary upstream repos.

## Next Phase

The next operational improvement is a dedicated `scan-due` flow so registry discovery and repo analysis can run as separate schedules:

- registry discovery refreshes the full directory inventory
- repo analysis works through due repos incrementally
- 72-hour rescans operate on the tracked repo set rather than requiring a one-shot full crawl
