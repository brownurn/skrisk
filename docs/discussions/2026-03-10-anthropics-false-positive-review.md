# Anthropics False Positive Review

Date: 2026-03-10

## Summary

`anthropics/skills/skill-creator` was previously surfaced as high/critical due to analyzer false positives, not because we found hard evidence of malware or covert exfiltration.

Latest reviewed posture:

- skill: `anthropics/skills/skill-creator`
- latest snapshot severity: `none`
- score: `0`
- findings: none

## What Went Wrong

Two heuristic classes were too broad:

1. Obfuscation scoring
   - benign reconstructed strings from AST and unicode decoding paths were treated as obfuscation findings
   - this overstated risk in normal tooling-heavy repos

2. Exfiltration scoring
   - generic SDK/client code that referenced `process.env.*` and an HTTPS API base URL could be misread as exfiltration
   - that is not hard evidence of secrets leaving the machine

Bare-domain extraction also produced code-token noise in some source files.

## Anthropic Skill Review

Manual review of the mirrored repo showed normal tooling behavior:

- explicit `claude -p` subprocess usage for evaluation/tooling
- local HTTP review server on `localhost`
- browser asset loads such as:
  - `fonts.googleapis.com`
  - `fonts.gstatic.com`
  - `cdn.sheetjs.com`

We did **not** find:

- covert downloader behavior
- suspicious hidden domains/IPs
- malware payload delivery
- hard evidence of data exfiltration

## Changes Made

- tightened obfuscation handling so benign reconstructed text is not enough to imply maliciousness
- tightened exfiltration heuristics so normal API base URLs do not become `data_exfiltration`
- reduced bogus bare-domain extraction from code/file-like tokens
- added a skill-detail evidence section that separates:
  - hard evidence
  - supporting signals
  - observed infrastructure

## Operational Follow-Up

- `anthropics/skills/skill-creator` was re-persisted into Postgres with the corrected analyzer result
- the currently flagged repo subset was marked due again so visible dashboard rows can be rescored with the corrected logic
