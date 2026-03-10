# Scoring Accuracy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce false-positive `critical` skills by making the analyzer context-aware for reference/example and router/catalog content while preserving strong scores for real operational behavior.

**Architecture:** Keep the existing analyzer pipeline, but classify each file and skill into contextual buckets before scoring. Preserve findings for analyst visibility, then compute weighted scores and a router/catalog severity cap from the contextualized findings.

**Tech Stack:** Python, pytest, FastAPI-backed rescoring pipeline, Postgres-backed live corpus

---

### Task 1: Add failing analyzer tests for reference/example false positives

**Files:**
- Modify: `tests/test_analysis.py`

**Step 1: Write the failing tests**

Add tests covering:
- a reference-heavy security skill that mentions cookies/tokens/webhooks and example HTTP calls but should not become `critical`
- a router/catalog skill that references installer snippets in docs and should not become `critical`
- a direct operational infra/admin skill that should stay `high` or `critical`

**Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_analysis.py -q
```

Expected:
- the new tests fail because the current analyzer still over-scores reference and router/catalog content

**Step 3: Commit**

```bash
git add tests/test_analysis.py
git commit -m "test: capture scoring accuracy regressions"
```

### Task 2: Implement contextual file and skill classification

**Files:**
- Modify: `src/skrisk/analysis/analyzer.py`

**Step 1: Add minimal implementation**

Implement helpers for:
- file context classification (`direct_operational` vs `reference_example`)
- router/catalog skill detection from aggregated skill text and metadata
- contextual finding recording so scoring can see both category and context

**Step 2: Run targeted tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_analysis.py -q
```

Expected:
- tests still fail until the score model is updated

**Step 3: Commit**

```bash
git add src/skrisk/analysis/analyzer.py
git commit -m "feat: classify analyzer evidence context"
```

### Task 3: Gate high-severity scoring by context

**Files:**
- Modify: `src/skrisk/analysis/analyzer.py`
- Test: `tests/test_analysis.py`

**Step 1: Write minimal scoring update**

Adjust scoring so:
- direct operational `remote_code_execution` and `data_exfiltration` remain strong
- reference/example-only evidence contributes supporting weight
- router/catalog skills without direct-operational evidence cannot become `critical`

**Step 2: Run tests to verify they pass**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_analysis.py -q
```

Expected:
- new tests pass
- existing analyzer coverage stays green

**Step 3: Commit**

```bash
git add src/skrisk/analysis/analyzer.py tests/test_analysis.py
git commit -m "feat: reduce reference-driven critical scores"
```

### Task 4: Verify against the live flagged corpus

**Files:**
- Inspect only: live Postgres corpus via CLI/SQL

**Step 1: Run targeted verification against representative skills**

Check the representative cases:
- `github/awesome-copilot/create-web-form`
- `mcp-use/mcp-use/mcp-apps-builder`
- `openai/skills/security-best-practices`
- `cloudflare/skills/cloudflare`
- `jeffallan/claude-skills/kubernetes-specialist`

**Step 2: Rerun targeted rescoring**

Run the existing rescore path against the currently flagged population or the representative repos.

**Step 3: Verify live dashboard output**

Confirm:
- obvious reference/catalog skills drop out of the homepage critical list
- real operational infra/admin skills still rank highly

**Step 4: Commit**

```bash
git add docs/plans/2026-03-10-scoring-accuracy-design.md docs/plans/2026-03-10-scoring-accuracy-implementation.md
git commit -m "docs: record scoring accuracy plan"
```

### Task 5: Full verification

**Files:**
- Verify existing code only

**Step 1: Run Python test suite**

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Expected:
- all tests pass

**Step 2: Run bytecode verification**

```bash
PYTHONPATH=src .venv/bin/python -m compileall src
```

Expected:
- passes without syntax errors

**Step 3: Commit final cleanup if needed**

```bash
git add -A
git commit -m "chore: finalize scoring accuracy verification"
```
