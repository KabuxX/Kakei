# Backend Responsibility-Based Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move backend implementation into responsibility-based `api/`, `services/`, `db/`, `cli/`, and `config/` packages without changing its commands, API, or saved data.

**Architecture:** Keep `backend/server.py` and `backend/replace_samples.py` as compatible entrypoints. Move validation and configuration first, persistence second, HTTP handling third, then split the one-time replacement into service, DB, and CLI units and remove temporary forwarding modules.

**Tech Stack:** Python 3.14, FastAPI, SQLite, `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-03-backend-layered-layout-design.md`

## Global Constraints

- Preserve `fastapi run backend/server.py --host 127.0.0.1 --port 8765` and `python backend/replace_samples.py --db ... --backup ...`.
- Preserve all API paths, methods, JSON bodies, status codes, error codes, same-origin/body limits, static serving, and startup trajectory sync.
- Preserve `server.app`, `server.create_app(db_path, front_dir, *, port=8765, timeline_path=...)`, and `replace_samples.replace_samples(db_path, old_path, new_path, timeline_path, backup_path)`.
- Do not change schema, saved transaction/trajectory data, or the real `backend/data/kakei.sqlite3`; run all backend tests and CLI checks with disposable DB and backup paths.
- Full-suite command for every task: `KAKEI_DB_PATH=/private/tmp/kakei-backend-layout-tests.sqlite3 backend/.venv/bin/python -m unittest discover -s backend/tests -v` from the repository root.
- Leave current uncommitted frontend/UI changes alone. Stage only backend files and this plan for task commits.
- Keep `backend/README.md`, `API.md`, requirements, data, and tests in their current locations. Do not add `backend/__init__.py`; add `__init__.py` to the five implementation directories.

## Review Focus

- An entrypoint launched from outside the repository still resolves default data and assets by absolute path: pin with a config-path test in Task 1 and CLI smoke in Tasks 3–4.
- An old SQLite schema migrates without losing transactions or initialization marker: retain the legacy migration tests in Task 2.
- Invalid trajectory JSON at app creation leaves saved trajectory rows intact: retain `test_invalid_fixture_fails_startup_without_erasing_saved_rows` in Task 3.
- Encoded transaction IDs and the fallback API route keep their previous 404/405 behavior: retain `test_encoded_id_and_missing_delete` and `test_api_lifecycle_and_codes` in Task 3.
- Edited sample rows or an existing backup destination stop replacement without writing: retain `test_edited_missing_and_extra_sample_rows_are_rejected` and `test_existing_backup_is_never_overwritten` in Task 4.

---

## File map

- Task 1 creates `backend/config/{__init__,paths,runtime}.py` and `backend/services/{__init__,validation,trajectory_validation}.py`; original root modules forward temporarily.
- Task 2 creates `backend/db/{__init__,schema,store,trajectory_store}.py`; original root storage modules forward temporarily.
- Task 3 creates `backend/api/{__init__,app,http,transactions,trajectory}.py` and narrows `backend/server.py` to the compatible entrypoint.
- Task 4 creates `backend/db/sample_replacement.py`, `backend/services/sample_replacement.py`, `backend/cli/{__init__,replace_samples}.py`, narrows `backend/replace_samples.py`, removes all temporary root forwarders, and updates `backend/README.md`.
- Tests remain under `backend/tests/` and switch to their new owning modules; entrypoint tests continue to use the two root files.

### Task 1: Pure validation and configuration packages

**Files:** Create `backend/config/{__init__,paths,runtime}.py`, `backend/services/{__init__,validation,trajectory_validation}.py`, `backend/tests/test_paths.py`; modify `backend/{runtime,validation,trajectory_validation}.py` into temporary forwarders and `backend/tests/{test_runtime,test_validation,test_trajectory_validation}.py` imports.

**Interfaces:** Produce `config.paths.BACKEND_DIR`, `FRONT_DIST_DIR`, `SAMPLE_DATA_DIR`, `DEFAULT_DB_PATH`, `TIMELINE_PATH` as absolute `Path` values; `config.runtime.require_supported_python(version=None) -> None`; `services.validation.ValidationError` and `normalize_transaction(payload, *, import_mode=False) -> dict`; `services.trajectory_validation.load_timeline(path: Path) -> dict` and `validate_timeline(value: object) -> dict`. Keep old imports working until Task 4.

- [ ] **Step 1: Write failing package tests.** In `test_paths.py`, assert all five constants resolve under this repository regardless of changed working directory. Update validation/runtime/trajectory test imports to the new package names; retain their existing behavior assertions.
- [ ] **Step 2: Verify red.** Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_paths.py' -v`; expect an import failure for `config.paths`. Run full discovery with disposable `KAKEI_DB_PATH`; expect the three changed test modules to fail on the new imports.
- [ ] **Step 3: Move implementation.** Copy existing behavior into the new modules, compute paths from `Path(__file__).resolve()`, and make the old root files import and reexport the existing public names. No validation rule changes.
- [ ] **Step 4: Verify green.** Run `KAKEI_DB_PATH=/private/tmp/kakei-backend-layout-tests.sqlite3 backend/.venv/bin/python -m unittest discover -s backend/tests -v`; expect every test, including `test_paths.py`, to pass.
- [ ] **Step 5: Commit only Task 1 files.** Commit as `Move backend validation and configuration into packages`.

### Task 2: SQLite package

**Files:** Create `backend/db/{__init__,schema,store,trajectory_store}.py`; modify `backend/{schema,store,trajectory_store}.py` into temporary forwarders and `backend/tests/{test_schema,test_store,test_trajectory_store}.py` imports.

**Interfaces:** Produce `db.schema.ensure_schema(connection: sqlite3.Connection) -> None`; `db.store.Store(db_path: Path)`, `AlreadyInitialized`, `NotInitialized`; `db.trajectory_store.replace_trajectory(connection, timeline) -> None`, `read_trajectory_day(connection, date) -> dict | None`. `Store` keeps every existing public method and return shape; it imports pure validators from Task 1.

- [ ] **Step 1: Write failing package tests.** Switch the three storage test files to `db.*` imports; retain the legacy migration, atomic write, ordered-item, and trajectory round-trip assertions.
- [ ] **Step 2: Verify red.** Run full discovery with disposable `KAKEI_DB_PATH`; expect import failures in the three changed test modules for `db.*`.
- [ ] **Step 3: Move implementation.** Place unchanged SQL/schema rules in `db/`; update imports to `services.*` and `db.*`; leave the original root modules as forwarding imports so the current server and CLI remain usable.
- [ ] **Step 4: Verify green.** Run the full backend suite with disposable `KAKEI_DB_PATH`; expect legacy migration and rollback tests to pass and no change to the real DB.
- [ ] **Step 5: Commit only Task 2 files.** Commit as `Move SQLite persistence into db package`.

### Task 3: HTTP package and compatible server entrypoint

**Files:** Create `backend/api/{__init__,app,http,transactions,trajectory}.py`; modify `backend/server.py`, `backend/tests/test_server.py`.

**Interfaces:** Produce `api.app.create_app(db_path: Path, front_dir: Path, *, port: int = 8765, timeline_path: Path = TIMELINE_PATH) -> FastAPI`; `api.http.HTTPFailure`, `json_response(status, value)`, `error_response(status, code, message, field=None)`, `read_json(request, limit)`; `api.transactions.register_transactions(app, store) -> None`; `api.trajectory.register_trajectory(app, store) -> None`. Root `server.py` reexports `create_app` and creates `app` using `config.paths` and `KAKEI_DB_PATH` after the `config.runtime` guard.

- [ ] **Step 1: Write failing ownership/contract test.** Import `api.app.create_app` in `test_server.py`, construct a temporary app, and assert `GET /api/status` and `GET /api/trajectory/2026-09-29` retain their response shapes. Keep existing tests for invalid timeline, body limits, origin rejection, encoded IDs, 404/405, and static assets.
- [ ] **Step 2: Verify red.** Run `test_server.py` with disposable `KAKEI_DB_PATH`; expect import failure for `api.app`.
- [ ] **Step 3: Split HTTP code.** Move JSON/error helpers to `api.http`, transaction routes to `api.transactions`, trajectory route to `api.trajectory`, and app wiring/middleware/fallback/static mount to `api.app`. Preserve registration order and all literals. Narrow `server.py` to the compatible entrypoint.
- [ ] **Step 4: Verify green.** Run the full backend suite with disposable `KAKEI_DB_PATH`. If port 8765 is free, launch the documented FastAPI command against that disposable DB, check `/api/status`, `/api/trajectory/2026-09-29`, and `/`, then stop only that process. If occupied, check FastAPI CLI discovery of `backend/server.py` without binding and verify the three responses through `create_app(..., port=<free port>)` with `TestClient`; never stop an unrelated process.
- [ ] **Step 5: Commit only Task 3 files.** Commit as `Split backend HTTP handling into api package`.

### Task 4: Replacement workflow, CLI, and final cleanup

**Files:** Create `backend/db/sample_replacement.py`, `backend/services/sample_replacement.py`, `backend/cli/{__init__,replace_samples}.py`; modify `backend/replace_samples.py`, `backend/tests/test_replace_samples.py`, `backend/README.md`; remove temporary `backend/{runtime,validation,trajectory_validation,schema,store,trajectory_store}.py` forwarders and update any remaining test imports.

**Interfaces:** Produce `services.sample_replacement.replace_samples(db_path: Path, old_path: Path, new_path: Path, timeline_path: Path, backup_path: Path) -> dict[str, int]`; `db.sample_replacement.replace_sample_rows(db_path: Path, backup_path: Path, old_records: list[dict], new_records: list[dict], timeline: dict) -> dict[str, int]`; `cli.replace_samples.main() -> None`. Root `replace_samples.py` reexports `replace_samples` and `main`, invoking `main()` only when run as a script.

- [ ] **Step 1: Write failing package tests.** Import the service function and CLI `main` from their new modules; retain assertions for malformed JSON, same-date references, edited rows, existing backup, atomic rollback, rerun, and default JSON paths. Add a focused CLI subprocess check from another working directory with explicit temporary DB and backup paths.
- [ ] **Step 2: Verify red.** Run `test_replace_samples.py` with disposable `KAKEI_DB_PATH`; expect import failures for `services.sample_replacement` or `cli.replace_samples`.
- [ ] **Step 3: Split implementation.** Put JSON/content/reference validation and coordination in `services/`; put current-row matching, backup, transactional delete/insert, trajectory replacement and rollback in `db/`; put argparse and JSON output in `cli/`. Keep the root wrapper interface and command behavior. Remove the six temporary root forwarders only after all imports use package modules.
- [ ] **Step 4: Verify green.** Run `test_replace_samples.py`, then the entire backend suite with a disposable DB; run the root CLI against a fresh temporary copy of the old-sample DB and a fresh backup destination. Confirm output `{"deleted":16,"inserted":37,"days":12}`, backup still has 16 transactions, and modified DB has 37 transactions plus 12 trajectory days.
- [ ] **Step 5: Update docs and check boundaries.** Describe the five implementation folders and preserved commands in `backend/README.md`; check `rg` for stale root-module imports in active backend code, `git diff --check`, and the real DB file hash before/after verification.
- [ ] **Step 6: Commit only Task 4 files.** Commit as `Separate sample replacement service DB and CLI`.

## Final verification and handoff

- [ ] Run the full backend suite with disposable `KAKEI_DB_PATH`, repeat the documented server and replacement CLI smoke checks on temporary DBs, and inspect all changed files against the spec.
- [ ] Confirm the actual `backend/data/kakei.sqlite3` was unchanged and the pre-existing frontend work remains unmodified. Request whole-branch review before selecting integration method.
