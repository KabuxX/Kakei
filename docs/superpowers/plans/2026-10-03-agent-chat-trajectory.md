# Agent Chat Trajectory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user create or edit a saved day's trajectory from transactions, choose unknown places from search results, and see confirmed versus inferred facts in Agent Chat and the live trajectory page.

**Architecture:** Extend the working chat and live trajectory API from the [foundation plan](2026-10-03-agent-chat-foundation.md). Migrate the trajectory schema to store evidence and nullable times; add a Geoapify search adapter and a staged `edit_trajectory` tool. Candidate selection and approval are validated on the server and share one atomic commit with any related transaction edits.

**Tech Stack:** Python 3.14, FastAPI, SQLite, LangChain, Geoapify Forward Geocoding API, React 19, Mapbox rendering, Vitest, `unittest`, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-agent-chat-design.md`

## Global Constraints

- Depends on the completed foundation plan; receipt work can run before this plan, as in the spec, but trajectory work must not require a receipt.
- Preserve all existing saved trajectory days during schema migration. Mark legacy facts as `legacy` evidence and accept global longitude -180…180 and latitude -90…90.
- Event `time` may be `null` only with `timeEvidence: "unknown"`; order is the saved `position`. `timeEvidence` is `exact`, `estimated`, `unknown`, or `legacy`, with `timeEvidenceNote` required for estimates. A synthetic `timeEstimated` transaction time cannot become `exact`.
- A place's `placeEvidence` is `provider`, `user`, or `legacy`; a manually chosen coordinate may have `address: null` and `sourceUrl: null`, while a provider place keeps URL and attribution. A leg's `modeEvidence` is `fare`, `user`, `inferred`, or `legacy`, with `modeEvidenceNote` for inferred modes. An inferred line and distance are approximate; do not present them as a traveled route.
- Reuse an existing saved place by ID, or create an unknown place only from a user-selected Geoapify candidate or user-supplied coordinate. Keep the source URL and attribution for provider results; Mapbox remains the map renderer.
- The agent may stage multiple transaction and trajectory commands in one proposal, but only versioned approval writes them. Cross-date references and stale candidate selections fail before commit.
- Maintain the existing local Host/Origin boundary, 8 tool calls and 60 seconds per turn, actionable missing-key errors, and built `front/dist/`.

## Review Focus

- Two stores with the same name in different cities remain separate candidate choices; text equality never silently selects a place (Tasks 2 and 3).
- A date-only imported transaction's synthetic time appears as estimated and does not order uncertain visits as confirmed (Tasks 1 and 3).
- A day with one visit has zero legs, and an unresolved place can be reviewed without breaking the map or timeline (Tasks 1 and 4).
- A Geoapify timeout, empty result, or changed candidate ID leaves a revisable proposal and never saves invented coordinates (Tasks 2 and 3).
- An approved transaction edit that moves a referenced purchase to another day cannot leave the old day's visit linked to it; the combined proposal succeeds together or conflicts (Task 3).

## File map

- `backend/db/schema.py`, `backend/db/trajectory_store.py`: transactional migration, evidence columns, nullable time, global coordinates, read/write representation.
- `backend/services/trajectory_validation.py`, `backend/services/trajectory_mutation.py`, `backend/db/store.py`: evidence, ordering, references, single-visit days, and command parsing.
- `backend/agent/places.py`, `backend/api/agent.py`: Geoapify search, place candidate binding, selection HTTP contract.
- `backend/agent/trajectory.py`, `backend/agent/runtime.py`, `backend/services/agent_changes.py`: date-specific transaction context, `search_place` and `edit_trajectory` tools, preapproval validation.
- `front/src/AgentChat.jsx`, `front/src/lib/agent-api.js`, `front/src/lib/trajectory-model.js`, `front/src/Trajectory.jsx`, `front/src/TrajectoryMap.jsx`: candidate choice and evidence-aware review and display.
- `backend/API.md`, `backend/README.md`, `front/README.md`, `front/dist/`: contracts, Geoapify configuration, shipped UI.

---

### Task 1: Global, evidence-aware trajectory storage

**Files:** Modify `backend/db/schema.py`, `backend/db/trajectory_store.py`, `backend/services/trajectory_validation.py`, `backend/services/trajectory_mutation.py`, `backend/db/store.py`, `backend/tests/test_schema.py`, `backend/tests/test_trajectory.py`, `backend/tests/test_server.py`, `backend/API.md`.

**Interfaces:** Keep the existing `GET /api/trajectory/{date}` shape and add `placeEvidence` and `attribution` to places; `timeEvidence` and `timeEvidenceNote` to events; `modeEvidence` and `modeEvidenceNote` to legs. `time: string | null` is allowed on events; `address` and `sourceUrl` may be `null` for user-coordinate places only. Extend `parse_trajectory_command(payload: object, method: str) -> TrajectoryCommand` and `validate_timeline(value: object, *, require_complete: bool = True) -> dict` for these fields. Zero or one event implies zero legs; an explicit user-chosen train/bus mode needs no fare transaction, while `modeEvidence: "fare"` does.

- [ ] **Step 1: Write failing tests.** `test_migration_preserves_legacy_days_and_marks_evidence`, `test_global_coordinates_and_unknown_time_round_trip`, `test_user_coordinate_without_address_or_url`, `test_estimated_time_cannot_claim_exact_evidence`, `test_one_event_day_has_no_leg`, `test_user_chosen_transit_without_fare`, and `test_known_times_follow_saved_position`. Assert a Tokyo legacy fixture still reads identically except for added evidence fields; new coordinates outside Tokyo persist; `null` without `unknown` fails; an estimate without a note fails; a reversed pair of known times fails.
- [ ] **Step 2: Run focused backend suites; expect failure.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_schema.py' -v` and `-p 'test_trajectory*.py' -v`.
- [ ] **Step 3: Migrate and validate.** Rebuild the constrained `trajectory_places` and `trajectory_events` tables while preserving days, dependent legs, and foreign keys, changing coordinate checks and time nullability without data loss; add evidence fields to existing rows with `legacy` defaults. Update store read/write and validation so incomplete days display safely while complete days require a leg only between adjacent events. Preserve source URLs and attribution.
- [ ] **Step 4: Rerun focused and server tests; expect PASS.** `backend/.venv/bin/python -m unittest discover -s backend/tests -v`; reopen a migrated SQLite file to confirm persistence.
- [ ] **Step 5: Commit.** Stage the listed files; `git commit -m "feat: store trajectory evidence and global places"`.

### Task 2: Geoapify candidate search and bound selection

**Files:** Create `backend/agent/places.py`, `backend/tests/test_agent_places.py`; modify `backend/api/agent.py`, `backend/db/agent_store.py`, `backend/agent/contracts.py`, `backend/tests/test_agent_api.py`, `backend/API.md`, `backend/README.md`.

**Interfaces:** Produce `search_places(query: str, *, bias: tuple[float, float] | None = None) -> list[PlaceCandidate]`, where each candidate has `id`, `name`, `address`, `coordinates`, `sourceUrl`, `attribution`; extend `AgentStore.create_proposal(..., place_candidates: list[PlaceCandidate] | None = None)` and produce `select_place_candidate(proposal_id: str, revision: int, candidate_id: str) -> dict`. Expose `POST /api/agent/proposals/{id}/places/selection` with `{revision, candidateId}` and return the revised proposal with a new revision.

- [ ] **Step 1: Write failing tests.** `test_geoapify_search_returns_distinct_same_name_results`, `test_timeout_empty_and_missing_key`, `test_candidate_selection_uses_saved_coordinates`, and `test_forged_or_stale_candidate_rejected`. Assert the key stays server-side, address and attribution remain visible, and the client cannot submit coordinates or use a candidate from another proposal.
- [ ] **Step 2: Run focused tests; expect failure.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_places.py' -v` and `-p 'test_agent_api.py' -v`.
- [ ] **Step 3: Implement search and selection.** Query [Geoapify Forward Geocoding](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/) at `https://api.geoapify.com/v1/geocode/search` with `text`, `format=json`, `limit=5`, and optional `bias=proximity:lon,lat`; map `place_id`, `name`/`formatted`, `lon`, `lat`, `datasource.attribution`, and `datasource.url` without putting the API key in a stored URL. Bound query and response sizes and use a timeout. Save candidates with the proposal; selection reads the stored server-side result, revalidates revision and coordinates, then revises the command. Return actionable errors for missing key, timeout, or no results. Existing saved places may also be selected by internal ID.
- [ ] **Step 4: Rerun focused tests; expect PASS.** Verify a real HTTP request is never made in tests by injecting the search client; run `git diff --check`.
- [ ] **Step 5: Commit.** Stage the listed files; `git commit -m "feat: search and select trajectory places"`.

### Task 3: Date-specific trajectory proposals and atomic cross-domain checks

**Files:** Create `backend/agent/trajectory.py`, `backend/tests/test_agent_trajectory.py`; modify `backend/agent/runtime.py`, `backend/agent/contracts.py`, `backend/services/agent_changes.py`, `backend/db/store.py`, `backend/tests/test_agent_runtime.py`, `backend/tests/test_agent_changes.py`, `backend/API.md`.

**Interfaces:** Produce `build_trajectory_context(connection: sqlite3.Connection, day: str) -> dict` for day-filtered transactions and the saved day; `AgentRunner.run_turn(...)` registers `search_place` and `edit_trajectory` alongside existing tools. `edit_trajectory` stages `AgentCommand(kind="trajectory.create" | "trajectory.update", identity={...}, data={...})`; it never calls `Store.mutate_trajectory` directly. The shared approval path validates command references and selected place IDs together.

- [ ] **Step 1: Write failing tests.** `test_day_transactions_stage_visit_proposal`, `test_synthetic_time_requires_estimated_evidence`, `test_two_unknown_visits_require_order_confirmation`, `test_same_transaction_not_auto_assigned_twice`, `test_place_search_failure_keeps_revisable_proposal`, `test_cross_date_transaction_edit_rolls_back_trajectory`, and `test_fare_deletion_downgrades_leg_evidence`. Assert no business write before approval; a fare-linked train or bus uses `modeEvidence: "fare"`, a guessed leg uses `"inferred"` with a note, and unrelated days are not sent to the model.
- [ ] **Step 2: Run focused tests; expect failure.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_trajectory.py' -v` and `-p 'test_agent_changes.py' -v`.
- [ ] **Step 3: Implement the tools and approval checks.** Query only the requested day; reuse `read_sql` for bounded factual reads, existing places, and the selected Geoapify candidates. Stage visit, place, and leg commands with before/after evidence, explanatory notes, estimated flags, and target fingerprints. In the one-transaction approval, recheck transaction date and IDs, event order, leg adjacency, place source, and the revision; reject stale or inconsistent proposals with `409`. When a fare transaction is deleted, detach its reference and mark the leg inferred in the same commit.
- [ ] **Step 4: Rerun agent and backend suites; expect PASS.** `backend/.venv/bin/python -m unittest discover -s backend/tests -v`; confirm an OpenAI or Geoapify failure leaves transaction and trajectory tables unchanged.
- [ ] **Step 5: Commit.** Stage the listed files; `git commit -m "feat: stage trajectory changes from transactions"`.

### Task 4: Place choice and evidence in the app

**Files:** Modify `front/src/AgentChat.jsx`, `front/src/lib/agent-api.js`, `front/src/lib/trajectory-model.js`, `front/src/Trajectory.jsx`, `front/src/TrajectoryMap.jsx`, `front/src/AgentChat.test.jsx`, `front/src/lib/trajectory-model.test.js`, `front/src/Trajectory.test.jsx`, `front/tests/e2e/app.spec.cjs`, `front/README.md`, `front/dist/`.

**Interfaces:** `selectPlaceCandidate(proposalId: string, revision: number, candidateId: string) -> Promise<Proposal>`; the review card shows the selected date, linked transactions, candidate name/address/source, before/after visits and legs, evidence notes, and `exact`/`estimated`/`unknown`/`legacy` labels. The live trajectory page renders nullable time, one visit, unresolved place, and approximate links without crashing.

- [ ] **Step 1: Write failing UI tests.** `test_same_name_candidates_need_explicit_selection`, `test_unknown_time_and_inferred_leg_labels`, `test_one_visit_and_unresolved_place_without_map`, `test_user_coordinate_without_source_link`, `test_stale_selection_recovers`, and `test_approved_day_reloads_from_api`. Assert selected candidate ID, not client coordinates, is submitted for provider results; a manual coordinate shows no broken source link; the screen never labels an inferred link as actual travel distance; approval refreshes the saved day.
- [ ] **Step 2: Run focused Vitest; expect failure.** `cd front && npm test -- src/AgentChat.test.jsx src/lib/trajectory-model.test.js src/Trajectory.test.jsx`.
- [ ] **Step 3: Implement candidate and evidence review.** Follow `DESIGN.md` visual properties, `MASTER.md` general UX, and `ui-ux-pro-max` accessibility guidance. Show address and attribution in candidate choices; allow explicit saved-place or user-coordinate selection, disclose inference, and keep the timeline usable when map rendering is unavailable. Label the provider link as a source, not necessarily a store-information page. Keep one-column phone layout and keyboard selection.
- [ ] **Step 4: Run front tests, isolated E2E, and build; expect PASS.** `cd front && npm test`, `npm run build`, then `npm run test:e2e -- --config=playwright.agent.config.cjs tests/e2e/app.spec.cjs`; extend the foundation's temporary-DB server with fake model/place services. Inspect Agent Chat and trajectory on desktop and phone, then run `git diff --check`.
- [ ] **Step 5: Commit.** Stage the listed files; `git commit -m "feat: review and display inferred trajectories"`.
