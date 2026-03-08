# Skills Page Performance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add install reach to the homepage critical-skills table and make the `/skills` page fast by moving it to server-side pagination, filtering, and sorting.

**Architecture:** Keep the homepage on the compact skill-list endpoint, add a paginated skills endpoint for the Svelte registry page, and replace full-corpus browser loading with URL-driven server queries. Push list filtering and ordering into SQL and keep heavyweight fields on the detail endpoint only.

**Tech Stack:** FastAPI, SQLAlchemy async, SQLite, SvelteKit, Vitest, pytest

---

### Task 1: Add failing tests for the new API shape

**Files:**
- Modify: `tests/test_api.py`
- Modify: `frontend/src/lib/api.test.ts`

**Step 1: Write failing backend tests**

- Add a test for `GET /api/skills/page` that expects:
  - `items`
  - `total`
  - `page`
  - `page_size`
  - `has_next`
  - `has_previous`

**Step 2: Run targeted backend test**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api.py -q`

**Step 3: Write failing frontend API test**

- Add a test for the new paginated fetch helper used by the Svelte `/skills` route.

**Step 4: Run targeted frontend API test**

Run: `cd frontend && npm test -- --run src/lib/api.test.ts`

### Task 2: Add failing UI tests

**Files:**
- Modify: `frontend/src/routes/home.page.test.ts`
- Modify: `frontend/src/routes/skills/page.test.ts`

**Step 1: Write failing homepage test**

- Assert the homepage critical-skills table renders a `Weekly Installs` column and row values.

**Step 2: Write failing skills-page test**

- Assert the `/skills` page renders server-driven pagination state rather than using the full in-memory corpus.

**Step 3: Run targeted frontend route tests**

Run: `cd frontend && npm test -- --run src/routes/home.page.test.ts src/routes/skills/page.test.ts`

### Task 3: Implement optimized backend list queries

**Files:**
- Modify: `src/skrisk/storage/repository.py`
- Modify: `src/skrisk/api/routes.py`
- Modify: `src/skrisk/storage/database.py`

**Step 1: Build a paginated repository method**

- Add a server-side paginated list method that:
  - filters in SQL
  - sorts in SQL
  - limits in SQL
  - returns summary rows plus total count

**Step 2: Add the paginated API route**

- Add `GET /api/skills/page`.
- Keep `GET /api/skills` for compact list consumers.

**Step 3: Add needed SQLite indexes**

- Add additive index creation for registry-observation and list-query access paths.

**Step 4: Run targeted backend tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api.py -q`

### Task 4: Move the Svelte skills page to server-side queries

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/routes/skills/+page.ts`
- Modify: `frontend/src/routes/skills/+page.svelte`

**Step 1: Add paginated client helper**

- Add a frontend API helper for `/api/skills/page`.

**Step 2: Read filters from URL params**

- Update the route loader to map URL params to the server query.

**Step 3: Update the page UI**

- Render the current page of items.
- Render simple pagination controls.
- Keep filters URL-driven and server-side.

**Step 4: Run targeted frontend tests**

Run: `cd frontend && npm test -- --run src/lib/api.test.ts src/routes/skills/page.test.ts`

### Task 5: Add the homepage installs column

**Files:**
- Modify: `frontend/src/routes/+page.svelte`
- Modify: `frontend/src/app.css`

**Step 1: Add the column**

- Render `Weekly Installs` in the critical-skills table.

**Step 2: Rebalance the panel widths**

- Give the critical-skills table more width and reduce the feed/VT panel width.

**Step 3: Run targeted homepage test**

Run: `cd frontend && npm test -- --run src/routes/home.page.test.ts`

### Task 6: Verify the full change

**Files:**
- No new files

**Step 1: Run backend tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q`

**Step 2: Run frontend tests**

Run: `cd frontend && npm test -- --run`

**Step 3: Run Svelte checks**

Run: `cd frontend && npm run check`

**Step 4: Run backend compile check**

Run: `PYTHONPATH=src .venv/bin/python -m compileall src`

**Step 5: Commit**

```bash
git add docs/plans/2026-03-08-skills-page-performance-design.md \
        docs/plans/2026-03-08-skills-page-performance-implementation.md \
        src/skrisk/storage/repository.py \
        src/skrisk/api/routes.py \
        src/skrisk/storage/database.py \
        frontend/src/lib/api.ts \
        frontend/src/lib/types.ts \
        frontend/src/routes/+page.svelte \
        frontend/src/routes/skills/+page.ts \
        frontend/src/routes/skills/+page.svelte \
        frontend/src/app.css \
        frontend/src/lib/api.test.ts \
        frontend/src/routes/home.page.test.ts \
        frontend/src/routes/skills/page.test.ts \
        tests/test_api.py
git commit -m "feat: speed up skills page and surface install reach"
```
