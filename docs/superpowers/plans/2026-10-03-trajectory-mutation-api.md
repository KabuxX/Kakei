# Trajectory Mutation API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add exactly three persistent mutation APIs for trajectory days, events, legs, and places.

**Architecture:** Keep SQLite as the trajectory source of truth and seed the fixed JSON once. Parse one command envelope for `POST`, `PUT`, and `DELETE /api/trajectory`; apply it to a timeline snapshot inside `BEGIN IMMEDIATE`, validate the resulting graph, and atomically replace trajectory rows. A whole-snapshot rewrite is acceptable for the current local 12-day dataset and reuses the existing reader and writer.

**Tech Stack:** Python 3.14, FastAPI, SQLite, `unittest`, FastAPI `TestClient`.

**Spec:** `docs/superpowers/specs/2026-10-03-trajectory-mutation-api-design.md`

## Global Constraints

- Add exactly `POST`, `PUT`, and `DELETE /api/trajectory`; keep `GET /api/trajectory/{date}` shape unchanged.
- Support `day`, `event`, `leg`, and `place` with the spec's `kind`/identity/`data` envelope; `PUT` replaces content and `DELETE` accepts no `data`.
- Permit incomplete saved days while preserving strict validation of the initial JSON sample.
- Persist API edits across restart, including deletion of every day; do not change React or the Vite mock API.
- Keep local Host and same-Origin enforcement, the 1 MiB mutation body limit, and trajectory access before transaction initialization.
- Return `201`/`200` with the canonical command envelope, `204` without a body, and the spec's `400`/`404`/`409` errors.

## Review Focus

- An API edit followed by app creation with a different fixture must retain the edited DB rows (Task 1 test).
- An explicit empty `viaPlaceIds` must remain present after mutation and GET (Task 3 test).
- A place referenced only as a leg's via point must resist deletion (Task 3 test).
- Adding an event between connected events must reject the operation without moving existing events (Task 3 test).
- A malformed or over-limit mutation body must leave SQLite unchanged (Task 4 test).

## File map

- `backend/services/trajectory_validation.py`: share sample and mutable graph validation while keeping sample completeness strict.
- `backend/services/trajectory_mutation.py`: parse the HTTP-independent mutation envelope into `TrajectoryCommand`.
- `backend/db/trajectory_store.py`: reconstruct a full timeline and write partial-day leg positions correctly.
- `backend/db/store.py`: seed once, apply mutations in one transaction, and expose not-found/conflict failures.
- `backend/db/sample_replacement.py`: reject sample replacement after API edits.
- `backend/api/trajectory.py`, `backend/api/app.py`: expose the three routes, exception mapping, and initialization exemption.
- `backend/API.md`, `backend/README.md`: document the new contract and one-time seed behavior.

---

### Task 1: One-time seed and protection of edited data

**Files:** Modify `backend/db/store.py`, `backend/db/sample_replacement.py`, `backend/api/app.py`, `backend/tests/test_server.py`, `backend/tests/test_replace_samples.py`.

**Interfaces:** Produce `Store.seed_trajectory_once(load_seed: Callable[[], dict]) -> None`. Use `meta` keys `trajectory_seeded` and `trajectory_modified`, both with value `1`. Later mutation work sets the latter key in the same transaction.

- [ ] **Step 1: Write failing tests.** Replace `test_app_creation_resyncs_changed_fixture` with `test_app_creation_preserves_seeded_trajectory`; after a second `create_app` with changed JSON, assert GET still returns the original place name and existing dates. Change `test_invalid_fixture_fails_startup_without_erasing_saved_rows` so invalid JSON fails a fresh seed but is not read after seeding. Add `test_existing_unmarked_trajectory_is_preserved`, `test_seeded_empty_trajectory_stays_empty`, and `test_replace_samples_rejects_api_modified_trajectory` with these assertions:
  ```python
  self.assertEqual(reopened_get["places"]["shibuyaStarbucks"]["name"], original_name)
  self.assertEqual(reopened_missing_day.status_code, 404)
  with self.assertRaisesRegex(ValueError, "edited"):
      replace_samples(self.db, OLD, NEW, TIMELINE, self.backup)
  self.assertEqual(saved_rows_after, saved_rows_before)
  ```
- [ ] **Step 2: Run the affected suites and see those cases fail.** Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_server.py' -v` and the same command with `test_replace_samples.py`; expect the new persistence and guard assertions to fail.
- [ ] **Step 3: Implement the seed interface.** In `Store.seed_trajectory_once`, hold `BEGIN IMMEDIATE`; if marked, return without calling `load_seed`; if unmarked and any trajectory row exists, preserve it; otherwise call `load_seed`, validate, and insert. Mark seeded before commit. Make `create_app` pass a loader. Check `trajectory_modified` before sample replacement changes rows, and mark seeded after successful replacement.
- [ ] **Step 4: Run both suites again.** Expect PASS, including the unchanged initial-sample GET contract.
- [ ] **Step 5: Commit.** `git add backend/db/store.py backend/db/sample_replacement.py backend/api/app.py backend/tests/test_server.py backend/tests/test_replace_samples.py` then `git commit -m "feat: seed trajectory only once"`.

### Task 2: Command parsing and mutable graph validation

**Files:** Create `backend/services/trajectory_mutation.py`, `backend/tests/test_trajectory_mutation.py`; modify `backend/services/trajectory_validation.py`, `backend/tests/test_trajectory_validation.py`.

**Interfaces:** Produce `TrajectoryCommand(kind: str, date: str | None, id: str | None, from_event_id: str | None, to_event_id: str | None, data: dict | None)` and `parse_trajectory_command(payload: object, method: str) -> TrajectoryCommand`. Extend `validate_timeline(value: object, *, require_complete: bool = True) -> dict`; the default keeps fixture behavior.

- [ ] **Step 1: Write failing tests.** Name the parser cases `test_parse_each_kind`, `test_reject_unknown_and_wrong_data`, and `test_put_retains_optional_field_omission`. Name the graph cases `test_mutable_empty_and_partial_days` and `test_mutable_rejects_nonadjacent_or_duplicate_leg`. Pin them with:
  ```python
  command = parse_trajectory_command({"kind": "day", "date": "2026-10-03", "data": {"events": [], "legs": []}}, "POST")
  self.assertEqual((command.kind, command.date), ("day", "2026-10-03"))
  self.assertEqual(validate_timeline(partial, require_complete=False), partial)
  with self.assertRaises(ValueError): validate_timeline(partial)
  with self.assertRaises(ValidationError): parse_trajectory_command({"kind": "place", "id": "p", "data": []}, "PUT")
  ```
- [ ] **Step 2: Run those tests and see them fail.** Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_trajectory_mutation.py' -v` and likewise `test_trajectory_validation.py`.
- [ ] **Step 3: Implement parsing and validation.** Parse exact identity keys per kind and method; use `ValidationError` with field `trajectory` for invalid envelopes. Reuse current field, date, time, place, mode, and transaction-ID checks. For mutable days, allow zero events and a subset of adjacent legs, ordered by their starting event; reject duplicate pairs. Keep the strict default's event and leg counts.
- [ ] **Step 4: Run both suites.** Expect PASS and no regression in fixed sample validation.
- [ ] **Step 5: Commit.** `git add backend/services/trajectory_mutation.py backend/services/trajectory_validation.py backend/tests/test_trajectory_mutation.py backend/tests/test_trajectory_validation.py` then `git commit -m "feat: validate trajectory mutation commands"`.

### Task 3: Atomic mutation of all four trajectory kinds

**Files:** Modify `backend/db/trajectory_store.py`, `backend/db/store.py`, `backend/tests/test_trajectory_store.py`.

**Interfaces:** Produce `read_trajectory_timeline(connection: sqlite3.Connection) -> dict` and `Store.mutate_trajectory(command: TrajectoryCommand, action: str) -> dict | None`, where `action` is `create`, `update`, or `delete`. Produce `TrajectoryNotFound` and `TrajectoryConflict` exceptions. `create`/`update` return the canonical command envelope; `delete` returns `None`.

- [ ] **Step 1: Write failing store tests.** Name the cases `test_mutate_each_kind_round_trip`, `test_day_replacement_and_empty_day`, `test_optional_via_list_round_trip`, `test_put_omission_removes_optional_field`, `test_referenced_place_or_event_cannot_be_deleted`, `test_event_insert_or_reorder_conflict_rolls_back`, and `test_duplicate_event_id_across_days`. Assert through `get_trajectory_day` and the mutation response:
  ```python
  self.assertEqual(saved_day["days"][0]["legs"][0]["viaPlaceIds"], [])
  self.assertEqual(created_day["data"]["events"], sorted_events)
  with self.assertRaises(TrajectoryConflict): store.mutate_trajectory(command, "delete")
  self.assertEqual(store.get_trajectory_day(date), before)
  ```
  Cover a place referenced only as a via point, an event referenced by a leg, insertion between connected events, time editing that changes adjacency, and a globally duplicate event ID.
- [ ] **Step 2: Run `test_trajectory_store.py` and see the new cases fail.** Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_trajectory_store.py' -v`.
- [ ] **Step 3: Implement timeline mutation.** Read all places including unused ones and all days in event order. In `BEGIN IMMEDIATE`, check target existence and dependencies, mutate the snapshot, sort events by time, validate with `require_complete=False`, replace rows, and set `trajectory_modified=1`. Store leg `position` as the index of its starting event so missing legs remain identifiable. Convert invalid input to `ValidationError`; preserve `TrajectoryConflict` for duplicate identities and operations that invalidate existing edges.
- [ ] **Step 4: Run `test_trajectory_store.py` and `test_schema.py`.** Expect PASS, including rollback and foreign-key behavior.
- [ ] **Step 5: Commit.** `git add backend/db/trajectory_store.py backend/db/store.py backend/tests/test_trajectory_store.py` then `git commit -m "feat: persist trajectory mutations"`.

### Task 4: HTTP contract, integration tests, and documentation

**Files:** Modify `backend/api/trajectory.py`, `backend/api/app.py`, `backend/API.md`, `backend/README.md`, `backend/tests/test_server.py`.

**Interfaces:** Consume `parse_trajectory_command` and `Store.mutate_trajectory`. Register exactly three methods at `/api/trajectory`; keep the existing date GET and its validation.

- [ ] **Step 1: Write failing HTTP tests.** Name the cases `test_trajectory_mutation_api_round_trip_uninitialized`, `test_trajectory_mutation_api_errors`, and `test_trajectory_mutation_body_guards`. Exercise all three methods and assert:
  ```python
  self.assertEqual(post_status, 201)
  self.assertEqual(put_payload["kind"], "event")
  self.assertEqual(delete_status, 204)
  self.assertEqual((invalid_status, invalid_payload["error"]["code"]), (400, "invalid_json"))
  self.assertEqual((large_status, large_payload["error"]["code"]), (413, "body_too_large"))
  self.assertEqual(store.get_trajectory_day(date), before_rejected_request)
  ```
  Also pin missing target/day to `404`, duplicate or referenced target to `409`, bad Origin to `403`, and confirm GET after successful writes.
- [ ] **Step 2: Run `test_server.py` and see the new cases fail.** Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_server.py' -v`.
- [ ] **Step 3: Implement the HTTP adapters.** Use `read_json(request, 1024 * 1024)`, parse the command, and call the store. Map `TrajectoryNotFound` to `404 not_found` and `TrajectoryConflict` to `409 conflict`; reuse `ValidationError` handling. Add `Cache-Control: no-store` to the `204`. Exempt exact `/api/trajectory` from initialization middleware and recognize it in unknown-method handling.
- [ ] **Step 4: Document and verify.** Update `backend/API.md` with one request per kind, response/error rules, partial-day GET, and 1 MiB limit. Update `backend/README.md` for one-time seed and edited-data replacement guard. Run `backend/.venv/bin/python -m unittest discover -s backend/tests -v` and `git diff --check`; expect all tests to pass and no whitespace errors.
- [ ] **Step 5: Commit.** `git add backend/api/trajectory.py backend/api/app.py backend/API.md backend/README.md backend/tests/test_server.py` then `git commit -m "feat: expose trajectory mutation APIs"`.
