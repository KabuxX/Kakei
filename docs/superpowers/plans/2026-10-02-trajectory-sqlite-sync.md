# Trajectory JSON to SQLite Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store the September trajectory JSON in SQLite at server creation and serve the existing date-scoped trajectory API from the synchronized tables.

**Architecture:** Add relational tables for places, days, ordered events, ordered legs, and ordered via places. Validate the JSON before an atomic, full replacement of trajectory rows. Reconstruct the existing API response from SQLite; keep transaction storage and the frontend fixture flow independent.

**Tech Stack:** Python 3.14, SQLite, FastAPI, `unittest`/`TestClient`.

**Spec:** `docs/superpowers/specs/2026-10-02-trajectory-sqlite-sync-design.md`

## Global Constraints

- Source of truth: `front/src/data/september-timeline.json`; sync on each `create_app`, with no file watcher.
- Sync only trajectory tables, exactly matching the JSON, inside one `BEGIN IMMEDIATE` transaction; transaction tables and initialization state stay untouched.
- `transactionId` and `transportTransactionId` are strings, never foreign keys to `transactions`.
- `GET /api/trajectory/{date}` keeps its URL, response shape, pre-initialization access, `400 invalid_date`, `404 not_found`, `500 database_error`, and `Cache-Control: no-store`.
- The trajectory page and Vite mock API keep their current JSON behavior. Preserve the existing uncommitted edits in `backend/README.md` and `backend/API.md`.
- Use temporary SQLite files for tests. Do not modify `backend/data/kakei.sqlite3` during verification.
- Server tests import the default app, so run them with `KAKEI_DB_PATH` pointing to a fresh temporary file.

## Review Focus

1. Duplicate keys in source JSON must fail loading rather than silently overwrite a place or event. Task 2 tests this.
2. An explicit empty `viaPlaceIds` must survive a DB round trip, while an omitted field stays omitted. Task 3 tests both.
3. A bad place reference, event order, or leg endpoint must stop sync before stored data changes. Tasks 2 and 3 test this.
4. A full resync must remove JSON-deleted trajectory rows without changing transactions or their initialization marker. Task 3 tests this.
5. An insertion failure after deletion has started must roll back to the previous trajectory snapshot. Task 3 tests this.

---

## File Structure

- `backend/schema.py`: create the five trajectory tables on fresh, current, and legacy DBs.
- `backend/trajectory_validation.py` (new): load JSON with duplicate-key detection and validate the timeline contract.
- `backend/trajectory_store.py` (new): replace trajectory rows and assemble one day's API payload from an SQLite connection.
- `backend/store.py`: expose transaction-scoped `sync_trajectory` and `get_trajectory_day` methods through the existing Store connection policy.
- `backend/server.py`: sync at app creation, then read the trajectory endpoint from Store.
- `backend/tests/test_schema.py`, `backend/tests/test_trajectory_validation.py` (new), `backend/tests/test_trajectory_store.py` (new), `backend/tests/test_server.py`: test each boundary with temporary DBs.
- `backend/README.md`, `backend/API.md`: explain startup sync and DB-backed GET without discarding their current uncommitted content.

### Task 1: Create relational trajectory tables

**Files:** Modify `backend/schema.py`; test `backend/tests/test_schema.py`.

**Interfaces:** `ensure_schema(connection: sqlite3.Connection) -> None` retains its signature. It creates `trajectory_places`, `trajectory_days`, `trajectory_events`, `trajectory_legs`, and `trajectory_leg_via_places` before all existing early returns. The `trajectory_legs.has_via_places` column is an integer flag for an explicitly present `viaPlaceIds`, including `[]`.

- [ ] **Step 1: Write failing schema tests.** Add `test_fresh_schema_has_trajectory_tables` asserting the five table names, event `(day_date, position)` uniqueness, leg/via composite keys, and foreign keys. Add `test_legacy_migration_keeps_trajectory_schema_and_transactions` asserting existing transaction and item rows survive migration while all trajectory tables exist.

  ```python
  self.assertTrue({"trajectory_places", "trajectory_days", "trajectory_events", "trajectory_legs", "trajectory_leg_via_places"} <= table_names)
  self.assertEqual(connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1)
  ```

- [ ] **Step 2: Run the schema tests.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_schema.py -v`; expect the new assertions to fail because the tables do not exist.
- [ ] **Step 3: Implement `_create_trajectory_tables(connection: sqlite3.Connection) -> None`.** Add non-null columns and `CHECK` constraints for nonnegative positions, `139.4 <= longitude <= 140.1`, `35.4 <= latitude <= 35.9`, and `has_via_places IN (0, 1)`. Use foreign keys with cascading delete for trajectory children. Call the helper from every `ensure_schema` path without altering the current transaction migration.
- [ ] **Step 4: Re-run the schema tests.** Same command; expect all schema tests to pass.
- [ ] **Step 5: Commit Task 1.** Stage only `backend/schema.py` and `backend/tests/test_schema.py` and commit `Add trajectory relational schema`.

### Task 2: Validate the source JSON

**Files:** Create `backend/trajectory_validation.py` and `backend/tests/test_trajectory_validation.py`.

**Interfaces:** Produce `load_timeline(path: Path) -> dict` and `validate_timeline(value: object) -> dict`. Loading rejects duplicate JSON object keys. Validation returns the input structure after checking it, without dropping optional fields; both functions raise `ValueError` with the invalid field's context.

- [ ] **Step 1: Write failing validation tests.** `test_current_september_fixture_is_valid` asserts 10 places, 30 days, 120 events, and 90 legs. `test_duplicate_json_key_is_rejected` writes a temporary file with a repeated place ID. Table-driven cases reject an unknown field, non-HTTPS URL, out-of-Tokyo/nonfinite coordinates, invalid date/time, duplicate day/event ID, bad `placeId`/`viaPlaceIds`, unordered events, wrong leg endpoints/count, and `train`/`bus` without `transportTransactionId`.

  ```python
  self.assertEqual((len(timeline["places"]), len(timeline["days"])), (10, 30))
  with self.assertRaisesRegex(ValueError, "duplicate"):
      load_timeline(duplicate_key_path)
  ```

- [ ] **Step 2: Run the validation tests.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_trajectory_validation.py -v`; expect import or assertion failure.
- [ ] **Step 3: Implement both functions.** Validate the exact known shape `{places, days}`; accept optional `transactionId`, `transportTransactionId`, `modeHint`, and `viaPlaceIds` with their declared types. Require at least two chronological events and exactly one ordered leg between each adjacent pair. Use the same Tokyo coordinate bounds as `front/src/lib/trajectory-model.js`; do not look up transaction IDs in SQLite.
- [ ] **Step 4: Re-run the validation tests.** Same command; expect all tests to pass.
- [ ] **Step 5: Commit Task 2.** Stage the two new validation files and commit `Validate trajectory timeline before sync`.

### Task 3: Atomically sync and read trajectory rows

**Files:** Create `backend/trajectory_store.py` and `backend/tests/test_trajectory_store.py`; modify `backend/store.py`.

**Interfaces:** Produce `replace_trajectory(connection: sqlite3.Connection, timeline: dict) -> None` and `read_trajectory_day(connection: sqlite3.Connection, date: str) -> dict | None` in `trajectory_store.py`. Add `Store.sync_trajectory(timeline: dict) -> None` and `Store.get_trajectory_day(date: str) -> dict | None`; the Store method validates before opening a write transaction, uses `BEGIN IMMEDIATE`, and calls `replace_trajectory`. `read_trajectory_day` returns `{places, days: [day]}` with only used places and optional JSON fields preserved.

- [ ] **Step 1: Write failing Store tests.** `test_sync_round_trips_all_days` compares every day's read result with `{places: used_places, days: [source_day]}` and checks row counts `10/30/120/90`. `test_optional_via_places_round_trip` covers omitted, empty, and ordered nonempty `viaPlaceIds`. `test_resync_replaces_only_trajectory_data` edits a small fixture, syncs twice, and asserts removed/updated rows plus unchanged transaction rows and `meta.initialized`. `test_invalid_fixture_and_insert_failure_roll_back` asserts both validation failure and a failing SQLite trigger leave the previous trajectory snapshot intact.

  ```python
  self.assertEqual(store.get_trajectory_day("2026-09-01"), expected_day_payload)
  self.assertEqual(store.get_trajectory_day(removed_date), None)
  self.assertEqual(store.list_transactions(), transactions_before_sync)
  ```

- [ ] **Step 2: Run the Store tests.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_trajectory_store.py -v`; expect import or assertion failure.
- [ ] **Step 3: Implement the persistence and read methods.** Delete trajectory rows child first, insert parent first, enumerate JSON array positions, store coordinate pair in lon/lat columns, and persist `has_via_places`. On read, use `ORDER BY position`, add optional keys only when stored, and query only places referenced by the selected day. Keep all writes inside the Store connection transaction.
- [ ] **Step 4: Re-run the Store tests.** Same command; expect all tests to pass.
- [ ] **Step 5: Commit Task 3.** Stage only `backend/trajectory_store.py`, `backend/store.py`, and `backend/tests/test_trajectory_store.py`; commit `Sync trajectory fixture into SQLite`.

### Task 4: Serve the DB snapshot through the existing API

**Files:** Modify `backend/server.py`, `backend/tests/test_server.py`, `backend/README.md`, and `backend/API.md`.

**Interfaces:** Change `create_app(db_path: Path, front_dir: Path, *, port: int = 8765, timeline_path: Path = _timeline_path) -> FastAPI`. It calls `load_timeline(timeline_path)` and `store.sync_trajectory(...)` once during app creation. The trajectory route keeps its signature and date checks, then calls `store.get_trajectory_day(requested_date)`.

- [ ] **Step 1: Write failing server tests.** Update the existing trajectory test to query all 30 dates from a temporary DB and compare each response to the fixture, including the filtered `places`. Add `test_trajectory_get_reads_sqlite`: after app creation, update one synchronized place name directly in the temporary DB and assert GET returns that name. Add tests that a missing day is 404, a malformed date is 400, a simulated SQLite read error is 500, and trajectory GET works before transaction initialization. Add `test_app_creation_resyncs_changed_fixture` with a temporary timeline path and `test_invalid_fixture_fails_startup_without_erasing_saved_rows`.

  ```python
  self.assertEqual(self.request("GET", "/api/trajectory/2026-09-01")[1]["places"]["shibuyaStarbucks"]["name"], "DB-edited")
  self.assertEqual(self.request("GET", "/api/trajectory/2026-10-01")[0], 404)
  ```

- [ ] **Step 2: Run the server tests.** Run `test_db_dir=$(mktemp -d /private/tmp/kakei-trajectory-tests.XXXXXX); KAKEI_DB_PATH="$test_db_dir/kakei.sqlite3" backend/.venv/bin/python -m unittest discover -s backend/tests -p test_server.py -v`; expect the new DB-backed assertions to fail.
- [ ] **Step 3: Change `create_app` and the trajectory route.** Remove the in-memory `timeline` lookup; retain the existing `invalid_date` and `not_found` messages and the initialization middleware exception for `/api/trajectory/`.
- [ ] **Step 4: Update documentation.** Revise `backend/README.md` and `backend/API.md` to state that the JSON is imported at app creation and GET reads SQLite. Preserve their current uncommitted API reference content and examples.
- [ ] **Step 5: Verify the complete backend.** Run `test_db_dir=$(mktemp -d /private/tmp/kakei-trajectory-tests.XXXXXX); KAKEI_DB_PATH="$test_db_dir/kakei.sqlite3" backend/.venv/bin/python -m unittest discover -s backend/tests -v` and `git diff --check`; expect zero failures and no whitespace errors. Inspect `git status --short` so no frontend/mock files or real DB were modified.
- [ ] **Step 6: Commit Task 4.** Stage only the four Task 4 files and commit `Serve synchronized trajectory data from SQLite`.

## Completion Check

Compare the implemented behavior against each section of the spec. Confirm all 30 days round-trip, a second app creation mirrors JSON changes, invalid data does not partially replace rows, transactions remain unchanged, and backend tests pass. Report any remaining warning or limitation separately from the completion claim.
