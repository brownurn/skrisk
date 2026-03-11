# Neo4j Bulk Import Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the slow transactional Neo4j full rebuild with a Postgres CSV export plus offline `neo4j-admin` bulk import.

**Architecture:** A new bulk graph service will stream graph CSV files out of Postgres into a timestamped bundle, then orchestrate a stop/import/start cycle for the existing Docker Compose Neo4j service. The existing `project-graph` path remains available for small transactional work, but full rebuilds move to the bulk path.

**Tech Stack:** Python, asyncpg, Docker Compose, Neo4j `neo4j-admin`, Postgres, pytest

---

### Task 1: Add failing tests for the bulk export bundle

**Files:**
- Create: `tests/test_graph_bulk.py`
- Modify: `src/skrisk/services/graph_project.py`

**Step 1: Write the failing test**

Add a test that calls a new export service against a fake Postgres connection and expects all required CSV files to be created:

- `skills.csv`
- `repos.csv`
- `registries.csv`
- `indicators.csv`
- `asns.csv`
- `registrars.csv`
- `organizations.csv`
- `nameservers.csv`
- `hosted_in.csv`
- `seen_in.csv`
- `emits.csv`
- `resolves_to.csv`
- `announced_by.csv`
- `registered_with.csv`
- `registered_to.csv`
- `uses_nameserver.csv`

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_graph_bulk.py::test_export_bundle_writes_expected_csvs -q
```

Expected: FAIL because the export service does not exist yet.

**Step 3: Write minimal implementation**

Add the bulk export service and required CSV file manifest in `src/skrisk/services/graph_project.py`.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm PASS.

**Step 5: Commit**

```bash
git add tests/test_graph_bulk.py src/skrisk/services/graph_project.py
git commit -m "feat: add graph bulk export service"
```

### Task 2: Add failing tests for Neo4j bulk import orchestration

**Files:**
- Modify: `tests/test_graph_bulk.py`
- Modify: `src/skrisk/services/graph_project.py`

**Step 1: Write the failing test**

Add a test that verifies a new import orchestration method issues:

1. `docker compose stop neo4j`
2. `docker compose run --rm --no-deps ... neo4j-admin database import full ...`
3. `docker compose up -d neo4j`

and uses the provided bundle directory plus thread/memory settings.

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_graph_bulk.py::test_import_bundle_runs_stop_import_start_sequence -q
```

Expected: FAIL because the import orchestration path does not exist yet.

**Step 3: Write minimal implementation**

Implement the import orchestration and command building in `src/skrisk/services/graph_project.py`.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm PASS.

**Step 5: Commit**

```bash
git add tests/test_graph_bulk.py src/skrisk/services/graph_project.py
git commit -m "feat: add neo4j bulk import orchestration"
```

### Task 3: Add failing tests for the new CLI command

**Files:**
- Modify: `tests/test_graph_bulk.py`
- Modify: `src/skrisk/cli.py`

**Step 1: Write the failing test**

Add a CLI test that expects a new command:

- `skrisk rebuild-graph-bulk`

and verifies the command invokes export and import in the right order.

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_graph_bulk.py::test_rebuild_graph_bulk_cli_invokes_export_then_import -q
```

Expected: FAIL because the CLI command does not exist yet.

**Step 3: Write minimal implementation**

Add the new CLI command in `src/skrisk/cli.py`.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm PASS.

**Step 5: Commit**

```bash
git add tests/test_graph_bulk.py src/skrisk/cli.py
git commit -m "feat: add bulk graph rebuild command"
```

### Task 4: Add documentation for the new graph rebuild path

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-11-neo4j-bulk-import-design.md`

**Step 1: Write the documentation changes**

Document:

- when to use `project-graph`
- when to use `rebuild-graph-bulk`
- the fact that full rebuilds are offline imports
- the expected Docker/Neo4j behavior

**Step 2: Verify documentation references the actual command**

Run:

```bash
rg -n "rebuild-graph-bulk|project-graph|neo4j-admin" README.md docs/plans/2026-03-11-neo4j-bulk-import-design.md
```

Expected: relevant matches only.

**Step 3: Commit**

```bash
git add README.md docs/plans/2026-03-11-neo4j-bulk-import-design.md
git commit -m "docs: describe bulk graph rebuild path"
```

### Task 5: Run the full verification suite

**Files:**
- No code changes expected

**Step 1: Run targeted tests**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_graph_project.py tests/test_graph_bulk.py -q
```

Expected: PASS

**Step 2: Run the broader test suite**

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Expected: PASS

**Step 3: Run compile verification**

```bash
PYTHONPATH=src .venv/bin/python -m compileall src
```

Expected: PASS

### Task 6: Execute the live bulk rebuild

**Files:**
- Runtime artifacts only

**Step 1: Stop the old transactional graph projector**

Stop any existing `project-graph` jobs before launching the new path.

**Step 2: Launch the new bulk rebuild**

Run:

```bash
PYTHONPATH=src .venv/bin/skrisk rebuild-graph-bulk
```

Expected:

- CSV bundle exported under `data/archive/graph-import/<timestamp>/`
- `neo4j` stopped
- `neo4j-admin` import runs
- `neo4j` restarts

**Step 3: Verify live graph counts**

Run:

```bash
curl -s -u neo4j:skriskneo4j http://127.0.0.1:17474/db/neo4j/tx/commit \
  -H 'Content-Type: application/json' \
  -d '{"statements":[{"statement":"MATCH (n) RETURN count(n) AS nodes"},{"statement":"MATCH ()-[r]->() RETURN count(r) AS rels"}]}'
```

Expected: nonzero node and relationship counts.

**Step 4: Commit**

```bash
git add src/skrisk/services/graph_project.py src/skrisk/cli.py tests/test_graph_bulk.py README.md docs/plans/2026-03-11-neo4j-bulk-import-design.md docs/plans/2026-03-11-neo4j-bulk-import-implementation.md
git commit -m "feat: add neo4j bulk graph rebuild"
```
