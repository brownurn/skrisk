# Scoring Accuracy Verification

## Date
- March 10, 2026

## Goal
- Verify that the scoring-accuracy pass reduced reference/router false positives without suppressing real operational findings.

## What Changed
- Added context-aware scoring for:
  - `direct_operational`
  - `reference_example`
  - `router_catalog`
- Downgraded reference/example `remote_code_execution` and `data_exfiltration` findings from hard-scorable `critical` weight to supporting weight.
- Reduced single direct `curl|sh` style installer findings from automatic `critical` skill severity to `high` unless corroborated by stronger behavior or intel.
- Ignored URLhaus domain-level hits for shared platforms such as `github.com` so shared hosting providers do not automatically become malicious corroboration.

## Representative Before/After

### Corrected Downward
- `github/awesome-copilot/create-web-form`
  - before: `critical 100`
  - after: `medium 15`
- `mcp-use/mcp-use/mcp-apps-builder`
  - before: `critical 100`
  - after: `medium 15`
- `openai/skills/security-best-practices`
  - before: `critical 100`
  - after: `medium 15`
- `github/awesome-copilot/aspire`
  - before: `critical 100`
  - after: `high 40`
- `cloudflare/skills/cloudflare`
  - before: `critical 100`
  - after: `medium 20`
- `jeffallan/claude-skills/kubernetes-specialist`
  - before: `critical 100`
  - after: `medium 10`

## Concrete Evidence Checks
- `mcp-apps-builder` now shows only reference-path findings:
  - `references/authentication/custom.md`
  - `references/authentication/overview.md`
- `security-best-practices` now shows only reference-path findings:
  - `references/javascript-express-web-server-security.md`
  - `references/python-django-web-server-security.md`
- `aspire` still shows a direct operational installer in `SKILL.md`, but no longer inherits false malicious corroboration from shared-host URLhaus domain hits on `github.com`.

## Remaining Work
- The representative repos are rescored and corrected.
- The broader flagged population still needs a bulk refresh so the homepage and `/skills` reflect the new rules across all stale rows, not just the verified samples.
