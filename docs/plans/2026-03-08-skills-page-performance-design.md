# Skills Page Performance Design

**Date:** 2026-03-08

## Goal

Speed up the Svelte `/skills` page by moving filtering, sorting, and pagination to the server, while also adding weekly installs to the homepage critical-skills table.

## Problem

- The homepage critical-skills table does not show install reach, which makes it harder to judge impact quickly.
- The `/skills` page currently loads the entire registry into the browser through `/api/skills?limit=0&sort=priority`.
- The backend list path loads all skill rows and all registry observations before it filters or limits results.
- The current payload is far larger than the page needs.

## Approved Design

### Homepage

- Add a `Weekly Installs` column to the homepage critical-skills table.
- Rebalance the homepage two-column panel layout so the critical-skills table is wider and the feed/VT panel is narrower.

### Skills Page

- Move `/skills` to server-side pagination.
- Drive filters and sort through URL query params so the page is shareable and reload-safe.
- Keep a dedicated server-side endpoint that returns:
  - current page items
  - total matching count
  - current page number
  - page size
  - has-prev / has-next flags
- Default to the first page with a bounded page size instead of loading the full corpus.

### API Strategy

- Keep `GET /api/skills` for compact list consumers like the homepage.
- Add a paginated `GET /api/skills/page` endpoint for the Svelte `/skills` route.
- Reuse one optimized repository query path under both endpoints.

### Backend Query Strategy

- Push severity, install filters, search, ordering, offset, and limit into SQL.
- Join only the latest snapshot per skill for list views.
- Compute previous-install and peak-install telemetry in SQL subqueries instead of loading all observations for all skills into Python.
- Return summary fields only for list pages; keep heavy detail data on the skill detail endpoint.
- Add SQLite indexes needed by the paginated list query, especially on registry observations by `(skill_id, observed_at, id)`.

### Testing

- Add backend API coverage for paginated `/api/skills/page`.
- Add frontend API coverage for paginated loading.
- Add homepage UI coverage for the new `Weekly Installs` column.
- Update `/skills` page tests to cover URL-driven server-side pagination state.

