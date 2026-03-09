# SkillsMP Enrichment Rollout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Load the first live `skillsmp` corpus into SK Risk and add production-backed `mewhois` / `meip` infrastructure enrichment with graceful handling for the current `meip` outage.

**Architecture:** Reuse the canonical source-entry model already in SK Risk for `skillsmp` live ingestion, then add a separate infrastructure-enrichment service that resolves domains locally, calls `mewhois` and `meip` through configured URLs, archives raw responses, and links normalized results back to indicators and scanned skills.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, httpx, Click, Scrapling, SQLite, pytest, OpenSearch, Neo4j, SSH port forwarding

---

### Task 1: Add Runtime Config For Infrastructure Enrichment

**Files:**
- Modify: `src/skrisk/config.py`
- Create: `tests/test_config_infra.py`
- Modify: `README.md`

**Step 1: Write the failing test**

Create config tests proving:

- `mewhois` and `meip` URLs can be read from env
- URL defaults can follow local tunnel ports when explicit URLs are not set

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_config_infra.py -q
```

Expected: FAIL because these settings do not exist yet.

**Step 3: Write minimal implementation**

Update `src/skrisk/config.py` to add:

- `mewhois_url`
- `meip_url`
- `mewhois_port`
- `meip_port`

Document the env vars in `README.md`.

**Step 4: Run test to verify it passes**

Run the same pytest command and expect PASS.

**Step 5: Commit**

```bash
git add src/skrisk/config.py tests/test_config_infra.py README.md
git commit -m "feat: add infrastructure enrichment runtime config"
```

### Task 2: Add mewhois / meip Client Adapters

**Files:**
- Create: `src/skrisk/collectors/infrastructure.py`
- Create: `tests/test_infrastructure_collectors.py`

**Step 1: Write the failing test**

Create tests proving:

- `mewhois` lookup normalizes domain responses
- `meip` lookup normalizes IP responses
- provider errors are surfaced as structured unavailable/error results rather than uncaught exceptions

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_infrastructure_collectors.py -q
```

Expected: FAIL because the adapters do not exist.

**Step 3: Write minimal implementation**

Create `src/skrisk/collectors/infrastructure.py` with:

- `WhoisClient`
- `IPIntelClient`
- normalized result dataclasses
- failure/result status handling

**Step 4: Run test to verify it passes**

Run the same pytest command and expect PASS.

**Step 5: Commit**

```bash
git add src/skrisk/collectors/infrastructure.py tests/test_infrastructure_collectors.py
git commit -m "feat: add mewhois and meip clients"
```

### Task 3: Add Infrastructure Enrichment Service And Persistence

**Files:**
- Modify: `src/skrisk/storage/models.py`
- Modify: `src/skrisk/storage/database.py`
- Modify: `src/skrisk/storage/repository.py`
- Create: `src/skrisk/services/infrastructure_enrichment.py`
- Create: `tests/test_infrastructure_enrichment.py`

**Step 1: Write the failing test**

Create tests proving:

- domains are looked up through `mewhois`
- resolved IPs are looked up through `meip`
- raw provider payloads are archived
- `meip` failure does not prevent `mewhois` enrichment from being stored

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_infrastructure_enrichment.py -q
```

Expected: FAIL because the enrichment service and storage do not exist.

**Step 3: Write minimal implementation**

Add storage for provider results and archive references.

Create `src/skrisk/services/infrastructure_enrichment.py` to:

- resolve hostnames locally
- dedupe domains and IPs
- call `mewhois`
- call `meip`
- archive raw responses
- record normalized enrichment rows linked to indicators

**Step 4: Run test to verify it passes**

Run the same pytest command and expect PASS.

**Step 5: Commit**

```bash
git add src/skrisk/storage/models.py src/skrisk/storage/database.py src/skrisk/storage/repository.py src/skrisk/services/infrastructure_enrichment.py tests/test_infrastructure_enrichment.py
git commit -m "feat: persist infrastructure enrichment results"
```

### Task 4: Add CLI For Infrastructure Enrichment

**Files:**
- Modify: `src/skrisk/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing test**

Extend CLI tests to prove a new enrichment command:

- reads config
- initializes the DB
- runs the infrastructure enrichment service
- reports success with partial-provider failure counts

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_cli.py -q
```

Expected: FAIL because the command does not exist.

**Step 3: Write minimal implementation**

Add a CLI command such as:

```bash
skrisk enrich-infra --limit 200
```

The command should enrich a bounded set of candidate indicators and report:

- domains attempted
- IPs attempted
- `mewhois` successes/failures
- `meip` successes/failures

**Step 4: Run test to verify it passes**

Run the CLI test file again and expect PASS.

**Step 5: Commit**

```bash
git add src/skrisk/cli.py tests/test_cli.py
git commit -m "feat: add infrastructure enrichment cli"
```

### Task 5: Add SkillsMP Live Seed Strategy Helpers

**Files:**
- Create: `src/skrisk/services/skillsmp_seed_terms.py`
- Create: `tests/test_skillsmp_seed_terms.py`
- Modify: `README.md`
- Modify: `docs/discussions/2026-03-09-skillsmp-enrichment-rollout.md`

**Step 1: Write the failing test**

Create tests proving the seed-term generator yields a bounded, deduped set of high-signal queries suitable for the `skillsmp` daily budget.

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_skillsmp_seed_terms.py -q
```

Expected: FAIL because the helper does not exist.

**Step 3: Write minimal implementation**

Create a helper that produces a recommended query set for live seeding, biased toward:

- security
- tools
- shell
- network
- browser
- github
- deploy
- data
- api
- auth
- agent
- coding
- terminal

Document how to use those terms operationally.

**Step 4: Run test to verify it passes**

Run the same pytest command and expect PASS.

**Step 5: Commit**

```bash
git add src/skrisk/services/skillsmp_seed_terms.py tests/test_skillsmp_seed_terms.py README.md docs/discussions/2026-03-09-skillsmp-enrichment-rollout.md
git commit -m "docs: add skillsmp live seeding guidance"
```

### Task 6: Run The First Live SkillsMP Ingestion

**Files:**
- No code changes required if previous tasks are green
- Document: `docs/discussions/2026-03-09-skillsmp-enrichment-rollout.md`

**Step 1: Source live credentials**

Use the existing `.envrc` from the main checkout so `SKILLSMP_API_KEY` is available.

**Step 2: Run live API seed passes**

Run a bounded set of real commands, for example:

```bash
skrisk seed-registry --source skillsmp --query security --page 1
skrisk seed-registry --source skillsmp --query tools --page 1
skrisk seed-registry --source skillsmp --query agent --page 1
```

**Step 3: Run live discovery passes**

Run real discovery against high-signal pages such as:

```bash
skrisk sync-skillsmp-discovery https://skillsmp.com/categories/security
skrisk sync-skillsmp-discovery https://skillsmp.com/categories/tools
```

**Step 4: Verify source-entry growth**

Check the live database and record:

- `skillsmp` source entry count
- canonical overlap count with `skills.sh`
- any new repos/skills added

**Step 5: Document results**

Record the live ingestion counts in `docs/discussions/2026-03-09-skillsmp-enrichment-rollout.md`.

### Task 7: Run The First Live Infrastructure Enrichment Pass

**Files:**
- No code changes required if previous tasks are green
- Document: `docs/discussions/2026-03-09-skillsmp-enrichment-rollout.md`

**Step 1: Establish production access**

Use local SSH port forwards or explicit URLs pointing at the production host-backed services.

**Step 2: Run the enrichment command**

Example:

```bash
skrisk enrich-infra --limit 200
```

**Step 3: Verify outcomes**

Record:

- `mewhois` success count
- `meip` success count
- `meip` failure count if the outage persists
- domains resolved locally
- IPs attempted

**Step 4: Document the live blocker if needed**

If `meip` is still down, document the exact production error and keep the rollout marked as partial rather than pretending full success.

### Task 8: Full Verification And Merge

**Files:**
- Modify: `README.md`
- Modify: `docs/discussions/2026-03-09-skillsmp-enrichment-rollout.md`

**Step 1: Run verification**

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest -q
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m compileall src
cd frontend && npm test -- --run
cd frontend && npm run check
cd frontend && npm run build
docker compose config
```

**Step 2: Re-run a small live smoke check**

```bash
skrisk check-runtime
skrisk index-search --limit 25
skrisk project-graph --limit 25
```

**Step 3: Commit**

```bash
git add README.md docs/discussions/2026-03-09-skillsmp-enrichment-rollout.md
git commit -m "feat: roll out skillsmp enrichment and infrastructure intel"
```
