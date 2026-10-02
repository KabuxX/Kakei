# September Sample Deduplication and DB Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove repeated cross-date September sample transactions, keep only supported trajectory days, and replace the local SQLite old samples with the cleaned data.

**Architecture:** Treat the two frontend JSON files as the source data. Rewrite them together so all retained timeline references resolve to retained transactions. Add a one-time backend command that backs up SQLite, checks its current sample state, and atomically replaces sample transactions and trajectory rows; do not change API contracts or startup transaction behavior.

**Tech Stack:** React 19, Vite/Vitest, Node.js, Python 3, SQLite, FastAPI unittest tests.

**Spec:** `docs/superpowers/specs/2026-10-02-september-sample-dedup-db-replacement-design.md`

## Global Constraints

- Preserve `front/src/data/old-samples.json` byte-for-byte and preserve non-sample DB transactions.
- Same-content key contains `type`, `title`, `category`, `amount`, `merchant`, `paymentMethod`, and ordered `items`; exclude only `id` and `date`. Retain the latest date's record without changing its ID.
- Expected cleaned data: 37 transactions; 12 trajectory days, 2026-09-19 through 2026-09-30; 36 events, 24 legs, 10 referenced places, and two fare-backed train legs.
- Keep only transaction-backed events and unlinked station events required as endpoints of retained fare-backed legs. Reconnect gaps as inferred movement without via places.
- Keep Vite mock API and backend API behavior unchanged. Keep existing backend startup JSON-to-trajectory sync; do not add startup transaction replacement.
- The trajectory and overview are in-product screens. Follow `DESIGN.md` for visuals, `design-system/household-budget-app/MASTER.md` for general UX, and `pages/dashboard.md` for overview content order.
- The real `backend/data/kakei.sqlite3` is ignored by Git. Update it only after tests, whole-branch review, and local integration; create a separate SQLite backup first.
- Set `KAKEI_DB_PATH=/private/tmp/kakei-september-dedup-test.sqlite3` for backend test commands because importing `backend/server.py` creates an app and otherwise touches the real DB. For final TestClient verification, set it to a temporary DB before importing the server module.

## Review Focus

1. Malformed or duplicate-key transaction JSON must stop before DB changes; Task 2 tests it.
2. Edited or unexpected `sample-` rows must stop replacement without touching user data; Task 2 tests it.
3. A SQL failure after deleting old rows must roll back both transaction and trajectory changes; Task 2 tests it with a failing trigger.
4. Removing a fare must never leave a train leg or dangling timeline reference; Task 1 tests it.
5. A backup-path collision must fail before DB writes; Task 2 tests it.

---

### Task 1: Clean the two fixtures and adapt trajectory display

**Files:**
- Modify: `front/src/data/september-transactions.json`, `front/src/data/september-timeline.json`, `front/src/Trajectory.jsx`
- Test: `front/src/lib/sample-data.test.js`, `front/src/lib/trajectory-model.test.js`, `front/src/Trajectory.test.jsx`, `front/src/Trajectory.failure.test.jsx`, `front/src/TrajectoryMap.test.jsx`, `front/src/App.route.test.jsx`, `front/src/dev-environments.test.js`, `front/tests/e2e/app.spec.cjs`
- Test: `backend/tests/test_trajectory_validation.py`, `backend/tests/test_trajectory_store.py`, `backend/tests/test_server.py`
- Modify: `front/README.md`, `backend/README.md`, `backend/API.md`

**Interfaces:**
- Consumes: existing `createSampleTransactions()`, `buildTrajectoryDays(transactions, timeline)`, `load_timeline(path)`, and the current JSON schemas.
- Produces: cleaned JSON at the same paths and schemas; `Trajectory` still selects dates from `buildTrajectoryDays` and displays only available dates.

- [ ] **Step 1: Write failing fixture tests.** Assert 37 transactions, unique same-content keys, unchanged `sample-0`, exactly 12 dates from `2026-09-19` to `2026-09-30`, 36 events, 24 legs, and two train legs whose fare IDs exist on the same date. Assert every event/leg/point reference resolves and removed fares leave no train legs.
- [ ] **Step 2: Run those focused tests and confirm RED.** Run `cd front && npm test -- src/lib/sample-data.test.js src/lib/trajectory-model.test.js`; expected failure is the old 103 transactions and 30 dates.
- [ ] **Step 3: Rewrite both JSON files.** Select one latest-date transaction for each spec key, preserving order and unchanged record values. Retain events referencing selected transactions plus unlinked endpoints of selected fare-backed legs; keep days with at least two selected transaction events. For each remaining adjacent event pair, retain a valid original direct leg or create a leg with only `fromEventId` and `toEventId`; prune unused places. Expected totals are in Global Constraints.
- [ ] **Step 4: Run the focused fixture tests and confirm GREEN.** Run the same command as Step 2; expected pass with all date-matched references.
- [ ] **Step 5: Write failing display and environment tests.** Assert first selected date is `2026-09-19`, last is `2026-09-30`, controls say `前の記録日`/`次の記録日`, selection has only 12 options, and mock GET returns the exact 37-record JSON while POST/DELETE behavior remains unchanged. Update fixture-date assumptions in the route, map, failure, and end-to-end tests.
- [ ] **Step 6: Run display/environment tests and confirm RED.** Run `cd front && npm test -- src/Trajectory.test.jsx src/TrajectoryMap.test.jsx src/dev-environments.test.js`; expected failure is obsolete date or button assumptions.
- [ ] **Step 7: Update `Trajectory.jsx`.** Change only the date control labels to `前の記録日` and `次の記録日`.
- [ ] **Step 8: Update fixture-dependent backend assertions.** Use retained sample dates and counts: 10 places, 12 days, 36 events, 24 legs. Exercise `GET /api/trajectory/2026-09-29` as present and a removed date as 404.
- [ ] **Step 9: Update runtime docs.** Revise `front/README.md`, `backend/README.md`, and `backend/API.md` to describe 37 transactions and 12 trajectory days with current API examples.
- [ ] **Step 10: Run the full checks.** Run `cd front && npm test`, `cd front && npm run build`, `cd front && npm run test:e2e -- tests/e2e/app.spec.cjs`, and `KAKEI_DB_PATH=/private/tmp/kakei-september-dedup-test.sqlite3 /Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -v`; expected all pass.
- [ ] **Step 11: Check and commit.** Run `git diff --check`; expected clean. Commit only Task 1 files as `Clean repeated September samples and trajectories`.

### Task 2: Implement guarded, atomic local DB replacement

**Files:**
- Create: `backend/replace_samples.py`
- Test: `backend/tests/test_replace_samples.py`
- Modify: `backend/README.md` (one-time command and backup behavior)

**Interfaces:**
- Consumes: `normalize_transaction(record, import_mode=True)`, `load_timeline(path)`, `validate_timeline(timeline)`, `ensure_schema(connection)`, `Store._insert(connection, record)`, and `replace_trajectory(connection, timeline)`.
- Produces: `replace_samples(db_path: Path, old_path: Path, new_path: Path, timeline_path: Path, backup_path: Path) -> dict[str, int]`; CLI takes `--db` and `--backup` with repository paths for both JSON inputs as defaults.

- [ ] **Step 1: Write failing migration tests.** Build temporary SQLite DBs from `old-samples.json`; assert the returned counts `{"deleted": 16, "inserted": 37, "days": 12}`, full new transaction/trajectory data, a preserved UUID user transaction, and a byte-for-byte source old JSON. Assert a second run with a new backup path is safe. Assert edited/extra sample rows, malformed or duplicate-key JSON, cross-date references, an existing backup path, and a trigger-induced insertion failure leave DB contents unchanged.
- [ ] **Step 2: Run migration tests and confirm RED.** Run `KAKEI_DB_PATH=/private/tmp/kakei-september-dedup-test.sqlite3 /Users/spco/Kakei/backend/.venv/bin/python -m unittest backend.tests.test_replace_samples -v`; expected failure is the missing `replace_samples` module/function.
- [ ] **Step 3: Implement `replace_samples(...)` and CLI.** Validate complete new records without silently dropping fields/items, enforce unique IDs/content keys and same-date timeline references, and load the timeline with existing validation. Require an existing DB and a free backup path; use SQLite backup API before writes. In one `BEGIN IMMEDIATE` transaction (started by `ensure_schema`), compare all current `sample-` rows with normalized old or new records, delete old sample IDs, insert new records/items, replace trajectory rows, and commit. Roll back on every failure; allow an already-new run to sync the same trajectory safely. Do not alter API routes.
- [ ] **Step 4: Run focused migration tests and confirm GREEN.** Run the command from Step 2; expected all pass.
- [ ] **Step 5: Run full backend unittests.** Run `KAKEI_DB_PATH=/private/tmp/kakei-september-dedup-test.sqlite3 /Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -v`; expected pass.
- [ ] **Step 6: Document the one-time command.** Add the exact CLI invocation and backup behavior to `backend/README.md`.
- [ ] **Step 7: Check and commit.** Run `git diff --check`; expected clean. Commit Task 2 files as `Add guarded September sample DB replacement`.

### Task 3: Review, integrate, and replace the actual local DB

**Files:**
- Update outside Git: `backend/data/kakei.sqlite3`
- Create outside Git: a unique backup alongside that DB

**Interfaces:**
- Consumes: the reviewed `backend/replace_samples.py` CLI and the committed cleaned JSON files.
- Produces: initialized local DB with the 37 cleaned transactions and 12 trajectory days; prior DB saved separately.

- [ ] **Step 1: Verify the branch before integration.** Run full frontend tests/build, backend unittests, and `git diff --check`; expected pass.
- [ ] **Step 2: Request whole-branch review.** Resolve Critical/Important findings and rerun affected checks.
- [ ] **Step 3: Integrate locally.** Follow `superpowers:finishing-a-development-branch` and the user's chosen integration method. Keep unrelated worktrees and stashes intact.
- [ ] **Step 4: Apply the one-time command on main.** Run `backend/.venv/bin/python backend/replace_samples.py --db backend/data/kakei.sqlite3 --backup backend/data/kakei.sqlite3.before-september-dedup.bak` from the repository root; fail if the backup path already exists. Expected output: deleted 16, inserted 37, trajectory days 12.
- [ ] **Step 5: Verify the real DB read-only.** Query the real DB in SQLite read-only mode: count 37 new sample transaction IDs, 12 trajectory days, and zero old-only IDs. Test `GET /api/transactions` and `GET /api/trajectory/2026-09-29` through an in-process TestClient against a temporary copy of the migrated DB, comparing with the JSON sources. Confirm the backup exists and no tracked file changed during DB replacement.
- [ ] **Step 6: Inspect the rendered overview at desktop and phone widths.** After app navigation, the selected month and financial summary or primary recording action must be visible first. If browser preview is unavailable, inspect rendered structure and report that limit.
