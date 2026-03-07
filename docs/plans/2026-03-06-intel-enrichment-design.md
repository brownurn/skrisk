# SK Risk Threat Intel And Frontend Design

## Goal

Extend SK Risk from a skill snapshotting prototype into a threat-intelligence platform that:

- archives immutable third-party feed evidence locally under `archive_root`
- normalizes indicators across skills and external feeds
- enriches the highest-risk findings with rate-limited VirusTotal lookups
- presents the resulting evidence in a Svelte analyst dashboard

This design is scoped for v1. It keeps storage local, preserves raw evidence, and avoids premature expansion into object storage, broad detonation, or large passive-DNS datasets.

## Approved Decisions

- Raw feed snapshots are stored immutably on local disk under `archive_root`.
- `data/` remains gitignored and is treated as runtime evidence, not source.
- Abuse.ch `URLhaus` and `ThreatFox` are the first bulk intel sources.
- VirusTotal is used only as a selective enrichment layer because the API key is capped at `490` lookups per day.
- Merklemap is deferred to a later phase as a domain and certificate enrichment provider.
- FastAPI remains the backend; the frontend moves to `Svelte` instead of extending the Jinja dashboard.

## Problem Statement

The current prototype can:

- discover skills from `skills.sh`
- mirror GitHub repositories
- snapshot skills and calculate a local risk report

It cannot yet:

- preserve third-party evidence over time
- correlate indicators across providers and skills
- distinguish raw provider observations from SK Risk conclusions
- throttle expensive enrichment providers
- explain risk changes with time-series evidence
- support a serious analyst workflow in the UI

The missing system is an intelligence layer that sits beside skill snapshots and turns extracted domains, URLs, IPs, and hashes into trackable objects with provenance and historical context.

## Architectural Approach

V1 uses a `feed-first archive + normalize` model.

### Why This Approach

- It preserves exact evidence for later replay and parser upgrades.
- It lets SK Risk re-run correlation and scoring without redownloading feeds.
- It separates raw provider claims from normalized entities and SK Risk verdicts.
- It aligns with the existing `skills.sh` snapshot model, which already treats history as a first-class concern.

### Rejected Alternatives

#### Lookup-first on demand

Rejected because it loses replayability, wastes the Abuse.ch bulk feeds, and forces high-latency enrichment every time a skill changes.

#### Full intel lake from day one

Rejected because it adds unnecessary complexity for v1 and would delay real scanning, scoring, and frontend delivery.

## Service Boundaries

V1 stays as one repository and one deployable backend, but with three explicit pipelines.

### 1. Intel Sync

Responsibilities:

- download raw Abuse.ch exports
- archive the exact response bodies
- record feed metadata and run results
- parse indicators into normalized tables

Cadence:

- every `24` hours

Initial providers:

- `URLhaus`
- `ThreatFox`

### 2. Skill Sync

Responsibilities:

- sync `skills.sh`
- mirror source repositories
- snapshot repos and skills
- extract indicators from skill artifacts
- link skill snapshots to indicators
- correlate skill indicators against known external observations
- calculate SK Risk-owned risk reports

Cadence:

- every `72` hours per repo

### 3. VT Triage

Responsibilities:

- process a queue of high-priority indicators only
- enforce daily call budgets
- cache raw VT responses and normalized verdict summaries
- raise confidence when VT corroborates local evidence

Cadence:

- multiple small runs per day

## Archive Layout

All raw external evidence is immutable and stored under `archive_root`.

### Directory Structure

```text
data/archive/
  intel/
    abusech/
      urlhaus/
        2026/
          03/
            06/
              141500Z/
                full.json.zip
                manifest.json
      threatfox/
        2026/
          03/
            06/
              141700Z/
                full.csv.zip
                manifest.json
    virustotal/
      url/
        2026/
          03/
            06/
              150200Z/
                <sha256>.json
                manifest.json
      domain/
      ip/
      file/
```

### Manifest Requirements

Each archive directory includes a sidecar `manifest.json` with:

- provider name
- feed name
- source URL
- fetched timestamp
- auth mode
- archive path
- SHA256 of the downloaded file
- compressed size in bytes
- extracted row count
- parser version
- success or failure state
- failure reason if parsing failed

The manifest is the evidence ledger that allows parser upgrades and repeatability without redownloading data.

## Data Model

The current `skills`, `skill_repos`, `skill_repo_snapshots`, `skill_snapshots`, and `external_verdicts` tables remain. V1 adds a parallel threat-intel schema.

### `intel_feed_runs`

One row per provider download and parse attempt.

Columns:

- `id`
- `provider`
- `feed_name`
- `fetched_at`
- `completed_at`
- `status`
- `source_url`
- `auth_mode`
- `parser_version`
- `archive_sha256`
- `archive_size_bytes`
- `row_count`
- `error_message`
- `created_at`

Purpose:

- operational history
- audit trail for feed health
- link parent for immutable archive artifacts

### `intel_feed_artifacts`

One row per raw file or derivative file produced during a feed run.

Columns:

- `id`
- `feed_run_id`
- `artifact_type`
- `relative_path`
- `sha256`
- `size_bytes`
- `content_type`
- `created_at`

Artifact types:

- `raw_archive`
- `manifest`
- `parsed_cache`

### `indicators`

Canonical unique IOC identity across the system.

Columns:

- `id`
- `indicator_type`
- `indicator_value`
- `normalized_value`
- `first_seen_at`
- `last_seen_at`
- `created_at`
- `updated_at`

Supported types for v1:

- `domain`
- `hostname`
- `url`
- `ip`
- `sha256`

Uniqueness:

- `(indicator_type, normalized_value)`

### `indicator_observations`

Provider- or source-specific claims about an indicator.

Columns:

- `id`
- `indicator_id`
- `feed_run_id`
- `source_provider`
- `source_feed`
- `provider_record_id`
- `classification`
- `confidence_label`
- `malware_family`
- `threat_type`
- `reporter`
- `first_seen_in_source`
- `last_seen_in_source`
- `provider_score`
- `summary`
- `raw_payload`
- `created_at`

Purpose:

- preserve what a provider actually claimed
- avoid flattening different providers into one unverifiable verdict
- support time-series history per indicator

### `skill_indicator_links`

Join table between a `skill_snapshot` and extracted indicators.

Columns:

- `id`
- `skill_snapshot_id`
- `indicator_id`
- `source_path`
- `extraction_kind`
- `raw_value`
- `is_new_in_snapshot`
- `created_at`

Extraction kinds:

- `inline-domain`
- `inline-url`
- `inline-ip`
- `decoded-base64`
- `script-string`
- `manifest-endpoint`
- `hash-reference`

Purpose:

- tell analysts exactly where the IOC came from
- make diffing possible across snapshots
- separate extraction evidence from external reputation

### `indicator_enrichments`

Cached results from non-bulk providers such as VirusTotal.

Columns:

- `id`
- `indicator_id`
- `provider`
- `lookup_key`
- `requested_at`
- `completed_at`
- `status`
- `archive_relative_path`
- `summary`
- `normalized_payload`
- `created_at`

Purpose:

- store results without repeated calls
- decouple queue state from cached enrichment state

### `vt_lookup_queue`

Explicit queue for VirusTotal triage.

Columns:

- `id`
- `indicator_id`
- `priority`
- `reason`
- `status`
- `attempt_count`
- `next_attempt_at`
- `requested_by`
- `created_at`
- `updated_at`

Statuses:

- `queued`
- `running`
- `completed`
- `failed`
- `rate_limited`
- `discarded`

### Relationship Summary

- a feed run has many artifacts
- an indicator has many observations
- a skill snapshot links to many indicators
- an indicator has many enrichments
- a VT queue item targets one indicator

This model preserves provenance and lets SK Risk answer both directions:

- which indicators appear in this skill
- which skills, repos, and publishers reuse this infrastructure

## Scan Flow

### Abuse.ch Ingestion

1. Read `ABUSECH_AUTH_KEY` from runtime environment.
2. Download the full `URLhaus` archive.
3. Write the raw archive and `manifest.json` under `archive_root`.
4. Record an `intel_feed_run`.
5. Parse the file into normalized indicators and observations.
6. Repeat for `ThreatFox`.
7. Mark old observations historical by `last_seen_in_source` without deleting them.

### Skill Scanning

1. Discover repo and skill entries from `skills.sh`.
2. Mirror the repo.
3. Snapshot repo and skill state.
4. Extract indicators from plain text and decoded content.
5. Upsert canonical indicators.
6. Record `skill_indicator_links`.
7. Fetch current external observations for matching indicators.
8. Produce a risk report that combines behavior, intel corroboration, and change signals.
9. Queue VT enrichment only if the indicator meets triage rules.

### VirusTotal Triage

1. Select queued indicators by descending priority.
2. Stop before the daily budget is exceeded.
3. Fetch VT data for the indicator type.
4. Archive the raw response.
5. Normalize a compact verdict summary into `indicator_enrichments`.
6. Update risk confidence for linked skills on the next scoring pass.

## Detailed Scoring Methodology

SK Risk owns the risk decision. External feeds raise confidence and context; they do not replace local evidence.

The scoring model uses four dimensions:

- `behavior_score`
- `intel_score`
- `change_score`
- `confidence_score`

The first three produce a numeric severity score. The fourth produces a separate confidence label.

### Severity Score Scale

Base severity score range:

- minimum: `0`
- practical v1 range: `0-120`

Severity mapping:

- `0-9`: `none`
- `10-24`: `low`
- `25-44`: `medium`
- `45-69`: `high`
- `70+`: `critical`

This mapping is intentionally strict about `critical`. A skill only reaches `critical` when behavior is strongly suspicious or behavior and external intel reinforce each other.

### Behavior Score

Behavior is the most important dimension because it reflects what the skill itself appears to do.

#### Exfiltration Indicators

- reads local credential or secret files: `+18`
- explicitly references environment secrets for outbound use: `+18`
- posts local content to a remote endpoint: `+22`
- bundles files or logs for upload: `+20`
- targets browser data, shell history, SSH keys, cloud credentials, or wallet files: `+25`

#### Remote Execution And Installer Behavior

- `curl|sh`, `wget|sh`, or equivalent download-and-execute pattern: `+22`
- shell execution of arbitrary remote content: `+20`
- package install during skill flow: `+12`
- binary download followed by execute or chmod: `+24`
- hidden helper scripts that execute external commands: `+14`

#### Obfuscation And Evasion

- Base64 payload that decodes to command execution or network activity: `+14`
- multi-layer decoding chain: `+18`
- heavy string splitting or charcode reconstruction for executable content: `+14`
- suspicious compression or archive unpacking step: `+8`
- evidence of deliberate concealment in comments or misleading docs: `+10`

#### Prompt And Trust Abuse

- prompt text attempting to override host safety or previous instructions: `+10`
- deceptive claims about what the skill does: `+8`
- explicit instruction to ignore local policy or security review: `+10`
- instructions to fetch and trust remote prompts or config dynamically: `+10`

#### Network And Infrastructure Behavior

- hard-coded external domain or URL in a suspicious context: `+6`
- multiple unrelated external domains in one skill: `+6`
- dynamic endpoint assembly from fragments or encoded pieces: `+10`
- direct IP usage instead of hostname: `+8`
- use of paste sites, raw content mirrors, ephemeral hosts, or tunneling-style endpoints: `+12`

#### Benign Dampeners

These are reductions, not exonerations. They prevent common legitimate tooling from inflating risk too aggressively.

- domain belongs to widely used package registries or major cloud APIs and behavior is otherwise normal: `-4`
- shell execution limited to clearly local utility tasks with no download or upload: `-4`
- external URLs present only in documentation examples with no execution path: `-3`

The behavior score floor is `0`.

### Intel Score

Intel score reflects corroboration from external providers.

#### URLhaus Signals

- direct URL match in `URLhaus`: `+22`
- matched domain associated with known malicious URLs: `+14`
- payload URL currently active or recently active: `+6`

#### ThreatFox Signals

- direct IOC match in `ThreatFox`: `+18`
- malware family present: `+8`
- threat type suggests downloader, stealer, RAT, or botnet infrastructure: `+8`

#### VirusTotal Signals

VirusTotal is only queried for the highest-signal candidates.

- domain or URL with high malicious consensus: `+16`
- file hash with malicious detections across multiple engines: `+20`
- suspicious but not strongly malicious consensus: `+8`
- clean or inconclusive VT result: `+0`

The VT score is capped to avoid over-trusting a single vendor. VT increases corroboration but does not by itself force `critical` without meaningful behavior signals.

### Change Score

Change score measures how a skill evolved from its previous snapshot. It captures risk expansion over time.

#### New Suspicious Capability

- new upload or exfil flow added: `+18`
- new remote execute or installer flow added: `+16`
- new obfuscation layer added: `+12`
- new hidden file or binary introduced: `+12`

#### New Infrastructure

- new domain or URL appears in latest snapshot: `+8`
- previously unseen direct IP appears: `+8`
- new IOC that already exists in Abuse.ch: `+14`
- new IOC queued for VT because of suspicious behavior: `+6`

#### De-escalation Signals

- suspicious IOC removed: `-4`
- downloader or upload behavior removed: `-8`

The change score can be negative, but the total severity score floor remains `0`.

### Confidence Score

Confidence is a separate classification because a highly suspicious but novel skill may deserve `high` severity with only `suspected` confidence.

Confidence labels:

- `suspected`
- `likely`
- `confirmed`

#### `suspected`

Use when:

- suspicious behavior is present
- external corroboration is missing or weak
- evidence is still largely local and inferential

#### `likely`

Use when any of these are true:

- suspicious behavior plus one strong external match
- multiple weaker external matches
- repeated suspicious changes over time pointing in the same direction

#### `confirmed`

Use when any of these are true:

- strong malicious behavior plus strong external corroboration
- a downloaded hash or URL is directly matched to known malware infrastructure
- the skill clearly exfiltrates or downloads malware and that infrastructure is externally verified

Confidence must never exceed what the evidence supports. A clean VT result does not reset confidence to benign; it only means VT did not corroborate the IOC.

### Example Severity Outcomes

#### Example A: downloader with external corroboration

- `curl|sh`: `+22`
- Base64 command reconstruction: `+14`
- suspicious domain: `+6`
- URLhaus direct URL hit: `+22`
- new IOC introduced this version: `+8`

Total: `72`
Severity: `critical`
Confidence: `confirmed`

#### Example B: novel exfiltration flow with no external match yet

- reads local tokens: `+18`
- uploads to remote endpoint: `+22`
- hidden endpoint assembly: `+10`
- new domain in latest version: `+8`

Total: `58`
Severity: `high`
Confidence: `suspected`

#### Example C: benign local automation with references to GitHub URLs

- shell execution for local tooling: `+4`
- GitHub URL in docs: `+0`
- benign dampener for docs-only URL: `-3`

Total: `1`
Severity: `none`
Confidence: `suspected`

## VT Budgeting Strategy

The VT key is limited to `490` lookups per day. V1 should hard-cap automated use to `450` per day and leave roughly `40` calls for manual analyst work.

### Queue Priority Rules

Highest priority:

- IOC extracted from a `critical` skill
- IOC tied to download-and-execute behavior
- IOC tied to exfiltration behavior
- newly introduced hash or URL

Medium priority:

- IOC extracted from a `high` skill
- IOC matched by one Abuse.ch source but missing a stronger verdict

Low priority:

- IOC from medium-risk skills without corroboration
- repeated low-signal domains already seen elsewhere in benign contexts

### Budget Enforcement Rules

- no provider-wide backfills with VT
- no repeated VT lookups for cached fresh results
- cooldown and retry windows for rate-limited lookups
- manual lookup headroom preserved every day

## Frontend Architecture

The current Jinja pages are sufficient for bootstrap visibility but should not be the long-term UI.

### Stack

- backend: `FastAPI`
- frontend: `Svelte` with a modern build setup
- transport: JSON API from FastAPI

### Primary Screens

#### Overview

Shows:

- tracked repos
- tracked skills
- critical skills
- high-risk skills
- intel-backed findings
- pending VT queue
- recently changed risky skills

#### Skills Explorer

Features:

- severity filters
- category filters
- intel-backed only toggle
- newly changed only toggle
- publisher and repo filtering

#### Skill Detail

Shows:

- severity and confidence
- local behavior findings
- extracted indicators with source path evidence
- Abuse.ch matches
- VT status and summaries
- snapshot history and behavioral diffs

#### Indicator Detail

Shows:

- canonical indicator identity
- all observed provider matches
- all linked skills and snapshots
- enrichment history
- timeline of first and last seen values

#### Repo Detail

Shows:

- all skills in the repo
- shared infrastructure
- risk concentration across versions

### UX Direction

The UI should feel like an analyst console, not a generic SaaS admin page.

Guidance:

- prioritize dense, scanable tables and diff surfaces
- use restrained accent colors for severity states
- keep alert colors meaningful and sparse
- use strong typography hierarchy and obvious evidence blocks
- support keyboard navigation and visible focus states
- honor reduced-motion preferences

## API Changes

The existing FastAPI routes are a starting point but not enough for the Svelte app.

Add endpoints for:

- intel feed run summaries
- indicator search and detail
- skill indicator links
- VT queue status
- recent risk changes
- snapshot diffs between successive skill versions

## Merklemap Phase 2

Merklemap is deferred intentionally.

Planned future uses:

- certificate pivoting around suspicious domains
- sibling subdomain discovery
- CT-based clustering of infrastructure families
- domain expansion around exfiltration endpoints

It is not required for v1 because:

- it is not the primary malware verdict source
- its large DNS dataset is operationally unnecessary for the first rollout
- SK Risk first needs a clean indicator model and evidence-driven UI

## Non-Goals For V1

- full object-storage deployment
- malware detonation or live execution of skills
- broad passive-DNS ingestion
- global infrastructure graph analytics beyond the normalized indicator model
- automatic blocking or takedown workflows

## Testing Strategy

V1 implementation must add tests for:

- feed archive download and manifest creation
- parser normalization for `URLhaus` JSON and `ThreatFox` CSV
- canonical indicator upserts
- skill-to-indicator linking
- VT queue prioritization and daily budget enforcement
- score calculation for behavior-only, intel-backed, and changed-snapshot scenarios
- API responses that power the Svelte dashboard

## Rollout Sequence

1. add the intel archive and indicator schema
2. implement Abuse.ch sync and normalization
3. link skill snapshots to canonical indicators
4. add scoring expansion and confidence modeling
5. add VT triage queue and caching
6. expand API surface
7. replace Jinja dashboard with Svelte frontend

This order gets real intelligence flowing before UI polish and keeps expensive enrichment last.
