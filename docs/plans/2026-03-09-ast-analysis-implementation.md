# Deep AST Analysis Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add parser-backed Python, JavaScript, and shell extraction plus richer decoders, then rerun the repo-first analysis across the mirrored corpus.

**Architecture:** Extend the existing `language_extractors` and `deobfuscator` layers rather than creating a second analyzer. Keep `SkillAnalyzer` as the single scoring pipeline, then reuse the Postgres-backed spool runtime to reanalyze the corpus at scale.

**Tech Stack:** Python, stdlib `ast`, `esprima`, `bashlex`, SQLAlchemy asyncio, Postgres, pytest

---

### Task 1: Add parser dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add the failing tests first**

Use tests in `tests/test_analysis.py` that require parser-backed JavaScript and shell reconstruction.

**Step 2: Add minimal dependencies**

- add `esprima`
- add `bashlex`

**Step 3: Reinstall editable package**

Run:

```bash
../../.venv/bin/pip install -e .
```

### Task 2: Add decoder coverage

**Files:**
- Modify: `src/skrisk/analysis/deobfuscator.py`
- Test: `tests/test_analysis.py`

**Step 1: Write failing tests**

Cover:

- hex-encoded URL recovery
- PowerShell `-enc` URL recovery

**Step 2: Implement decoders**

Add helpers for:

- printable hex decoding
- UTF-16LE Base64 PowerShell decode

**Step 3: Run focused tests**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_analysis.py -q
```

### Task 3: Deepen Python extraction

**Files:**
- Modify: `src/skrisk/analysis/language_extractors.py`
- Test: `tests/test_analysis.py`

**Step 1: Write failing tests**

Cover:

- `.join([...])`
- `.format(...)`
- `%` formatting
- simple `requests/httpx/urllib` call arguments

**Step 2: Implement bounded AST evaluation**

Extend the Python collector to reconstruct those string flows.

**Step 3: Run focused tests**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_analysis.py -q
```

### Task 4: Add JavaScript AST extraction

**Files:**
- Modify: `src/skrisk/analysis/language_extractors.py`
- Test: `tests/test_analysis.py`

**Step 1: Write failing tests**

Cover:

- template literals
- array `.join("")`
- `atob(...)`
- `decodeURIComponent(...)`
- `fetch/axios/XMLHttpRequest.open(...)` URL reconstruction

**Step 2: Implement JS AST visitor**

Parse the program with `esprima` and evaluate bounded string expressions.

**Step 3: Run focused tests**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_analysis.py -q
```

### Task 5: Add shell AST extraction

**Files:**
- Modify: `src/skrisk/analysis/language_extractors.py`
- Test: `tests/test_analysis.py`

**Step 1: Write failing tests**

Cover:

- shell variable concatenation
- `${VAR}` substitution
- `curl` and `wget` targets reconstructed from assignments

**Step 2: Implement shell parsing**

Use `bashlex` to walk assignments and simple command invocations.

**Step 3: Run focused tests**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_analysis.py -q
```

### Task 6: Verify analyzer integration

**Files:**
- Modify: `src/skrisk/analysis/analyzer.py` only if needed
- Test: `tests/test_analysis.py`

**Step 1: Keep extraction kinds explainable**

Make sure new indicators surface with consistent `extraction_kind` labels.

**Step 2: Run analyzer test suite**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_analysis.py -q
```

### Task 7: Full verification

**Files:**
- No code changes expected

**Step 1: Run full suite**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest -q
PYTHONPATH=src ../../.venv/bin/python -m compileall src
```

### Task 8: Relaunch corpus reanalysis

**Files:**
- No code changes expected

**Step 1: Apply the new analyzer to the corpus**

Use the existing Postgres-backed repo-first runtime with the `24` worker producer.

**Step 2: Keep ingesters small-batch for giant repos**

Use `--limit-artifacts 1` or another very small value so giant registry repos do not pin large ingest batches.
