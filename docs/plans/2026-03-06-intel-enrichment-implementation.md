# Intel Enrichment And Svelte Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Abuse.ch bulk intelligence ingestion, selective VirusTotal enrichment, detailed risk scoring, and a Svelte frontend to SK Risk.

**Architecture:** Keep FastAPI as the backend API and scan orchestration service, extend the SQLAlchemy schema with indicator and feed-history tables, archive immutable raw provider artifacts under `data/archive`, and build a SvelteKit frontend that consumes the JSON API. SK Risk remains the system of record for risk scoring; external feeds and VT increase confidence and context but do not replace local behavioral analysis.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy asyncio, Click, httpx, APScheduler, SQLite bootstrap path, SvelteKit, TypeScript, Vitest, pytest, pytest-asyncio

---

### Task 1: Add Threat Intel Schema And Settings

**Files:**
- Modify: `src/skrisk/config.py`
- Modify: `src/skrisk/storage/models.py`
- Modify: `src/skrisk/storage/repository.py`
- Test: `tests/test_intel_repository.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_record_intel_feed_run_and_indicator_observation(tmp_path: Path) -> None:
    session_factory = create_sqlite_session_factory(f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    await init_db(session_factory)
    repository = SkillRepository(session_factory)

    feed_run_id = await repository.record_intel_feed_run(
        provider="abusech",
        feed_name="urlhaus",
        source_url="https://urlhaus-api.abuse.ch/files/exports/full.json.zip",
        auth_mode="query-key",
        parser_version="v1",
        archive_sha256="abc123",
        archive_size_bytes=10,
    )
    indicator_id = await repository.upsert_indicator(
        indicator_type="domain",
        indicator_value="bad.example",
    )
    await repository.record_indicator_observation(
        indicator_id=indicator_id,
        feed_run_id=feed_run_id,
        source_provider="abusech",
        source_feed="urlhaus",
        classification="malicious",
        confidence_label="high",
        summary="Known payload host",
    )

    detail = await repository.get_indicator_detail("domain", "bad.example")
    assert detail is not None
    assert detail["indicator"]["indicator_value"] == "bad.example"
    assert detail["observations"][0]["classification"] == "malicious"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_intel_repository.py::test_record_intel_feed_run_and_indicator_observation -v`

Expected: FAIL with missing repository methods or missing intel tables.

**Step 3: Write minimal implementation**

- add settings for:
  - `ABUSECH_AUTH_KEY`
  - `VT_APIKEY`
  - `SKRISK_VT_DAILY_BUDGET`
- add new SQLAlchemy models:
  - `IntelFeedRun`
  - `IntelFeedArtifact`
  - `Indicator`
  - `IndicatorObservation`
  - `SkillIndicatorLink`
  - `IndicatorEnrichment`
  - `VTLookupQueueItem`
- add repository methods to create and query those rows

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_intel_repository.py::test_record_intel_feed_run_and_indicator_observation -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_intel_repository.py src/skrisk/config.py src/skrisk/storage/models.py src/skrisk/storage/repository.py
git commit -m "feat: add threat intel persistence model"
```

### Task 2: Implement Abuse.ch Feed Archive And Parsers

**Files:**
- Create: `src/skrisk/collectors/abusech.py`
- Create: `tests/test_abusech_collectors.py`
- Create: `tests/fixtures/urlhaus_full.json.zip`
- Create: `tests/fixtures/threatfox_full.csv.zip`

**Step 1: Write the failing tests**

```python
def test_parse_urlhaus_archive_extracts_urls_domains_and_payload_metadata(tmp_path: Path) -> None:
    archive_path = Path("tests/fixtures/urlhaus_full.json.zip")
    parsed = parse_urlhaus_archive(archive_path)
    assert parsed.provider == "abusech"
    assert any(item.indicator_type == "url" for item in parsed.indicators)
    assert any(item.indicator_type == "domain" for item in parsed.indicators)


def test_write_archive_manifest_records_sha256_and_row_count(tmp_path: Path) -> None:
    destination = tmp_path / "archive"
    result = write_archive_manifest(
        provider="abusech",
        feed_name="threatfox",
        fetched_at=datetime(2026, 3, 6, tzinfo=UTC),
        raw_bytes=b"feed",
        row_count=7,
        destination=destination,
    )
    assert result.manifest_path.exists()
    assert json.loads(result.manifest_path.read_text())["row_count"] == 7
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_abusech_collectors.py -v`

Expected: FAIL with missing module or missing parser functions.

**Step 3: Write minimal implementation**

- add downloader helper that accepts provider URL and auth key
- add archive writer that places immutable files under:
  - `data/archive/intel/abusech/urlhaus/YYYY/MM/DD/HHMMSSZ/`
  - `data/archive/intel/abusech/threatfox/YYYY/MM/DD/HHMMSSZ/`
- add parser functions for:
  - full URLhaus JSON export zip
  - full ThreatFox CSV export zip
- normalize raw rows into indicator records plus provider observation payloads

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_abusech_collectors.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_abusech_collectors.py tests/fixtures/urlhaus_full.json.zip tests/fixtures/threatfox_full.csv.zip src/skrisk/collectors/abusech.py
git commit -m "feat: add abusech feed archiver and parsers"
```

### Task 3: Add Intel Sync Service And CLI Command

**Files:**
- Create: `src/skrisk/services/intel_sync.py`
- Modify: `src/skrisk/cli.py`
- Test: `tests/test_intel_sync.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_sync_abusech_archives_raw_feed_and_persists_indicators(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}",
        archive_root=tmp_path / "archive",
    )
    session_factory = create_sqlite_session_factory(settings.database_url)
    await init_db(session_factory)

    summary = await AbuseChSyncService(session_factory=session_factory, settings=settings).sync_all(
        urlhaus_bytes=load_fixture_bytes("urlhaus_full.json.zip"),
        threatfox_bytes=load_fixture_bytes("threatfox_full.csv.zip"),
    )

    assert summary["feed_runs"] == 2
    assert summary["indicators_upserted"] > 0


def test_sync_intel_cli_runs_abusech_sync(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    result = runner.invoke(cli, ["sync-intel", "--provider", "abusech"])
    assert result.exit_code == 0
    assert "feed runs" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_intel_sync.py tests/test_cli.py -v`

Expected: FAIL with missing service or missing CLI command.

**Step 3: Write minimal implementation**

- add `AbuseChSyncService`
- wire it to:
  - create feed-run rows
  - archive raw downloads
  - parse indicators
  - persist observations
- add CLI command:
  - `skrisk sync-intel --provider abusech`

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_intel_sync.py tests/test_cli.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_intel_sync.py tests/test_cli.py src/skrisk/services/intel_sync.py src/skrisk/cli.py
git commit -m "feat: add abusech sync service"
```

### Task 4: Link Skill Snapshots To Indicators And Expand Scoring

**Files:**
- Modify: `src/skrisk/analysis/analyzer.py`
- Modify: `src/skrisk/analysis/deobfuscator.py`
- Modify: `src/skrisk/services/sync.py`
- Modify: `src/skrisk/services/ingestion.py`
- Modify: `src/skrisk/storage/repository.py`
- Test: `tests/test_indicator_linking.py`
- Test: `tests/test_analysis.py`

**Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_skill_sync_links_extracted_indicators_and_raises_confidence_on_abusech_match(
    tmp_path: Path,
) -> None:
    session_factory = create_sqlite_session_factory(f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    await init_db(session_factory)
    repository = SkillRepository(session_factory)

    indicator_id = await repository.upsert_indicator("domain", "bad.example")
    feed_run_id = await repository.record_intel_feed_run(
        provider="abusech",
        feed_name="urlhaus",
        source_url="https://example.test/urlhaus.zip",
        auth_mode="query-key",
        parser_version="v1",
        archive_sha256="abc123",
        archive_size_bytes=10,
    )
    await repository.record_indicator_observation(
        indicator_id=indicator_id,
        feed_run_id=feed_run_id,
        source_provider="abusech",
        source_feed="urlhaus",
        classification="malicious",
        confidence_label="high",
        summary="Known payload host",
    )

    # ingest skill containing curl|sh to https://bad.example/install.sh
    ...

    detail = await repository.get_skill_detail(
        publisher="evil",
        repo="skillz",
        skill_slug="dropper",
    )
    report = detail["latest_snapshot"]["risk_report"]
    assert report["severity"] == "critical"
    assert report["confidence"] == "confirmed"
    assert report["indicator_matches"][0]["indicator_value"] == "bad.example"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_indicator_linking.py tests/test_analysis.py -v`

Expected: FAIL because indicator linking and confidence scoring are not implemented.

**Step 3: Write minimal implementation**

- expand extracted indicator handling beyond `extracted_domains`
- store `skill_indicator_links`
- update analyzer output to include:
  - `behavior_score`
  - `intel_score`
  - `change_score`
  - `confidence`
  - `indicator_matches`
- preserve current finding evidence while adding the new score model

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_indicator_linking.py tests/test_analysis.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_indicator_linking.py tests/test_analysis.py src/skrisk/analysis/analyzer.py src/skrisk/analysis/deobfuscator.py src/skrisk/services/sync.py src/skrisk/services/ingestion.py src/skrisk/storage/repository.py
git commit -m "feat: correlate skill indicators with threat intel"
```

### Task 5: Add VirusTotal Queueing, Budgeting, And Caching

**Files:**
- Create: `src/skrisk/collectors/virustotal.py`
- Create: `src/skrisk/services/vt_triage.py`
- Modify: `src/skrisk/config.py`
- Modify: `src/skrisk/storage/repository.py`
- Test: `tests/test_virustotal.py`

**Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_vt_triage_respects_daily_budget_and_caches_results(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}",
        archive_root=tmp_path / "archive",
        vt_daily_budget=2,
        vt_api_key="test-key",
    )
    session_factory = create_sqlite_session_factory(settings.database_url)
    await init_db(session_factory)
    repository = SkillRepository(session_factory)

    await repository.enqueue_vt_lookup("url", "https://bad.example/a.sh", priority=100, reason="critical")
    await repository.enqueue_vt_lookup("domain", "bad.example", priority=90, reason="abusech-hit")
    await repository.enqueue_vt_lookup("url", "https://other.example/b.sh", priority=10, reason="medium")

    summary = await VTTriageService(session_factory=session_factory, settings=settings, client=FakeVTClient()).run_once()

    assert summary["lookups_completed"] == 2
    assert summary["lookups_skipped_budget"] == 1
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_virustotal.py -v`

Expected: FAIL with missing VT queueing or missing triage service.

**Step 3: Write minimal implementation**

- add VT API client wrapper
- queue only:
  - critical skill indicators
  - high-risk downloader or exfil indicators
  - newly introduced suspicious hashes and URLs
- archive raw VT responses
- cache summarized enrichment rows to avoid repeated lookups

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_virustotal.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_virustotal.py src/skrisk/collectors/virustotal.py src/skrisk/services/vt_triage.py src/skrisk/config.py src/skrisk/storage/repository.py
git commit -m "feat: add virustotal triage queue"
```

### Task 6: Expand The FastAPI JSON API For Intel Workflows

**Files:**
- Modify: `src/skrisk/api/routes.py`
- Modify: `src/skrisk/storage/repository.py`
- Test: `tests/test_api_intel.py`
- Modify: `tests/test_api.py`

**Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_indicator_detail_api_returns_linked_skills_and_observations(async_client) -> None:
    response = await async_client.get("/api/indicators/domain/bad.example")
    assert response.status_code == 200
    payload = response.json()
    assert payload["indicator"]["indicator_value"] == "bad.example"
    assert payload["observations"]
    assert payload["linked_skills"]


@pytest.mark.asyncio
async def test_vt_queue_api_returns_remaining_budget(async_client) -> None:
    response = await async_client.get("/api/queue/vt")
    assert response.status_code == 200
    assert "daily_budget_remaining" in response.json()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_intel.py tests/test_api.py -v`

Expected: FAIL with missing routes or missing repository query methods.

**Step 3: Write minimal implementation**

- add endpoints:
  - `GET /api/intel/feeds`
  - `GET /api/indicators`
  - `GET /api/indicators/{indicator_type}/{indicator_value}`
  - `GET /api/queue/vt`
  - enrich existing skill detail with linked indicators and confidence data

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_intel.py tests/test_api.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_api_intel.py tests/test_api.py src/skrisk/api/routes.py src/skrisk/storage/repository.py
git commit -m "feat: expose threat intel api surfaces"
```

### Task 7: Replace The Bootstrap Dashboard With A SvelteKit Frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/svelte.config.js`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/routes/+page.svelte`
- Create: `frontend/src/routes/skills/+page.svelte`
- Create: `frontend/src/routes/skills/[publisher]/[repo]/[skill_slug]/+page.svelte`
- Create: `frontend/src/routes/indicators/[indicator_type]/[indicator_value]/+page.svelte`
- Create: `frontend/src/routes/queue/vt/+page.svelte`
- Create: `frontend/src/app.html`
- Create: `frontend/src/app.css`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/routes/+page.test.ts`
- Modify: `README.md`

**Step 1: Write the failing frontend tests**

```ts
import { render, screen } from '@testing-library/svelte';
import OverviewPage from './+page.svelte';

test('renders intel-backed dashboard metrics', () => {
  render(OverviewPage, {
    data: {
      stats: {
        trackedRepos: 10,
        trackedSkills: 120,
        intelBackedFindings: 8,
        pendingVtQueue: 3
      }
    }
  });

  expect(screen.getByText('Intel-Backed Findings')).toBeInTheDocument();
  expect(screen.getByText('8')).toBeInTheDocument();
});
```

**Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- --run`

Expected: FAIL because the SvelteKit frontend does not exist yet.

**Step 3: Write minimal implementation**

- scaffold a SvelteKit app in `frontend/`
- build initial analyst pages:
  - overview
  - skills list
  - skill detail
  - indicator detail
  - VT queue
- use a restrained intelligence-console visual language
- keep FastAPI templates only as temporary fallback until parity exists

**Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- --run`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend README.md
git commit -m "feat: add svelte analyst dashboard"
```

### Task 8: Wire End-To-End Flow, Docs, And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/discussions/2026-03-06-kickoff.md`
- Modify: `docs/plans/2026-03-06-intel-enrichment-design.md`
- Test: `tests/test_regressions.py`

**Step 1: Write the failing end-to-end regression test**

```python
@pytest.mark.asyncio
async def test_end_to_end_sync_links_skill_to_abusech_and_vt_queue(tmp_path: Path) -> None:
    # seed fixture feeds
    # ingest suspicious skill repo
    # assert indicator appears on skill detail
    # assert abusech match is present
    # assert vt queue contains the high-priority IOC
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_regressions.py::test_end_to_end_sync_links_skill_to_abusech_and_vt_queue -v`

Expected: FAIL until the individual pieces are integrated.

**Step 3: Write minimal implementation**

- connect the intel sync, skill sync, scoring, queueing, and API layers
- update docs and operator instructions:
  - required env vars
  - new CLI commands
  - VT budget expectations
  - archive retention model
  - Merklemap deferred-to-phase-2 note

**Step 4: Run full verification**

Run: `pytest -q`
Expected: PASS

Run: `python -m compileall src`
Expected: PASS

Run: `cd frontend && npm test -- --run`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md docs/discussions/2026-03-06-kickoff.md docs/plans/2026-03-06-intel-enrichment-design.md tests/test_regressions.py
git commit -m "docs: finalize intel enrichment rollout"
```
