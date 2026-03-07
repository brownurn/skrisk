# Risk And Intelligence Model

This document describes the SK Risk v1 data model, risk system, and how external intelligence is folded into skill-level findings.

## Core Principle

SK Risk owns the risk decision. Third-party feeds and enrichment providers increase confidence and context, but they do not replace local evidence from the skill snapshot itself.

## Data Model

The risk system is built from two layers:

- skill state: repos, skill snapshots, extracted artifacts, and risk reports
- intelligence state: canonical indicators, provider observations, enrichment cache, and VT triage

### Skill-State Tables

- `skill_repos`: tracked source repositories
- `skill_repo_snapshots`: repo-level points in time
- `skills`: canonical skill identities
- `skill_snapshots`: versioned skill content, extracted domains, and serialized risk report
- `external_verdicts`: partner verdicts kept separate from SK Risk’s own scoring

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

## Risk Scoring

SK Risk uses four dimensions:

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
