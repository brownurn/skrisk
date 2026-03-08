# Install Impact Telemetry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Capture `skills.sh` weekly installs as historical telemetry, attach install footprint to scans, expose impact and priority in the API, and display installs prominently in the Svelte analyst UI.

**Architecture:** Extend the existing registry sync pipeline so it preserves `skills.sh` install metadata instead of discarding it. Persist the latest install value on `skills`, append immutable install observations for every registry crawl and scan attribution, derive impact and priority in a small shared scoring helper, and surface the result through the existing FastAPI and Svelte interfaces.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, SQLite, pytest, SvelteKit, Vitest

---

### Task 1: Parse Weekly Installs From `skills.sh`

**Files:**
- Modify: `src/skrisk/collectors/skills_sh.py`
- Modify: `src/skrisk/services/sync.py`
- Test: `tests/test_collectors.py`

**Step 1: Write the failing test**

Add assertions to `tests/test_collectors.py::test_parse_directory_page_extracts_registry_entries` and `tests/test_collectors.py::test_skills_sh_client_fetch_snapshot_pages_through_directory_api` proving:

- `SkillSitemapEntry` carries `weekly_installs`
- parsed entries preserve `installs` from the raw directory payload
- entries with missing installs normalize to `0` or `None` consistently

Example assertion:

```python
assert page.entries[0].weekly_installs == 1234
assert snapshot.sitemap_entries[1].weekly_installs == 80
```

**Step 2: Run test to verify it fails**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_collectors.py::test_parse_directory_page_extracts_registry_entries tests/test_collectors.py::test_skills_sh_client_fetch_snapshot_pages_through_directory_api -q
```

Expected: FAIL because `SkillSitemapEntry` does not expose `weekly_installs`.

**Step 3: Write minimal implementation**

Update `src/skrisk/collectors/skills_sh.py`:

- add `weekly_installs: int | None = None` to `SkillSitemapEntry`
- parse `raw_skill.get("installs")`
- carry the value through `parse_directory_page()`

Update `src/skrisk/services/sync.py` only as needed so existing code constructing `SkillSitemapEntry` includes the new field where required.

**Step 4: Run test to verify it passes**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_collectors.py::test_parse_directory_page_extracts_registry_entries tests/test_collectors.py::test_skills_sh_client_fetch_snapshot_pages_through_directory_api -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_collectors.py src/skrisk/collectors/skills_sh.py src/skrisk/services/sync.py
git commit -m "feat: parse weekly installs from skills directory"
```

### Task 2: Add Install Telemetry Schema And Repository Helpers

**Files:**
- Modify: `src/skrisk/storage/models.py`
- Modify: `src/skrisk/storage/repository.py`
- Modify: `src/skrisk/storage/database.py`
- Test: `tests/test_intel_repository.py`
- Create: `tests/test_registry_observations.py`

**Step 1: Write the failing test**

Create `tests/test_registry_observations.py` covering:

- `skills` stores `current_weekly_installs`
- a `registry_sync_run` can be recorded
- a `skill_registry_observation` row can be appended
- the latest skill metrics update without deleting historical rows

Example test shape:

```python
async def test_repository_records_latest_installs_and_history(tmp_path):
    repo = SkillRepository(session_factory)
    run_id = await repo.record_registry_sync_run(...)
    skill_id = await repo.upsert_skill(...)
    await repo.record_skill_registry_observation(
        skill_id=skill_id,
        registry_sync_run_id=run_id,
        repo_snapshot_id=None,
        observed_at=observed_at,
        weekly_installs=1200,
        registry_rank=4,
        observation_kind="directory_fetch",
        raw_payload={"installs": 1200},
    )
    detail = await repo.get_skill_detail("tul-sh", "skills", "agent-tools")
    assert detail["current_weekly_installs"] == 1200
```

**Step 2: Run test to verify it fails**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_registry_observations.py -q
```

Expected: FAIL because the schema and repository methods do not exist.

**Step 3: Write minimal implementation**

Update `src/skrisk/storage/models.py`:

- add fields on `Skill`:
  - `current_weekly_installs`
  - `current_weekly_installs_observed_at`
  - `current_registry_rank`
  - `current_registry_sync_run_id`
- add `RegistrySyncRun`
- add `SkillRegistryObservation`

Update `src/skrisk/storage/repository.py`:

- add methods:
  - `record_registry_sync_run(...)`
  - `record_skill_registry_observation(...)`
  - `list_skill_registry_observations(...)`
  - helpers to update current skill install fields

Update `src/skrisk/storage/database.py` only if initialization helpers need to be aware of the new models.

**Step 4: Run test to verify it passes**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_registry_observations.py tests/test_intel_repository.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/skrisk/storage/models.py src/skrisk/storage/repository.py src/skrisk/storage/database.py tests/test_registry_observations.py tests/test_intel_repository.py
git commit -m "feat: persist install telemetry observations"
```

### Task 3: Add Impact And Priority Scoring

**Files:**
- Create: `src/skrisk/analysis/impact.py`
- Modify: `src/skrisk/analysis/__init__.py`
- Test: `tests/test_analysis.py`
- Create: `tests/test_impact.py`

**Step 1: Write the failing test**

Create `tests/test_impact.py` proving:

- install buckets map to the approved impact ladder
- rising installs increase impact
- falling installs reduce impact
- risk severity stays separate from impact
- priority increases when a risky skill also has high installs

Example:

```python
def test_priority_increases_for_high_risk_high_install_skill():
    scores = compute_priority_metrics(
        risk_score=82,
        severity="high",
        confidence="likely",
        current_weekly_installs=12000,
        previous_weekly_installs=4000,
        peak_weekly_installs=12000,
    )
    assert scores.impact_score >= 80
    assert scores.priority_score > 82
```

**Step 2: Run test to verify it fails**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_impact.py -q
```

Expected: FAIL because the scoring helper does not exist.

**Step 3: Write minimal implementation**

Create `src/skrisk/analysis/impact.py` with pure functions:

- `compute_impact_score(...)`
- `compute_priority_score(...)`
- `compute_install_delta(...)`
- `bucket_weekly_installs(...)`

Keep the formulas simple and deterministic so they are easy to unit test.

**Step 4: Run test to verify it passes**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_impact.py tests/test_analysis.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/skrisk/analysis/impact.py src/skrisk/analysis/__init__.py tests/test_impact.py tests/test_analysis.py
git commit -m "feat: add install impact and priority scoring"
```

### Task 4: Record Registry Runs, Install History, And Scan Attribution

**Files:**
- Modify: `src/skrisk/services/sync.py`
- Modify: `src/skrisk/cli.py`
- Modify: `src/skrisk/storage/repository.py`
- Test: `tests/test_sync_service.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_regressions.py`

**Step 1: Write the failing test**

Extend sync tests to prove:

- `seed-registry` creates one `registry_sync_run`
- every skill row writes a `directory_fetch` observation
- `scan-due` writes `scan_attribution` observations tied to `repo_snapshot_id`
- `scan-due` still uses tracked DB entries and does not fetch the full registry again

Example assertion:

```python
observations = await repository.list_skill_registry_observations(skill_id)
assert {item["observation_kind"] for item in observations} == {"directory_fetch", "scan_attribution"}
assert any(item["repo_snapshot_id"] == repo_snapshot_id for item in observations)
```

**Step 2: Run test to verify it fails**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_sync_service.py tests/test_cli.py tests/test_regressions.py -q
```

Expected: FAIL because sync does not yet record install telemetry runs and observations.

**Step 3: Write minimal implementation**

Update `src/skrisk/services/sync.py`:

- create a `registry_sync_run` when directory pages are processed
- persist `directory_fetch` observations during metadata seeding
- use the freshest known install value when writing `scan_attribution`
- ensure repeated scans append new observations without rewriting history

Update `src/skrisk/cli.py` only if command summaries should report install telemetry counts.

**Step 4: Run test to verify it passes**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_sync_service.py tests/test_cli.py tests/test_regressions.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/skrisk/services/sync.py src/skrisk/cli.py src/skrisk/storage/repository.py tests/test_sync_service.py tests/test_cli.py tests/test_regressions.py
git commit -m "feat: record install history during sync and scans"
```

### Task 5: Expose Installs, Impact, And Priority In The API

**Files:**
- Modify: `src/skrisk/api/routes.py`
- Modify: `src/skrisk/storage/repository.py`
- Modify: `src/skrisk/api/dashboard.py`
- Test: `tests/test_api.py`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing test**

Extend `tests/test_api.py` so `/api/skills` and `/api/skills/{publisher}/{repo}/{skill_slug}` expose:

- `current_weekly_installs`
- `current_weekly_installs_observed_at`
- `peak_weekly_installs`
- `weekly_installs_delta`
- `impact_score`
- `priority_score`
- install history on detail responses

Also add filter/sort tests such as:

```python
response = await client.get("/api/skills?limit=0&min_weekly_installs=1000&sort=installs")
assert [item["skill_slug"] for item in response.json()] == ["popular-skill", "mid-skill"]
```

**Step 2: Run test to verify it fails**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_api.py tests/test_dashboard.py -q
```

Expected: FAIL because the API and repository projections do not include install telemetry.

**Step 3: Write minimal implementation**

Update `src/skrisk/storage/repository.py`:

- enrich list/detail queries with current installs, peak installs, delta, impact, and priority
- add list filtering and sorting by installs and priority

Update `src/skrisk/api/routes.py`:

- accept query params:
  - `min_weekly_installs`
  - `max_weekly_installs`
  - `sort`

Update `src/skrisk/api/dashboard.py` only if overview payloads or server-rendered fallbacks need the same fields.

**Step 4: Run test to verify it passes**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_api.py tests/test_dashboard.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/skrisk/api/routes.py src/skrisk/storage/repository.py src/skrisk/api/dashboard.py tests/test_api.py tests/test_dashboard.py
git commit -m "feat: expose install impact telemetry via api"
```

### Task 6: Add Install And Priority UX To The Svelte Frontend

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/presenters.ts`
- Modify: `frontend/src/routes/skills/+page.ts`
- Modify: `frontend/src/routes/skills/+page.svelte`
- Modify: `frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/+page.ts`
- Modify: `frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/+page.svelte`
- Test: `frontend/src/lib/api.test.ts`
- Test: `frontend/src/routes/skills/page.test.ts`
- Test: `frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/page.test.ts`

**Step 1: Write the failing test**

Add frontend tests proving:

- the skills table renders a `Weekly Installs` column
- install values are formatted and sortable
- the list defaults to priority-first ordering
- the skill detail page shows latest installs, peak installs, and install history

Example assertion:

```ts
expect(screen.getByRole('columnheader', { name: /weekly installs/i })).toBeInTheDocument();
expect(screen.getByText('12.0k')).toBeInTheDocument();
expect(screen.getByText(/priority/i)).toBeInTheDocument();
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- --run src/lib/api.test.ts src/routes/skills/page.test.ts src/routes/skills/[publisher]/[repo]/[skill_slug]/page.test.ts
```

Expected: FAIL because the frontend types, loaders, and views do not yet support install telemetry.

**Step 3: Write minimal implementation**

Update `frontend/src/lib/types.ts` and `frontend/src/lib/api.ts` to normalize the new API fields.

Update `frontend/src/lib/presenters.ts` with helpers such as:

- `formatWeeklyInstalls`
- `installTrendTone`
- `priorityTone`

Update the Svelte routes:

- `/skills` table adds `Weekly Installs` and `Priority`
- `/skills` filters include install buckets
- skill detail page shows latest installs, peak installs, delta, and recent install observations

Keep installs as a dedicated column, not part of the severity badge.

**Step 4: Run test to verify it passes**

Run:

```bash
cd frontend && npm test -- --run src/lib/api.test.ts src/routes/skills/page.test.ts src/routes/skills/[publisher]/[repo]/[skill_slug]/page.test.ts
cd frontend && npm run check
cd frontend && npm run build
```

Expected:

- targeted Vitest suite passes
- Svelte check reports `0 errors`
- build succeeds

**Step 5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/lib/presenters.ts frontend/src/routes/skills/+page.ts frontend/src/routes/skills/+page.svelte frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/+page.ts frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/+page.svelte frontend/src/lib/api.test.ts frontend/src/routes/skills/page.test.ts frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/page.test.ts
git commit -m "feat: show install impact telemetry in frontend"
```

### Task 7: Update Docs And Run Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/risk-and-intel-model.md`
- Modify: `docs/architecture/skills-sh-discovery-and-crawl.md`

**Step 1: Write the failing doc/test checklist**

Before editing docs, list the user-visible facts that must be true:

- README mentions weekly install tracking
- architecture docs explain risk vs impact vs priority
- crawl docs explain that directory fetches now preserve `installs`

**Step 2: Update documentation**

Add:

- storage model for install observations
- impact scoring ladder
- frontend `Weekly Installs` column behavior
- note that install history starts from the first install-aware sync forward

**Step 3: Run full backend verification**

Run:

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/python -m compileall src
```

Expected:

- full pytest suite passes
- compileall succeeds

**Step 4: Run full frontend verification**

Run:

```bash
cd frontend && npm test -- --run
cd frontend && npm run check
cd frontend && npm run build
```

Expected:

- frontend tests pass
- `npm run check` reports `0 errors`
- production build succeeds

**Step 5: Commit**

```bash
git add README.md docs/architecture/risk-and-intel-model.md docs/architecture/skills-sh-discovery-and-crawl.md
git commit -m "docs: describe install impact telemetry"
```
