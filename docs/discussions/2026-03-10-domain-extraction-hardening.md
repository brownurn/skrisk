# Domain Extraction Hardening

## Date
- March 10, 2026

## Problem
- The analyzer regressed and started treating dotted code/property tokens as domains.
- `Extracted domains` on skills such as `rivet-dev/skills/sandbox-agent` included values like:
  - `app.use`
  - `client.postmessage`
  - `sdk.dispose`
  - `a.id`
  - `item.started`
  - `process.env`
  - malformed template hosts such as `localhost${path}${query}`
- Loopback, placeholder, and reserved example hosts were also being mixed into the domain inventory.

## Root Cause
- Bare-domain extraction was too permissive for markdown/reference content with code blocks.
- URL host extraction was trusting malformed or low-signal hosts without enough validation.
- The analysis pipeline was promoting those values into persistent indicators.

## Fix
- Strip fenced markdown code blocks and inline code spans before bare-domain extraction on markdown-like files.
- Prevent bare-domain submatches inside larger dotted hosts.
- Harden candidate validation to reject:
  - obvious code/member-access tokens
  - two-label code-like values such as `item.started`
  - file-like values such as `skill.md`
  - template/malformed values containing `${...}`, backticks, angle brackets, or similar artifacts
  - placeholder domains such as `*.example.com` and `your-*.com`
  - low-signal local hosts such as `localhost`
- Suppress loopback, private, reserved, and placeholder hosts from URL-host indicator generation.

## Verification
- Local `sandbox-agent` domain inventory dropped from `271` entries to `21` plausible hosts.
- Representative remaining hosts include:
  - `api.anthropic.com`
  - `releases.rivet.dev`
  - `sandboxagent.dev`
  - `developers.cloudflare.com`
  - `www.daytona.io`
- Python test suite result after the fix:
  - `163 passed`

## Follow-Up
- Re-run the full repo-first analysis wave so persisted indicators and latest snapshots are regenerated under the hardened extractor.
