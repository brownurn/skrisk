# Exfiltration Evidence And Country Risk Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add structured outbound evidence and primary-cyber-concern country classification so SK Risk can explain what data was sent, where it went, and whether the destination country is a policy concern.

**Architecture:** Add a small policy module, extend analyzer findings with structured outbound evidence metadata, enrich skill-detail payloads with destination IP/country context from existing `local_dns` and `meip` enrichments, then render the result in the Svelte skill detail page.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Postgres, SvelteKit, Vitest, Pytest

---

### Task 1: Add country-risk policy helper

**Files:**
- Create: `src/skrisk/policy.py`
- Test: `tests/test_policy.py`

**Step 1: Write the failing test**

Add tests that:
- normalize `Tanazania` to `Tanzania`
- treat `CN` / `China` as primary cyber concern
- treat both Congo variants as primary cyber concern
- treat `US` as not primary cyber concern

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_policy.py -q`

**Step 3: Write minimal implementation**

Implement a helper returning normalized country metadata and a boolean risk flag.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_policy.py -q`

### Task 2: Add structured outbound evidence to analyzer findings

**Files:**
- Modify: `src/skrisk/analysis/analyzer.py`
- Test: `tests/test_analysis.py`

**Step 1: Write the failing tests**

Add tests for:
- direct secret exfiltration with `curl -X POST ... -F secret=$AWS_SECRET_ACCESS_KEY`
- credential transmission with `Authorization: Bearer $BOCHA_API_KEY`
- reference-example credential/API docs staying downgraded

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_analysis.py -q`

**Step 3: Write minimal implementation**

Add structured `details` to findings and classify outbound evidence into:
- `secret_exfiltration`
- `credential_transmission`

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_analysis.py -q`

### Task 3: Shape skill-detail payload with destination IP/country evidence

**Files:**
- Modify: `src/skrisk/storage/repository.py`
- Test: `tests/test_api.py`

**Step 1: Write the failing tests**

Add an API-level test asserting skill detail includes outbound evidence entries with:
- source values
- sink host/url
- resolved IP
- country
- `is_primary_cyber_concern`

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api.py -q`

**Step 3: Write minimal implementation**

Build outbound evidence entries from:
- `risk_report.findings[*].details`
- matching `indicator_links`
- `local_dns` and `meip` enrichments
- new country-risk helper

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api.py -q`

### Task 4: Render outbound evidence on the skill detail page

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/+page.svelte`
- Test: `frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/page.test.ts`

**Step 1: Write the failing test**

Add a page test that expects:
- an `Outbound evidence` section
- explicit `what was sent`
- destination host
- destination IP/country
- primary-cyber-concern badge

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/routes/skills/[publisher]/[repo]/[skill_slug]/page.test.ts`

**Step 3: Write minimal implementation**

Add new client types/normalizers and render the evidence section.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run src/routes/skills/[publisher]/[repo]/[skill_slug]/page.test.ts`

### Task 5: Re-evaluate example skills and verify the end-to-end result

**Files:**
- Modify: `docs/discussions/2026-03-11-exfil-evidence-country-risk-rollout.md`

**Step 1: Run focused verification**

Check:
- `ccheney/robust-skills/clean-ddd-hexagonal`
- `176336109/.openclaw/bocha-web-search`

**Step 2: Verify API/UI behavior**

Run:
- `curl -s http://127.0.0.1:8080/api/skills/ccheney/robust-skills/clean-ddd-hexagonal | jq '.'`
- `curl -s http://127.0.0.1:8080/api/skills/176336109/.openclaw/bocha-web-search | jq '.'`

Document whether each is:
- false positive / no exfil
- credential transmission
- secret exfiltration

### Task 6: Final verification

**Step 1: Run backend verification**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q`

**Step 2: Run frontend verification**

Run:
- `cd frontend && npm test -- --run`
- `cd frontend && npm run check`
- `cd frontend && npm run build`

**Step 3: Run compile verification**

Run: `PYTHONPATH=src .venv/bin/python -m compileall src`
