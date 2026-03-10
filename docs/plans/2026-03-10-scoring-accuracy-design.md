# Scoring Accuracy Design

## Date
- March 10, 2026

## Problem
- The latest-snapshot critical list still contains broad guide, catalog, and reference skills that are unlikely to be malicious.
- The analyzer currently treats a single `remote_code_execution` or `data_exfiltration` match as enough to force `critical`, even when the evidence only appears in documentation, examples, or router/catalog skills.
- This creates high-severity noise on the homepage and `/skills`, which weakens analyst trust in the results.

## Evidence
- `mcp-use/mcp-use/mcp-apps-builder` was scoring `critical` from example `fetch(...)` calls in `references/authentication/*.md`.
- `openai/skills/security-best-practices` was scoring `critical` from security reference markdown that mentioned cookies, CSRF tokens, and webhook handling.
- `redis/agent-skills/redis-development` was scoring `critical` from `curl -X POST` examples in docs and rules files.
- `cloudflare/skills/cloudflare` still contains real operational examples, including installer patterns and infrastructure guidance, so it remains a valid high-risk case.

## Root Cause
- The analyzer does not currently classify content context.
- Findings from `references/`, `docs/`, `examples/`, `README*`, `api.md`, `configuration.md`, `patterns.md`, and similar files are scored the same as active operational instructions in `SKILL.md` or executable scripts.
- Router/catalog skills that mostly point users to subskills or reference material are not distinguished from directly operational skills.

## Goals
- Reduce false-positive `critical` and `high` scores for guide, catalog, and reference-heavy skills.
- Preserve strong scores for skills that directly instruct install, execution, credential access, or operational infrastructure interaction.
- Keep the explanation model concrete and evidence-first.

## Non-Goals
- Do not redesign the entire taxonomy.
- Do not remove findings entirely from reference material; keep them visible as supporting context.
- Do not weaken clearly operational infra/admin skills just because they belong to reputable publishers.

## Decision
- Add context-aware scoring rather than only tuning weights.
- Classify findings by source context:
  - `direct_operational`
  - `reference_example`
  - `router_catalog`
- Use that context to gate high-severity categories:
  - `remote_code_execution` remains strong only when it appears in direct operational context.
  - `data_exfiltration` requires both sensitive source and remote sink plus direct operational context to remain strong.
  - Reference/example-only evidence is downgraded to supporting severity and lower score contribution.
- Apply a severity cap for router/catalog skills when all findings are contextual/reference-only.

## Heuristic Design

### File Context Classification
- Treat these as reference/example biased:
  - paths containing `references/`, `docs/`, `examples/`, `example/`
  - filenames such as `README`, `api.md`, `configuration.md`, `patterns.md`, `installation.md`
- Treat these as direct operational by default:
  - `SKILL.md`
  - executable script paths such as `.sh`, `.py`, `.js`, `.ts`, `.ps1`
  - automation/config files that are part of the skill itself rather than reference material

### Router/Catalog Skill Classification
- Detect router/catalog skills using text and metadata markers such as:
  - `navigation guide`
  - `choose the relevant skill`
  - `available skills`
  - `load reference files`
  - `catalog`
  - `router`
  - `index of skills`
- Only apply the router/catalog cap when the skill has no direct-operational evidence.

### Finding Severity Treatment
- `remote_code_execution`
  - direct operational: keep `critical`
  - reference/example: downgrade to supporting severity
- `data_exfiltration`
  - direct operational: keep `critical`
  - reference/example: downgrade to supporting severity unless it also includes explicit local-secret/file access and imperative operational guidance
- `obfuscation`
  - remains supporting only

### Score Model
- Keep categories intact for analyst visibility.
- Add score weights by category and context rather than only by category.
- Reference/example findings still contribute modestly so they are visible, but should not force `critical` alone.
- Router/catalog skills with only supporting evidence should cap at `medium` or `high` depending on aggregate score, never `critical`.

## UI/Analyst Impact
- The homepage critical list should stop surfacing obvious reference/catalog false positives.
- Skill detail pages still show the findings, but the overall score better reflects whether the behavior is directly performed by the skill.
- Existing repo drill-down and skill pages continue to work without schema changes.

## Test Strategy
- Add analyzer tests for:
  - reference docs with example exfil patterns not becoming `critical`
  - router/catalog skills with reference install snippets not becoming `critical`
  - direct operational infra/admin skills remaining high-risk
- Re-run targeted rescoring over the currently flagged set after the heuristic change.
