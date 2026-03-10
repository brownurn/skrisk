# Postgres Cutover Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace SQLite as the source-of-truth database with Postgres so the deep-analysis runtime can scale beyond the current single-writer ingest bottleneck.

**Architecture:** Keep the existing spool producers and artifact archive layout, introduce a generic async SQLAlchemy database factory, add a Postgres migration command and Docker runtime, then cut the running system over from the live SQLite DB to Postgres.

**Tech Stack:** Python, SQLAlchemy asyncio, asyncpg, Postgres 16, Docker Compose, pytest

---

### Task 1: Lock the database runtime abstraction

**Files:**
- Modify: `src/skrisk/storage/database.py`
- Test: `tests/test_database_runtime.py`

**Step 1: Write the failing test**

Add tests that prove the session factory normalizes both SQLite and Postgres URLs correctly and keeps the engine reachable on the returned session factory.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_database_runtime.py -q`

**Step 3: Write minimal implementation**

Finish `create_session_factory()` and keep SQLite-only setup guarded behind the SQLite dialect.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_database_runtime.py -q`

**Step 5: Commit**

Commit message: `feat: add generic database runtime factory`

### Task 2: Add the migration CLI

**Files:**
- Create: `src/skrisk/services/db_migrate.py`
- Modify: `src/skrisk/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

Keep the CLI test that asserts `migrate-sqlite-to-postgres` calls the migration service with the configured source path, reset flag, and batch size.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_cli.py::test_migrate_sqlite_to_postgres_cli_runs_service -q`

**Step 3: Write minimal implementation**

Implement the migration service and CLI command, including target-URL validation and operator-facing summary output.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_cli.py::test_migrate_sqlite_to_postgres_cli_runs_service -q`

**Step 5: Commit**

Commit message: `feat: add sqlite to postgres migration command`

### Task 3: Make repository queries portable

**Files:**
- Modify: `src/skrisk/storage/repository.py`
- Test: `tests/test_api.py`
- Test: `tests/test_regressions.py`

**Step 1: Write the failing test**

Use the existing API/repository tests to catch JSON extraction and priority/install sorting regressions.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_api.py tests/test_regressions.py -q`

**Step 3: Write minimal implementation**

Replace SQLite-specific JSON and scalar helper expressions with cross-dialect SQLAlchemy expressions that still work on SQLite.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_api.py tests/test_regressions.py -q`

**Step 5: Commit**

Commit message: `fix: make repository queries portable across sqlite and postgres`

### Task 4: Add the Postgres runtime

**Files:**
- Modify: `pyproject.toml`
- Modify: `docker-compose.yml`
- Modify: `README.md`

**Step 1: Write the failing test**

Use a local runtime smoke test instead of a new unit test:

Run: `SKRISK_DATABASE_URL=postgresql://skrisk:skrisk@127.0.0.1:15432/skrisk ../../.venv/bin/skrisk init-db`

Expected: failure until Postgres service and driver are in place.

**Step 2: Run test to verify it fails**

Run the smoke command before the dependency and Docker changes.

**Step 3: Write minimal implementation**

Add `asyncpg`, add a Postgres Docker service, and document how to initialize and run SK Risk against Postgres.

**Step 4: Run test to verify it passes**

Run:
- `../../.venv/bin/pip install -e .`
- `docker compose up -d postgres`
- `SKRISK_DATABASE_URL=postgresql://skrisk:skrisk@127.0.0.1:15432/skrisk ../../.venv/bin/skrisk init-db`

**Step 5: Commit**

Commit message: `chore: add postgres runtime support`

### Task 5: Verify, migrate, and cut over

**Files:**
- Modify: `README.md`
- Modify: `docs/discussions/2026-03-09-skillsmp-live-rollout.md`

**Step 1: Run the verification slice**

Run:
- `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/test_database_runtime.py tests/test_cli.py tests/test_api.py tests/test_regressions.py -q`
- `PYTHONPATH=src ../../.venv/bin/python -m compileall src`

**Step 2: Stop the live SQLite runtime**

Stop the spool producers and ingester so the source DB is stable for migration.

**Step 3: Migrate the live corpus**

Run:
- `SKRISK_DATABASE_URL=postgresql://skrisk:skrisk@127.0.0.1:15432/skrisk ../../.venv/bin/skrisk migrate-sqlite-to-postgres --source-sqlite-path /home/hdtech/code/skrisk/skrisk.db --reset-target`

**Step 4: Relaunch on Postgres**

Restart the API and analysis runtime with `SKRISK_DATABASE_URL` pointed at Postgres and verify that core commands work.

**Step 5: Commit**

Commit message: `feat: cut over deep analysis runtime to postgres`
