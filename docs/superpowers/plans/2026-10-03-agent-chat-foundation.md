# Agent Chat Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make saved trajectory data visible and deliver a working local Agent Chat that can read bounded SQL and create or edit transactions only after approval.

**Architecture:** FastAPI keeps the local access boundary; `backend/agent/` runs one LangChain agent with read and proposal tools. SQLite stores conversations and proposals, and the existing domain store validates and atomically applies approved changes. This plan supplies the shared proposal interface used by the receipt and trajectory plans.

**Tech Stack:** Python 3.14, FastAPI, SQLite, LangChain `create_agent`, `langchain-openai`, React 19, Vitest, `unittest`, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-agent-chat-design.md`

## Global Constraints

- Keep the app local and single user, with the existing Host and same-Origin checks; configure `OPENAI_API_KEY` and `KAKEI_AGENT_MODEL` on the server only.
- One agent; tool names are `read_sql`, `edit_transaction`, and `edit_trajectory`. Both edit tools stage commands; only the approval endpoint writes business data.
- A proposal is one atomic confirmation unit; it expires after 24 hours. Approval uses proposal ID and revision, is idempotent, and returns `409 conflict` after relevant source data changes.
- `read_sql` accepts one `SELECT` over public transaction and trajectory views, at most 100 rows, 2 seconds, and 64 KiB; use SQLite `mode=ro` and an authorizer.
- One turn allows at most 8 tool calls and 60 seconds; unavailable model configuration leaves the existing app usable.
- External LangChain/OpenAI tracing is disabled by default; keep receipt bytes, private SQL rows, and API keys out of application logs.
- The trajectory page reads SQLite-backed APIs and supports arbitrary valid dates, global coordinates, and zero or one event without crashing.
- Preserve the existing API error shape, `Cache-Control: no-store`, and the current transaction categories, payment methods, and item-sum rule.
- Implement tests first within each task; commit each independently verified task. Build and commit `front/dist/` for UI changes.

## Review Focus

- A date-only imported transaction edited without changing its date retains `timeEstimated: true`; an explicit time confirmation clears it (Task 1).
- Deleting a sample transaction referenced by a train leg detaches both references and downgrades the leg to inferred in the same transaction (Task 1).
- An empty trajectory day and a one-point day render without a Turf bounding-box failure (Task 3).
- A crafted `SELECT` invoking a disallowed function or reading `receipt_assets` cannot bypass the SQL view boundary (Task 4).
- A successful approval whose HTTP response is lost returns the original result on retry and creates no duplicate transaction (Tasks 6 and 8).

## File map

- `backend/services/validation.py`, `backend/db/store.py`, `backend/api/transactions.py`: transaction replacement and reference-safe deletes.
- `backend/db/trajectory_store.py`, `backend/api/trajectory.py`: date listing and shared connection-level trajectory mutation.
- `front/src/lib/trajectory-model.js`, `front/src/Trajectory.jsx`, `front/src/TrajectoryMap.jsx`, `front/src/lib/api.js`, `front/dev/mock-api.mjs`: general trajectory model and live API read path, including the mock fixture response.
- `backend/agent/contracts.py`, `backend/agent/read_sql.py`, `backend/agent/runtime.py`: typed proposal commands, bounded SQL, LangChain tool loop.
- `backend/db/schema.py`, `backend/db/agent_store.py`, `backend/services/agent_changes.py`: durable threads, proposals, history, validation, and atomic application.
- `backend/api/agent.py`, `backend/api/app.py`: agent HTTP routes, lazy configuration, and fake-runner injection for browser tests.
- `backend/tests/agent_browser_server.py`, `front/playwright.agent.config.cjs`: isolated browser server with temporary SQLite and a fake agent runner.
- `front/src/AgentChat.jsx`, `front/src/lib/agent-api.js`, `front/src/App.jsx`, `front/src/AppShell.jsx`, `front/styles.css`: in-product conversation and approval UI.
- `backend/API.md`, `backend/README.md`, `front/README.md`, `front/dist/`: document and ship the new contracts and built screen.

---

### Task 1: Transaction editing and reference-safe deletion

**Files:** Modify `backend/services/validation.py`, `backend/db/store.py`, `backend/db/trajectory_store.py`, `backend/api/transactions.py`, `backend/api/app.py`, `backend/tests/test_store.py`, `backend/tests/test_server.py`.

**Interfaces:** Produce `Store.update_transaction(transaction_id: str, draft: object, *, confirm_time: bool = False) -> dict`; `PUT /api/transactions/{id}` accepts the create fields plus optional `confirmTime`. Produce `detach_trajectory_references(connection: sqlite3.Connection, ids: set[str]) -> int` for both delete paths.

- [ ] **Step 1: Write failing tests.** Add `test_update_transaction_replaces_items_and_keeps_id`, `test_update_estimated_time_requires_confirmation`, `test_update_invalid_rolls_back`, and `test_delete_detaches_event_and_train_leg`. Assert the same ID survives, item rows match the replacement, an unchanged imported date keeps `timeEstimated`, `confirmTime: true` clears it, invalid item sums leave the old record, and deleting a referenced sample removes `transactionId` and `transportTransactionId` plus `modeHint`.
- [ ] **Step 2: Run the focused tests; expect failure.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_store.py' -v` and `-p 'test_server.py' -v`.
- [ ] **Step 3: Implement the interfaces.** Reuse `normalize_transaction`; preserve or clear `timeEstimated` by the stated rule, replace item rows in `BEGIN IMMEDIATE`, validate any same-day trajectory reference before update, and detach deleted IDs before deleting rows. Return existing `404 not_found`, `400 validation_error`, and body-limit errors through the HTTP adapter.
- [ ] **Step 4: Rerun both focused suites; expect PASS.** Verify `GET /api/transactions/{id}` returns the new record and existing create/delete tests remain green.
- [ ] **Step 5: Commit.** `git add backend/services/validation.py backend/db/store.py backend/db/trajectory_store.py backend/api/transactions.py backend/api/app.py backend/tests/test_store.py backend/tests/test_server.py` then `git commit -m "feat: edit transactions with trajectory-safe deletes"`.

### Task 2: SQLite-backed trajectory date listing

**Files:** Modify `backend/db/store.py`, `backend/api/trajectory.py`, `backend/api/app.py`, `backend/tests/test_server.py`, `backend/API.md`.

**Interfaces:** Produce `Store.list_trajectory_dates() -> list[str]`; `GET /api/trajectory` returns `{ "dates": ["YYYY-MM-DD", ...] }` in ascending order, including before transaction initialization.

- [ ] **Step 1: Write `test_trajectory_dates_reflect_mutations` and `test_trajectory_dates_work_before_initialization`.** Assert a newly created day appears, a deleted day disappears, and the GET has `Cache-Control: no-store`.
- [ ] **Step 2: Run `test_server.py`; expect the new GET tests to fail.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_server.py' -v`.
- [ ] **Step 3: Add the store query and route.** Register the exact path before the `{requested_date}` route; update middleware and unknown-method recognition; document the response in `backend/API.md`.
- [ ] **Step 4: Rerun `test_server.py`; expect PASS.** Confirm the existing day GET contract still passes.
- [ ] **Step 5: Commit.** `git add backend/db/store.py backend/api/trajectory.py backend/api/app.py backend/tests/test_server.py backend/API.md` then `git commit -m "feat: list saved trajectory dates"`.

### Task 3: Live trajectory page and general date model

**Files:** Modify `front/src/lib/trajectory-model.js`, `front/src/lib/api.js`, `front/src/Trajectory.jsx`, `front/src/TrajectoryMap.jsx`, `front/dev/mock-api.mjs`, `front/src/lib/trajectory-model.test.js`, `front/src/Trajectory.test.jsx`, `front/src/TrajectoryMap.test.jsx`, `front/src/App.route.test.jsx`, `front/README.md`, `front/dist/`.

**Interfaces:** Produce `listTrajectoryDates(fetchImpl = fetch) -> Promise<string[]>` and `loadTrajectoryDay(date: string, fetchImpl = fetch) -> Promise<object>`; `Trajectory` consumes saved transactions from `App`, fetches the date list and selected day, and passes a normalized day to `TrajectoryMap`.

- [ ] **Step 1: Write failing model and screen tests.** Add `test_arbitrary_date_and_global_place`, `test_empty_and_single_event_days`, `test_trajectory_fetches_selected_day`, and `test_trajectory_retry_after_api_failure`. Assert 2027-01-04 and a non-Tokyo place work; zero events show an empty state; one event yields one stop and no segments; switching dates issues a fresh GET; missing map data leaves the timeline usable.
- [ ] **Step 2: Run Vitest; expect those tests to fail.** `cd front && npm test -- --run src/lib/trajectory-model.test.js src/Trajectory.test.jsx src/TrajectoryMap.test.jsx src/App.route.test.jsx`.
- [ ] **Step 3: Implement the live read path.** Remove month and coordinate hardcoding, derive bounds from points when there is no leg, and show loading/error/empty states. Add mock GET routes backed by the fixture so `dev:mock` remains usable. Keep the app's transaction state as the join input.
- [ ] **Step 4: Rerun focused tests and build; expect PASS.** `cd front && npm test -- --run src/lib/trajectory-model.test.js src/Trajectory.test.jsx src/TrajectoryMap.test.jsx src/App.route.test.jsx`, then `npm run build`. At desktop and phone widths inspect the first visible dashboard content after navigation; confirm selected period and financial state or an action remain immediately visible.
- [ ] **Step 5: Commit.** Stage the listed source, tests, README, and `front/dist/`; `git commit -m "feat: show saved trajectory data"`.

### Task 4: Bounded read-only SQL tool

**Files:** Create `backend/agent/__init__.py`, `backend/agent/read_sql.py`, `backend/tests/test_agent_read_sql.py`; modify `backend/db/schema.py`.

**Interfaces:** Produce `run_read_sql(db_path: Path, sql: str) -> list[dict]`. Expose views `agent_transactions`, `agent_transaction_items`, `agent_trajectory_days`, `agent_trajectory_events`, `agent_trajectory_legs`, and `agent_trajectory_places` with no receipt BLOB or agent metadata.

- [ ] **Step 1: Write failing tests.** Name `test_select_from_public_views`, `test_reject_write_pragma_attach_and_multiple_statements`, `test_reject_private_table_and_disallowed_function`, and `test_limit_rows_bytes_and_runtime`. Assert a normal date-filtered SELECT returns rows, private reads and `load_extension` fail, 101 rows truncate to 100, and a recursive query is interrupted by the 2-second budget.
- [ ] **Step 2: Run the focused suite; expect failure.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_read_sql.py' -v`.
- [ ] **Step 3: Add views and tool implementation.** Open a URI `mode=ro` connection; use `set_authorizer` to permit reads only through named views and allowlisted built-in functions; execute one statement, use `set_progress_handler`, cap returned rows at 100 and serialized JSON at 64 KiB. Raise `ValidationError("sql", ...)` for rejected queries.
- [ ] **Step 4: Rerun the focused suite and `test_schema.py`; expect PASS.** Include a query containing a semicolon inside a string literal to ensure one-statement handling is parser-based.
- [ ] **Step 5: Commit.** `git add backend/agent backend/db/schema.py backend/tests/test_agent_read_sql.py` then `git commit -m "feat: add bounded agent SQL reader"`.

### Task 5: Durable conversations and versioned proposals

**Files:** Create `backend/agent/contracts.py`, `backend/db/agent_store.py`, `backend/tests/test_agent_store.py`; modify `backend/db/schema.py`.

**Interfaces:** Define `AgentCommand(kind: str, identity: dict[str, str], data: dict)`. Produce `AgentStore(db_path: Path)` with `create_thread() -> dict`, `list_threads() -> list[dict]`, `get_thread(thread_id: str) -> dict | None`, `append_message(thread_id: str, client_message_id: str, role: str, text: str) -> dict`, `create_proposal(thread_id: str, commands: list[AgentCommand], baselines: dict[str, str]) -> dict`, `revise_proposal(proposal_id: str, expected_revision: int, commands: list[AgentCommand]) -> dict`, and `reject_proposal(proposal_id: str) -> dict`.

- [ ] **Step 1: Write failing persistence tests.** `test_thread_messages_survive_reopen`, `test_message_retry_uses_client_id`, `test_revise_increments_revision`, and `test_expiry_and_rejection_remove_pending_only`. Assert proposal states are `pending`, `applied`, `rejected`, or `expired`; expiry is 24 hours; deleting a thread removes its pending proposals and messages but leaves a committed transaction intact.
- [ ] **Step 2: Run `test_agent_store.py`; expect failure.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_store.py' -v`.
- [ ] **Step 3: Add schema and repository.** Store commands and baselines as validated JSON, index `(thread_id, created_at)`, use unique `(thread_id, client_message_id)`, and keep approval result and before/after audit data separate from messages. Never store an API key or raw model debug trace.
- [ ] **Step 4: Rerun `test_agent_store.py` and `test_schema.py`; expect PASS.** Reopen the SQLite file in a new `Store` to verify persistence.
- [ ] **Step 5: Commit.** `git add backend/agent/contracts.py backend/db/agent_store.py backend/db/schema.py backend/tests/test_agent_store.py` then `git commit -m "feat: persist agent conversations and proposals"`.

### Task 6: Atomic approval and conflict checks

**Files:** Create `backend/services/agent_changes.py`, `backend/tests/test_agent_changes.py`; modify `backend/db/store.py`, `backend/db/agent_store.py`.

**Interfaces:** Produce `validate_agent_commands(connection: sqlite3.Connection, commands: list[AgentCommand]) -> dict[str, str]` for target fingerprints and `Store.apply_agent_proposal(proposal_id: str, revision: int) -> dict`. Command kinds are `transaction.create`, `transaction.update`, `trajectory.create`, and `trajectory.update`; transaction identity is `{}` for create or `{id}` for update; trajectory identity is `{kind, date}` for a day, `{kind, date, id}` for an event, and the corresponding existing `TrajectoryCommand` identity fields for a leg or place. `data` contains that command's validated draft.

- [ ] **Step 1: Write failing tests.** `test_unapproved_proposal_never_writes`, `test_transaction_and_day_apply_atomically`, `test_stale_record_or_revision_conflicts`, `test_approval_retry_returns_saved_result`, and `test_bad_second_command_rolls_back_first`. Assert a two-command proposal changes neither target before approval, both afterward, and neither if the second validation fails; a repeated approval returns the same transaction ID.
- [ ] **Step 2: Run `test_agent_changes.py`; expect failure.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_changes.py' -v`.
- [ ] **Step 3: Implement one `BEGIN IMMEDIATE` application path.** Use the same SQLite connection for proposal state, domain changes, audit, and saved approval result; extract connection-level helpers from existing Store methods instead of opening nested transactions. Recheck command targets against canonical JSON SHA-256 fingerprints, apply commands, run cross-reference validation, then commit. Map stale/expired/rejected proposals to explicit conflict errors.
- [ ] **Step 4: Rerun focused tests and `test_store.py`; expect PASS.** Test restart after a successful approval and after a forced rollback.
- [ ] **Step 5: Commit.** `git add backend/services/agent_changes.py backend/db/store.py backend/db/agent_store.py backend/tests/test_agent_changes.py` then `git commit -m "feat: apply approved agent changes atomically"`.

### Task 7: LangChain runtime and agent HTTP contract

**Files:** Create `backend/agent/runtime.py`, `backend/api/agent.py`, `backend/tests/test_agent_runtime.py`, `backend/tests/test_agent_api.py`; modify `backend/api/app.py`, `backend/requirements.txt`, `backend/API.md`, `backend/README.md`.

**Interfaces:** Produce `AgentRunner.run_turn(thread_id: str, messages: list[dict], receipt_id: str | None = None) -> dict` returning `{text, commands}` and `register_agent(app: FastAPI, store: Store, runner_factory: Callable | None = None) -> None`. `POST /api/agent/threads/{id}/messages` accepts `{clientMessageId, text, receiptId?}` and returns `{message, proposal?}`; `PUT /api/agent/proposals/{id}` accepts `{revision, commands}`; `POST .../approve` and `POST .../reject` accept `{revision}`. Add the spec's thread list/get/delete routes and `GET /api/agent/status` for configuration state.

- [ ] **Step 1: Write failing runtime and HTTP tests.** `test_runtime_registers_three_tools_and_stages_edits`, `test_tool_and_time_limits`, `test_missing_model_key_reports_unavailable`, `test_thread_and_proposal_http_lifecycle`, and `test_origin_and_malformed_body_guards`. Patch the model/runner; assert no network call or DB write before approval, then `PUT` revision, approve, reject, 404, 409, and repeated approval behavior through `TestClient`.
- [ ] **Step 2: Run both focused suites; expect failure.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_*.py' -v`.
- [ ] **Step 3: Implement runtime and routes.** Lazily construct `ChatOpenAI` from server environment and `create_agent` with the three named tools; keep tool-collected commands in the turn context. Use `AgentStore` for conversation and `Store.apply_agent_proposal` for approval. Limit tool calls to 8 and turn time to 60 seconds; return actionable 503 for missing config. Add compatible, pinned LangChain packages to requirements and document the exact API and environment variables.
- [ ] **Step 4: Rerun focused and full backend suites; expect PASS.** `backend/.venv/bin/python -m unittest discover -s backend/tests -v` and `git diff --check`.
- [ ] **Step 5: Commit.** Stage the listed files; `git commit -m "feat: expose local agent chat API"`.

### Task 8: Agent Chat screen and end-to-end read/write proof

**Files:** Create `front/src/AgentChat.jsx`, `front/src/lib/agent-api.js`, `front/src/AgentChat.test.jsx`, `backend/tests/agent_browser_server.py`, `front/playwright.agent.config.cjs`; modify `front/src/App.jsx`, `front/src/AppShell.jsx`, `front/src/App.route.test.jsx`, `front/src/AppShell.test.jsx`, `front/styles.css`, `front/tests/e2e/app.spec.cjs`, `front/README.md`, `front/dist/`.

**Interfaces:** `AgentChat` receives `onCommitted: () => Promise<void>` and uses `front/src/lib/agent-api.js` for thread, message, revision, approval, and rejection requests. `#agent` is the third main navigation destination; the first screen exposes status, conversation, pending change card, and composer.

- [ ] **Step 1: Write failing UI tests.** `test_agent_route_and_navigation`, `test_chat_stages_and_edits_transaction`, `test_approval_refreshes_app_data_once`, and `test_pending_and_error_states_keyboard_accessible`. Assert an agent reply can be read, an edited draft increments revision, approval is explicit, Enter does not accidentally approve, and retry after lost approval response does not add a second transaction.
- [ ] **Step 2: Run focused Vitest; expect failure.** `cd front && npm test -- --run src/AgentChat.test.jsx src/App.route.test.jsx src/AppShell.test.jsx`.
- [ ] **Step 3: Implement the in-product screen and API client.** Follow `DESIGN.md` for visual tokens and `MASTER.md` plus `ui-ux-pro-max` for interaction. Show responsive review cards, loading, missing configuration, errors, and keyboard focus. On commit, call transaction refresh and trajectory reload without a full page refresh.
- [ ] **Step 4: Verify.** Run `cd front && npm test`, `npm run build`, then `npm run test:e2e -- --config=playwright.agent.config.cjs tests/e2e/app.spec.cjs`. The config starts `backend/tests/agent_browser_server.py` on a dedicated port with a temporary SQLite file and fake runner, and serves the built `front/dist/`; it never opens the user's database. Inspect Agent Chat and the first visible dashboard content after navigation at desktop and phone widths; confirm selected period and financial state or an action appear immediately on the dashboard. Run `git diff --check`.
- [ ] **Step 5: Commit.** Stage the listed source, tests, docs, and `front/dist/`; `git commit -m "feat: add agent chat screen"`.
