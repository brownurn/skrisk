# Exfiltration Evidence Example Review

Date: 2026-03-11

## Summary

Two skills were reviewed as concrete examples for the next SK Risk evidence model:

- `ccheney/robust-skills/clean-ddd-hexagonal`
- `176336109/.openclaw/bocha-web-search`

The first is a false-positive cleanup example. The second is the better template for country-risk-aware outbound evidence.

## Clean DDD Hexagonal

`clean-ddd-hexagonal` should not be presented as malicious.

What the current reanalysis shows:

- latest severity: `none`
- latest score: `0`
- outbound evidence: none

Why the earlier result was wrong:

- the old record was driven by reference documentation and sample code
- examples such as `process.env.DATABASE_URL` and local route/test snippets were being treated as operational exfiltration evidence
- there is no confirmed sensitive source to real remote sink path

This skill is now the example of what SK Risk should *not* claim without hard evidence.

## Bocha Web Search

`bocha-web-search` is the better evidence template.

What the current reanalysis shows:

- latest severity: `medium`
- latest score: `18`
- finding category: `credential_transmission`
- evidence path: `test_api.sh`
- observed source: `BOCHA_API_KEY`
- transport: `Authorization header`
- sink: `https://api.bocha.cn/v1/web-search`
- resolved IPs:
  - `123.57.128.210`
  - `8.147.108.53`
- resolved country: `China`
- ASN: `Hangzhou Alibaba Advertising Co.,Ltd.`
- high-risk classification: `primary cyber concern`

Important nuance:

- this is outbound credential transmission to a China-hosted service
- it is not automatically secret exfiltration unless the skill also demonstrates that it is reading local sensitive data and sending it out beyond normal API authentication/query behavior

## Product Direction

The UI/API should explain outbound evidence using four concrete pieces:

- what data/token/path was observed
- how it was transmitted
- where it was sent
- what IP/country/ASN the destination resolves to

Severity should only escalate to the highest levels for country risk when the foreign destination is part of a real operational outbound path, not a documentation reference.
