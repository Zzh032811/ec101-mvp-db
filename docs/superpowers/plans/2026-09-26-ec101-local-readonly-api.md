# EC101 Local Read-only API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the fee operations frontend to the real SQLite database through a cross-platform local read-only API.

**Architecture:** Add a Python standard-library API under `api/` that owns the SQLite queries and exposes a stable business-object contract. Replace hardcoded business rows in the Site with API state, while keeping the existing UI controls and export behavior.

**Tech Stack:** Python 3.10+ `http.server`/`sqlite3`, React/TypeScript/Vinext, Python `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-26-ec101-local-readonly-api-design.md`

## Global Constraints

- SQLite remains the source for the local phase; do not write to it from the API.
- API is standard-library-only so macOS and Windows require Python 3.10+ but no dependency install.
- Frontend must not silently fall back to static business data when API requests fail.
- Preserve the eight Chinese business-object labels in the UI.

## Review Focus

- Unknown object names must return 404 rather than becoming SQL identifiers.
- Search, dealer, platform, pagination and detail must be parameterized and bounded.
- Empty API responses and API-offline state must be visible in the UI.
- CSV export must export the currently loaded real rows only.
- The database path must work when the command is launched from either the repository root or `api/`.

### Task 1: Read-only query contract and tests

**Files:**
- Create: `api/server.py`
- Test: `api/tests/test_server.py`

**Interfaces:**
- Produce `query_dataset(db_path: Path, object_name: str, query: Query) -> Dataset` and `get_detail(db_path: Path, object_name: str, record_id: str) -> dict | None`.

- [ ] Write tests for health metadata, eight object names, filtered/paginated orders, and unknown object rejection.
- [ ] Run `python -m unittest api.tests.test_server -v` and confirm the missing module/query functions fail.
- [ ] Implement the whitelist query definitions, parameterized filters, and a `ThreadingHTTPServer` handler for `/health` and `/api/business-data/*`.
- [ ] Run the tests again and confirm all pass against `mvp/ec101_mvp.db`.
- [ ] Commit `feat: add local readonly business data api`.

### Task 2: Cross-platform run documentation

**Files:**
- Create: `api/README.md`
- Modify: `README.md` (create if absent)

- [ ] Document Python version, root-relative and `api/` launch commands, Windows PowerShell environment variables, health check, and read-only boundary.
- [ ] Verify both launch forms resolve the same database by calling `/health`.
- [ ] Commit `docs: document local api workflow`.

### Task 3: Frontend API integration

**Files:**
- Modify: `ec101-fee-platform-v1/app/page.tsx`
- Modify: `ec101-fee-platform-v1/.env.example` if needed

- [ ] Replace the hardcoded `businessTabs` rows with API state while preserving object labels and columns.
- [ ] Add loading, empty and offline states; do not render the old sample rows on request failure.
- [ ] Keep detail and CSV export bound to the loaded rows.
- [ ] Run `npm run build` and `npx oxlint app/page.tsx app/layout.tsx`.
- [ ] Commit `feat: connect business data workspace to local api`.

### Task 4: Local integration verification

**Files:**
- No new production files.

- [ ] Start API from repository root and verify `/health` plus an orders query.
- [ ] Start API from `api/` and verify the same responses.
- [ ] Start frontend with the API URL and verify build plus HTTP 200.
- [ ] Record the production migration seam: replace the SQLite connection in `api/server.py`; keep frontend endpoint contract unchanged.
