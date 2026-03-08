# Risk And Intelligence Model

This document describes the SK Risk v1 data model, install telemetry model, risk system, and how external intelligence is folded into skill-level findings.

## Core Principle

SK Risk owns the risk decision. Third-party feeds and enrichment providers increase confidence and context, but they do not replace local evidence from the skill snapshot itself. Install telemetry affects impact and triage priority, but it does not change the underlying severity label by itself.

## Data Model

The risk system is built from three layers:

- skill state: repos, skill snapshots, extracted artifacts, and risk reports
- install telemetry state: latest registry-derived installs plus append-only install observations
- intelligence state: canonical indicators, provider observations, enrichment cache, and VT triage

### Skill-State Tables

- `skill_repos`: tracked source repositories
- `skill_repo_snapshots`: repo-level points in time
- `skills`: canonical skill identities plus current install telemetry fields used for fast list/detail reads
- `skill_snapshots`: versioned skill content, extracted domains, and serialized risk report
- `external_verdicts`: partner verdicts kept separate from SK Risk’s own scoring

### Install-Telemetry Tables

SK Risk uses a hybrid current-plus-history install model:

- `skills` caches the latest registry-derived telemetry on
  `current_weekly_installs`,
  `current_weekly_installs_observed_at`,
  `current_registry_rank`, and
  `current_registry_sync_run_id`
- `registry_sync_runs`: one row per `skills.sh` directory crawl, including `source`, `view`, `total_skills_reported`, `pages_fetched`, `success`, and `error_summary`
- `skill_registry_observations`: append-only install rows with `skill_id`, `registry_sync_run_id`, optional `repo_snapshot_id`, `observed_at`, `weekly_installs`, `registry_rank`, `observation_kind`, and optional `raw_payload`

### Intelligence-State Tables

- `intel_feed_runs`: one row per feed download/parse attempt
- `intel_feed_artifacts`: immutable raw archive and manifest files tied to a feed run
- `indicators`: canonical IOC identities keyed by `(indicator_type, normalized_value)`
- `indicator_observations`: provider claims about one indicator over time
- `skill_indicator_links`: evidence showing where an indicator was extracted from a skill
- `indicator_enrichments`: cached secondary lookups such as VirusTotal
- `vt_lookup_queue`: selective queue for high-priority enrichment candidates

## Archive Strategy

Raw provider artifacts are stored immutably under `archive_root`, currently on local disk for v1.

Directory pattern:

```text
data/archive/intel/<provider>/<feed>/<YYYY>/<MM>/<DD>/<HHMMSSZ>/
```

Each run stores:

- the original archive body
- a `manifest.json` with provider, feed, fetch time, source URL, auth mode, SHA256, size, parser version, and row count

This keeps provenance and allows parser upgrades or replay without re-downloading external evidence.

## Install Telemetry Provenance

`skills.sh` directory payloads already include `installs`, so SK Risk records install telemetry as part of the registry sync instead of creating a separate crawler.

- every install-aware registry crawl creates a `registry_sync_runs` row
- every fetched skill row appends a `skill_registry_observations` row with `observation_kind = directory_fetch`
- only `directory_fetch` rows update the cached `skills.current_*` fields, so the current install metrics always come from registry data rather than from a later scan
- repo analysis appends a second observation with `observation_kind = scan_attribution` and a `repo_snapshot_id`, preserving the install footprint attached to the analyzed snapshot
- scan attribution reuses the freshest known `observed_at`, `registry_rank`, and `registry_sync_run_id` when that context is available, rather than re-fetching the registry

Current install metrics, impact scoring, and priority ordering are derived from `directory_fetch` history when it exists. The detail API keeps both `directory_fetch` and `scan_attribution` rows in `install_history` so analysts can inspect provenance instead of seeing a flattened trend line.

Install history is only accurate from the first install-aware registry sync forward. SK Risk does not reconstruct old installs or mutate historical snapshots retroactively.

## Risk Scoring

Risk scoring remains separate from install telemetry. SK Risk uses four risk dimensions:

- `behavior_score`
- `intel_score`
- `change_score`
- `confidence`

The first three sum into a numeric severity score. Confidence is a separate label so novel malicious behavior can be high severity even before third-party confirmation exists.

### Severity Thresholds

- `0-9`: `none`
- `10-24`: `low`
- `25-44`: `medium`
- `45-69`: `high`
- `70+`: `critical`

### Behavior Score

Behavior is weighted most heavily because it reflects what the skill appears to do.

High-signal behavior examples:

- reads local credential or secret files: `+18`
- posts local content to a remote endpoint: `+22`
- targets browser data, SSH keys, cloud credentials, wallets, or shell history: `+25`
- `curl|sh` or `wget|sh` style download-and-execute flow: `+22`
- binary download followed by execute: `+24`
- Base64 or multi-layer decoding that resolves to execution or egress: `+14` to `+18`
- hard-coded suspicious domains, direct IPs, or dynamically assembled endpoints: `+6` to `+12`

Behavior dampeners reduce false positives but do not exonerate a skill:

- common package registries or cloud APIs in otherwise normal behavior: `-4`
- clearly local shell execution with no download or upload: `-4`
- URLs present only in docs/examples with no execution path: `-3`

### Intel Score

Intel score represents corroboration from external sources.

- direct `URLhaus` URL match: `+22`
- matched malicious domain from `URLhaus`: `+14`
- direct `ThreatFox` IOC match: `+18`
- malware family or threat type consistent with downloaders/stealers/RATs: `+8`
- strong VT malicious consensus: `+16`
- suspicious but inconclusive VT result: `+8`

Low-signal or benign observations should not increase the score materially. The implementation explicitly avoids boosting severity from weak or neutral provider claims.

### Change Score

Change score measures how the skill evolved relative to the previous snapshot.

- new upload or exfil flow: `+18`
- new remote-execution or installer behavior: `+16`
- new obfuscation layer or hidden binary: `+12`
- new domain, URL, or IP introduced: `+8`
- new IOC that already exists in Abuse.ch: `+14`
- suspicious IOC or downloader removed: negative adjustment

This is what turns SK Risk into a monitoring system rather than a one-time scanner.

### Confidence Labels

- `suspected`: suspicious local behavior with little or no corroboration
- `likely`: local behavior plus at least one strong external signal or repeated suspicious changes
- `confirmed`: strong malicious behavior plus strong external corroboration

Confidence never overrides severity. A clean VT result does not make suspicious local behavior safe; it only means VT did not confirm it.

## Impact And Priority Scoring

SK Risk keeps three separate analyst concepts:

- `risk`: how suspicious or malicious the behavior looks
- `impact`: how much current install reach the skill has
- `priority`: how urgently the skill should be triaged

Severity labels still come only from the risk model above. Install telemetry raises or lowers `impact_score` and `priority_score`, not `severity`.

### Impact Score

`impact_score` is derived from the latest known weekly installs plus momentum versus the previous install observation. `peak_weekly_installs` is exposed as context in the API and frontend, but it is not currently a scoring input.

Base impact ladder:

- `<=0` or unknown installs: `0`
- `1-9`: `5`
- `10-99`: `15`
- `100-999`: `30`
- `1,000-9,999`: `50`
- `10,000-49,999`: `70`
- `50,000+`: `90`

Momentum adjustments:

- previous installs unknown: no momentum adjustment
- previous installs `<=0` and current installs `>0`: `+20`
- current installs at least `2x` previous installs: `+20`
- current installs at least `1.1x` previous installs: `+10`
- current installs at or below `0.5x` previous installs: `-10`

`impact_score` is clamped to `0-100`.

### Priority Score

`priority_score` multiplies the base risk score by risk severity, confidence, and impact:

- severity multiplier:
  `none=0.5`,
  `low=0.7`,
  `medium=0.9`,
  `high=1.0`,
  `critical=1.1`
- confidence multiplier:
  `suspected=0.9`,
  `likely=1.0`,
  `confirmed=1.1`
- impact multiplier:
  `1 + (impact_score / 200)`

The final priority is rounded and clamped to `0-100`. This keeps a risky high-install skill near the top of the queue while leaving the severity label unchanged.

## API And Frontend Surfaces

Install telemetry is exposed on both backend and frontend surfaces.

### Backend API

- `/api/skills` returns `current_weekly_installs`, `current_weekly_installs_observed_at`, `peak_weekly_installs`, `weekly_installs_delta`, `impact_score`, and `priority_score`
- `/api/skills` supports `min_weekly_installs`, `max_weekly_installs`, and `sort=priority|risk|installs|growth`
- when `sort` is omitted, the backend defaults to priority ordering, then breaks ties by installs, risk score, and snapshot recency
- `/api/skills/{publisher}/{repo}/{skill_slug}` returns the same summary fields plus `install_history`

### Frontend

- `frontend/src/lib/api.ts` requests `/api/skills?limit=0&sort=priority`, so the `/skills` route starts in priority-first order
- `/skills` keeps `Priority` and `Weekly Installs` as dedicated columns, supports local severity and install-bucket filters (`0-9`, `10-99`, `100-999`, `1k-9.9k`, `10k+`), and lets analysts switch between priority and install sorting
- `/skills/[publisher]/[repo]/[skill_slug]` displays latest installs, peak installs, install delta, impact, priority, and the append-only history table
- detail history labels both `directory_fetch` and `scan_attribution` so the analyst can distinguish registry provenance from scan-time attribution

## Indicator Lifecycle

1. A skill snapshot is ingested and decoded.
2. URLs, domains, IPs, and hashes are extracted into canonical `indicators`.
3. Each extracted IOC is recorded in `skill_indicator_links` with source path and extraction kind.
4. Existing `indicator_observations` are loaded and folded into the skill’s current risk report.
5. High-priority indicators are queued for VT enrichment if they meet the budget and severity rules.
6. The frontend exposes both the skill-level summary and the underlying IOC evidence.

## VT Budgeting

`VT_APIKEY` is capped at `490` lookups per day. SK Risk should reserve part of that budget for manual analyst use, so automation is designed around a lower internal ceiling.

Priority order:

- IOCs from `critical` skills
- IOCs tied to downloader or exfil behavior
- newly introduced hashes or URLs
- indicators already corroborated by Abuse.ch but still needing stronger confirmation

Do not use VT for broad backfills or low-signal bulk enrichment.

## Phase 2

The next enrichment layer is planned around:

- `mewhois`
- `meip`
- Merklemap CT/DNS pivots
- infrastructure rarity and registrar/nameserver scoring

Those enrichments should sit beside the current indicator model, not replace it.
