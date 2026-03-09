# SkillsMP Multi-Registry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `skillsmp.com` as a first-class SK Risk registry, preserve cross-registry provenance without duplicate scans, combine installs across registries, and stand up required `OpenSearch` and `Neo4j` services in Docker.

**Architecture:** Generalize the current single-registry model into canonical skill records plus source-specific provenance rows. Add a `skillsmp` collector that combines API enrichment with browser-capable discovery, then project canonical state into `OpenSearch` and `Neo4j` while keeping SQLite as the system of record.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, SQLite, pytest, SvelteKit, Vitest, Docker Compose, OpenSearch, Neo4j, Scrapling

---

### Task 1: Add Source-Aware Registry Schema

**Files:**
- Modify: `src/skrisk/storage/models.py`
- Modify: `src/skrisk/storage/repository.py`
- Modify: `src/skrisk/storage/database.py`
- Test: `tests/test_registry_observations.py`
- Create: `tests/test_registry_sources.py`

**Step 1: Write the failing test**

Create `tests/test_registry_sources.py` proving:

- source rows can be recorded for `skills.sh` and `skillsmp`
- one canonical skill can have multiple source entries
- source entries preserve source URL, source-native ID, installs, rank, and last-seen timestamps
- canonical total installs are the sum of current installs across source entries

Example:

```python
async def test_repository_tracks_multiple_source_entries_and_combined_installs(tmp_path):
    source_ids = {
        "skills.sh": await repo.upsert_registry_source("skills.sh", "https://skills.sh"),
        "skillsmp": await repo.upsert_registry_source("skillsmp", "https://skillsmp.com"),
    }
    skill_id = await repo.upsert_skill(...)
    await repo.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_ids["skills.sh"],
        source_url="https://skills.sh/a/b/c",
        source_native_id=None,
        weekly_installs=120,
        registry_rank=8,
        observed_at=observed_at,
        raw_payload={"source": "skills.sh"},
    )
    await repo.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_ids["skillsmp"],
        source_url="https://skillsmp.com/skills/example",
        source_native_id="example-id",
        weekly_installs=55,
        registry_rank=None,
        observed_at=observed_at,
        raw_payload={"source": "skillsmp"},
    )
    detail = await repo.get_skill_detail("a", "b", "c")
    assert detail["current_total_installs"] == 175
    assert {entry["source_name"] for entry in detail["source_entries"]} == {"skills.sh", "skillsmp"}
```

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_registry_sources.py -q
```

Expected: FAIL because source-aware tables and repository methods do not exist.

**Step 3: Write minimal implementation**

Update `src/skrisk/storage/models.py`:

- add `RegistrySource`
- add `SkillSourceEntry`
- add source-aware fields on `Skill`:
  - `current_total_installs`
  - `current_total_installs_observed_at`
- add relationships from canonical skills to source entries

Update `src/skrisk/storage/repository.py`:

- add:
  - `upsert_registry_source(...)`
  - `upsert_skill_source_entry(...)`
  - helpers to recompute canonical total installs
  - source-aware detail/list serialization

Update `src/skrisk/storage/database.py`:

- register the new models
- add indexes supporting source lookups and source-aware install aggregation

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_registry_sources.py tests/test_registry_observations.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/skrisk/storage/models.py src/skrisk/storage/repository.py src/skrisk/storage/database.py tests/test_registry_sources.py tests/test_registry_observations.py
git commit -m "feat: add multi-registry provenance schema"
```

### Task 2: Generalize Registry Sync To Canonical Skills Plus Source Entries

**Files:**
- Modify: `src/skrisk/collectors/skills_sh.py`
- Modify: `src/skrisk/services/sync.py`
- Modify: `src/skrisk/cli.py`
- Modify: `tests/test_collectors.py`
- Modify: `tests/test_sync_service.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing test**

Extend sync/collector tests to prove:

- sync operates on a generic registry entry shape instead of a `skills.sh`-only type
- `seed-registry` records source provenance rows instead of flattening source data into canonical fields
- `scan-due` scans each canonical skill once even when two source entries point to it
- `skills.sh` remains functional after the refactor

Example:

```python
assert summary["skills_seen"] == 1
detail = await repo.get_skill_detail("vercel-labs", "skills", "find-skills")
assert detail["source_count"] == 2
assert detail["current_total_installs"] == 900
```

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_collectors.py tests/test_sync_service.py tests/test_cli.py -q
```

Expected: FAIL because sync currently assumes a single `skills.sh` source and a single registry URL per skill.

**Step 3: Write minimal implementation**

Update `src/skrisk/collectors/skills_sh.py`:

- rename/generalize `SkillSitemapEntry` into a source-agnostic registry entry type or add a new generic dataclass used by sync
- keep `skills.sh` parsing logic intact, but have it emit source-aware entries

Update `src/skrisk/services/sync.py`:

- thread `source` and `view` through registry sync flows
- record/update `RegistrySource` and `SkillSourceEntry`
- dedupe canonical skills by normalized repo + discovered skill identity
- ensure scan attribution uses the canonical skill, not each source row

Update `src/skrisk/cli.py`:

- keep `seed-registry`, `sync-registry`, and `scan-due` working with the refactored sync service

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_collectors.py tests/test_sync_service.py tests/test_cli.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/skrisk/collectors/skills_sh.py src/skrisk/services/sync.py src/skrisk/cli.py tests/test_collectors.py tests/test_sync_service.py tests/test_cli.py
git commit -m "refactor: make registry sync source-aware"
```

### Task 3: Add `skillsmp` API Collector And Source Normalization

**Files:**
- Create: `src/skrisk/collectors/skillsmp.py`
- Modify: `src/skrisk/config.py`
- Modify: `src/skrisk/cli.py`
- Create: `tests/test_skillsmp_collector.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing test**

Create `tests/test_skillsmp_collector.py` proving:

- bearer auth headers are constructed correctly
- `search` responses normalize into source entries with:
  - source-native ID
  - source URL
  - GitHub URL
  - author
  - stars
  - updated timestamp
- locale-prefixed or variant URLs normalize to a canonical `skillsmp` source URL
- invalid wildcard-style enumeration is rejected cleanly

Example:

```python
entry = page.entries[0]
assert entry.source == "skillsmp"
assert entry.source_native_id == "openclaw-openclaw-extensions-open-prose-skills-prose-skill-md"
assert entry.source_url == "https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md"
assert entry.repo_url == "https://github.com/openclaw/openclaw/tree/main/extensions/open-prose/skills/prose"
```

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_skillsmp_collector.py -q
```

Expected: FAIL because the collector does not exist.

**Step 3: Write minimal implementation**

Create `src/skrisk/collectors/skillsmp.py` with:

- a `SkillsMpClient`
- read-only search helpers
- response normalization into source-aware registry entries
- URL canonicalization helpers
- rate-limit aware request handling

Update `src/skrisk/config.py`:

- add `skillsmp_api_key`
- add `skillsmp_base_url`

Update `src/skrisk/cli.py`:

- add a source-seeding command or extend the registry seed path so `skillsmp` can be fetched intentionally

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_skillsmp_collector.py tests/test_cli.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/skrisk/collectors/skillsmp.py src/skrisk/config.py src/skrisk/cli.py tests/test_skillsmp_collector.py tests/test_cli.py
git commit -m "feat: add skillsmp api collector"
```

### Task 4: Add Scrapling Discovery, HTML Archiving, And Source Ingestion

**Files:**
- Modify: `pyproject.toml`
- Create: `src/skrisk/services/skillsmp_discovery.py`
- Modify: `src/skrisk/cli.py`
- Modify: `src/skrisk/storage/repository.py`
- Create: `tests/test_skillsmp_discovery.py`
- Modify: `tests/test_sync_service.py`

**Step 1: Write the failing test**

Create `tests/test_skillsmp_discovery.py` proving:

- discovery results from category/detail pages normalize into `skillsmp` source entries
- raw HTML artifacts are archived under `archive_root`
- source entries discovered by Scrapling can be merged with API-enriched metadata without duplicating canonical skills

Example:

```python
results = await service.normalize_discovery_results(...)
assert results[0].source == "skillsmp"
assert results[0].source_url.startswith("https://skillsmp.com/skills/")
assert archive_manifest["provider"] == "skillsmp"
```

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_skillsmp_discovery.py -q
```

Expected: FAIL because discovery service and archiving do not exist.

**Step 3: Write minimal implementation**

Update `pyproject.toml`:

- add `scrapling` dependency

Create `src/skrisk/services/skillsmp_discovery.py`:

- browser-capable category/detail discovery service
- HTML archiving helpers under `archive_root`
- normalization into source-aware registry entries

Update `src/skrisk/cli.py`:

- add a `sync-skillsmp-discovery` command or equivalent discovery entrypoint

Update `src/skrisk/storage/repository.py` only as needed for source-entry merge/upsert paths.

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_skillsmp_discovery.py tests/test_sync_service.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml src/skrisk/services/skillsmp_discovery.py src/skrisk/cli.py src/skrisk/storage/repository.py tests/test_skillsmp_discovery.py tests/test_sync_service.py
git commit -m "feat: add skillsmp discovery and archiving"
```

### Task 5: Expose Multi-Registry Provenance In API And Svelte UI

**Files:**
- Modify: `src/skrisk/api/routes.py`
- Modify: `src/skrisk/storage/repository.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/routes/+page.svelte`
- Modify: `frontend/src/routes/skills/+page.svelte`
- Modify: `frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/+page.svelte`
- Modify: `frontend/src/routes/home.page.test.ts`
- Modify: `frontend/src/routes/skills/page.test.ts`
- Modify: `frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/page.test.ts`

**Step 1: Write the failing test**

Add API and frontend assertions proving:

- list rows expose `sources`, `source_count`, `current_total_installs`, and per-source install breakdowns
- homepage critical-skills rows display registry badges
- skill detail displays a source provenance panel with both `skills.sh` and `skillsmp` when applicable
- canonical skills appear once in list views even if present in both registries

Example:

```ts
expect(row.sources).toEqual(['skills.sh', 'skillsmp']);
expect(screen.getByText('skillsmp')).toBeInTheDocument();
expect(screen.getByText('175')).toBeInTheDocument();
```

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_api.py -q
cd frontend && npm test -- --run
```

Expected: FAIL because the API and Svelte views do not surface multi-source provenance yet.

**Step 3: Write minimal implementation**

Update `src/skrisk/storage/repository.py` and `src/skrisk/api/routes.py`:

- include source-entry data and canonical total installs in list/detail payloads

Update Svelte routes:

- add registry badges/columns
- show combined installs in the main tables
- add per-registry breakdown on the detail page

Keep the design dense and analyst-oriented rather than decorative.

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_api.py -q
cd frontend && npm test -- --run
cd frontend && npm run check
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/skrisk/api/routes.py src/skrisk/storage/repository.py frontend/src/lib/api.ts frontend/src/lib/types.ts frontend/src/routes/+page.svelte frontend/src/routes/skills/+page.svelte frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/+page.svelte frontend/src/routes/home.page.test.ts frontend/src/routes/skills/page.test.ts frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/page.test.ts
git commit -m "feat: show multi-registry provenance in analyst ui"
```

### Task 6: Add Dockerized OpenSearch And Neo4j Projection

**Files:**
- Create: `docker-compose.yml`
- Create: `src/skrisk/services/search_index.py`
- Create: `src/skrisk/services/graph_project.py`
- Modify: `src/skrisk/config.py`
- Modify: `src/skrisk/cli.py`
- Create: `tests/test_search_index.py`
- Create: `tests/test_graph_project.py`
- Modify: `README.md`

**Step 1: Write the failing test**

Create projection tests proving:

- canonical skills and source entries serialize into OpenSearch-ready documents
- canonical relationships serialize into Neo4j-ready node/edge payloads
- startup/config validation fails clearly when required services are enabled but unavailable

Example:

```python
doc = build_skill_document(skill_detail)
assert doc["sources"] == ["skills.sh", "skillsmp"]
graph = build_skill_graph_payload(skill_detail)
assert any(edge["type"] == "SEEN_IN" for edge in graph["edges"])
```

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_search_index.py tests/test_graph_project.py -q
```

Expected: FAIL because the projector services do not exist.

**Step 3: Write minimal implementation**

Create:

- `docker-compose.yml` with required `opensearch` and `neo4j` services
- `src/skrisk/services/search_index.py`
- `src/skrisk/services/graph_project.py`

Update `src/skrisk/config.py` and `src/skrisk/cli.py`:

- add service URLs and required/optional flags
- add projector/indexing commands

Update `README.md`:

- document Docker startup, required env vars, and operational commands

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest tests/test_search_index.py tests/test_graph_project.py -q
docker compose config
```

Expected: PASS and valid compose config

**Step 5: Commit**

```bash
git add docker-compose.yml src/skrisk/services/search_index.py src/skrisk/services/graph_project.py src/skrisk/config.py src/skrisk/cli.py tests/test_search_index.py tests/test_graph_project.py README.md
git commit -m "feat: add search and graph runtime services"
```

### Task 7: Full Verification And Documentation Sweep

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-08-skillsmp-multiregistry-design.md`
- Modify: `docs/discussions/2026-03-08-skillsmp-integration.md`

**Step 1: Write the failing test**

No new failing test for this task. Use it to verify that the full plan has actually landed and the docs match reality.

**Step 2: Run full verification**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest -q
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m compileall src
cd frontend && npm test -- --run
cd frontend && npm run check
cd frontend && npm run build
docker compose config
```

Expected: PASS

**Step 3: Write minimal documentation updates**

Update docs to reflect:

- `skillsmp` source support
- multi-registry install policy
- canonical dedupe behavior
- Dockerized `OpenSearch` and `Neo4j`
- Scrapling discovery role and operational commands

**Step 4: Re-run verification**

Run:

```bash
PYTHONPATH=src /home/hdtech/code/skrisk/.venv/bin/python -m pytest -q
cd frontend && npm run build
```

Expected: PASS

**Step 5: Commit**

```bash
git add README.md docs/plans/2026-03-08-skillsmp-multiregistry-design.md docs/discussions/2026-03-08-skillsmp-integration.md
git commit -m "docs: document skillsmp multi-registry integration"
```
