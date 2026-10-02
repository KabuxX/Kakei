# September Trajectory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a Tokyo based, 30 day September 2026 sample journey as a dated transaction timeline and an estimated route on the existing trajectory page.

**Architecture:** Keep the archived 16 transactions, the new transaction fixture, and the new timeline fixture in three separate JSON files. Build a validated day model by joining the two new fixtures on transaction ID; render its timeline independently of a lazily loaded Mapbox GL JS map with deck.gl layers and Turf.js measurements.

**Tech Stack:** React 19, Vite 7, Vitest, Playwright, Mapbox GL JS, `@deck.gl/mapbox`, `@deck.gl/layers`, Turf.js.

**Spec:** `docs/superpowers/specs/2026-10-02-september-trajectory-design.md`

## Global Constraints

- The demo covers every date from `2026-09-01` through `2026-09-30` in Tokyo; purchases, times, amounts, and movement are fictional.
- `old-samples.json` remains separate and unchanged after creation. Existing SQLite databases, API contracts, and the normal transaction form are not migrated or extended.
- Fresh initialization reads only `september-transactions.json`; the trajectory reads both new JSON files. The trajectory remains a fixed, explicitly labeled sample even when stored transactions differ or samples are deleted.
- Source URLs and addresses for real stations and shops accompany coordinates in the timeline JSON. Drawn lines and distance are labeled estimated.
- Keep the existing `sample-0` salary transaction (`2026-09-28`, `給与`, 320000 yen) in the new fixture so existing transaction detail flows and local development checks still have their referenced record.
- Follow `DESIGN.md` for visual styling, the in-product guidance in `MASTER.md`, and the existing app navigation. Keep the first visible trajectory content date and day summary at desktop and phone widths.
- A Mapbox public token is read from `VITE_MAPBOX_ACCESS_TOKEN`; no token is committed. Date controls and the timeline work without a map.
- Do not alter the unrelated preexisting worktree changes in `.gitignore`, `backend/README.md`, `front/package.json`, `front/vite.config.mjs`, `front/README.md`, `front/dev/`, or `front/src/dev-environments.test.js` except where this plan explicitly needs `front/package.json` for map dependencies; preserve those existing edits and stage only feature hunks.

## Review Focus

1. A partly deleted legacy sample set must remain untouched; the existing DB import path must never reseed it. Task 1 tests an initialized server response.
2. A timeline event with an unknown transaction ID or a transaction from another date must fail fixture validation, rather than draw a plausible but false route. Task 2 tests both inputs.
3. Rent, online payments, and pass purchase must not become visited places merely because they have a merchant. Task 2 tests a non-geographic transaction.
4. Missing token, unsupported WebGL, or a map loading error must leave the selected date and timeline operable. Task 3 tests the map messages; Task 4 tests the intact page.
5. Switching dates rapidly, including the first and last day, must not show stale markers or enable out of range navigation. Task 4 tests boundaries and rapid changes.

---

## File Map

- `front/src/data/old-samples.json`: archive of the current 16 September 2026 sample transactions.
- `front/src/data/september-transactions.json`: transaction records used for fresh initialization and trajectory display.
- `front/src/data/september-timeline.json`: sourced places, dated events, and legs for the trajectory display.
- `front/src/lib/sample-data.js`: load and return a defensive copy of the new transaction fixture.
- `front/src/lib/trajectory-model.js`: validate and join fixtures; derive days, leg geometry, and summary values.
- `front/src/Trajectory.jsx` and `front/trajectory.css`: date controls, day summary, timeline, legend, and responsive layout.
- `front/src/TrajectoryMap.jsx`: lazily mounted Mapbox/deck.gl map, view fitting, selection, and map failure states.
- `front/src/App.jsx`: mount the trajectory page at `#trajectory` and preserve existing focus behavior.
- `front/package.json` and `front/package-lock.json`: map and geometry dependencies.
- `docs/trajectory-mapbox-setup.md`: public token setup and sample behavior, separate from the existing untracked `front/README.md`.

### Task 1: Independent JSON fixtures and fresh initialization

**Files:** Create `front/src/data/old-samples.json` and `front/src/data/september-transactions.json`. Modify `front/src/lib/sample-data.js`, `front/src/useTransactions.js`, and `front/src/lib/contracts.test.js`. Test `front/src/lib/sample-data.test.js`.

**Interfaces:** Produce `createSampleTransactions(): Transaction[]`, a defensive copy of `september-transactions.json`. Both JSON files used by the trajectory are static imports in Task 2.

- [ ] **Step 1: Write failing tests.** In `sample-data.test.js`, assert 30 distinct September dates, unique IDs, valid expense item sums, and that mutating one `createSampleTransactions()` result does not mutate the next. Update the contract test to assert the archived old JSON has 16 records and the fresh sample comes from the new JSON. Keep the existing API test that proves an initialized server skips the sample factory.
- [ ] **Step 2: Run `cd front && npm test -- src/lib/sample-data.test.js src/lib/contracts.test.js`.** Expect the new fixture assertions to fail against the current 16 record generator.
- [ ] **Step 3: Add the two transaction JSON files.** The old JSON records must match the current generator for September 2026. The new JSON must use existing server fields, cover 30 days, retain the `sample-0` salary record, and include location specific merchants and transport item names.
- [ ] **Step 4: Implement `createSampleTransactions()` in `sample-data.js` and remove its dynamic month argument in `useTransactions.js`.** Keep the existing localStorage import precedence.
- [ ] **Step 5: Run the same focused tests.** Expect PASS, including the initialized server behavior.
- [ ] **Step 6: Commit only Task 1 files.**

### Task 2: Timeline fixture and day model

**Files:** Populate `front/src/data/september-timeline.json`. Create `front/src/lib/trajectory-model.js` and `front/src/lib/trajectory-model.test.js`. Add `@turf/bbox` and `@turf/length` (and any required Turf geometry helper) to `front/package.json` and lockfile, preserving preexisting edits.

**Interfaces:** Timeline JSON is `{ places: Record<string, {name,address,coordinates,sourceUrl}>, days: Array<{date,events,legs}> }`. An event is `{id,time,placeId,transactionId?}`. A leg is `{fromEventId,toEventId,transportTransactionId?,modeHint?,viaPlaceIds?}`. `modeHint` is `walk`, `train`, or `bus`; train and bus require a matching transport transaction, while walk is labeled estimated. Export `buildTrajectoryDays(transactions, timeline): Map<string, DayModel>`; each `DayModel` has `date`, ordered `events`, ordered `segments` with route coordinates and a mode, `expenseTotal`, `stopCount`, `modes`, `distanceKm`, and `bounds`. The model throws an explanatory error for invalid fixture references.

- [ ] **Step 1: Write failing model tests.** Cover all 30 dates, at least two visited events per date, chronological order, joined merchant/items/amount, source and Tokyo coordinate checks, unknown ID, cross date ID, duplicate event/transaction ID, and non-geographic rent or pass purchase. Assert a train or bus leg has a matching traffic item, a walk hint yields `walk_estimated`, and a leg without evidence or hint is `inferred`.
- [ ] **Step 2: Run `cd front && npm test -- src/lib/trajectory-model.test.js`.** Expect FAIL because the model does not exist.
- [ ] **Step 3: Add the Turf dependencies.** Stage only dependency hunks in the already modified package file.
- [ ] **Step 4: Complete the timeline JSON.** Verify each source URL against an official station or merchant page and provide all 30 days, places, events, and legs.
- [ ] **Step 5: Implement `buildTrajectoryDays()` in `trajectory-model.js`.** Use Turf to calculate a bounding box and approximate length from each leg's start, optional via points, and end. Do not infer exact roads or rail lines. Keep geographic validation in this data layer, not in React components.
- [ ] **Step 6: Run the focused tests.** Expect PASS for the full fixture and malformed fixture cases.
- [ ] **Step 7: Commit only Task 2 files.**

### Task 3: Map rendering and resilient fallback

**Files:** Create `front/src/TrajectoryMap.jsx`, `front/src/TrajectoryMap.test.jsx`. Add `mapbox-gl`, `@deck.gl/mapbox`, `@deck.gl/layers` to `front/package.json` and lockfile; retain Task 2 and preexisting package edits.

**Interfaces:** Default export `TrajectoryMap({ day, selectedEventId, onSelectEvent })`. `day` is a Task 2 `DayModel`. The component owns Mapbox creation, one `MapboxOverlay` with `PathLayer`, `ScatterplotLayer`, and `TextLayer`, bounds fitting, error state, and cleanup. It never owns the timeline or date state.

- [ ] **Step 1: Write failing component tests.** Mock Mapbox and deck.gl modules. Assert one map instance and overlay while mounted, fresh layer data and `fitBounds` on date changes, marker selection calls `onSelectEvent`, and removal on unmount. Parameterize missing `VITE_MAPBOX_ACCESS_TOKEN`, unsupported WebGL, and map error: each shows a readable message while the parent timeline remains available.
- [ ] **Step 2: Run `cd front && npm test -- src/TrajectoryMap.test.jsx`.** Expect FAIL because the component does not exist.
- [ ] **Step 3: Add Mapbox and deck.gl dependencies.** Stage only dependency hunks in the already modified package file.
- [ ] **Step 4: Implement `TrajectoryMap`.** Import Mapbox CSS. Set accessible label and description on the map region; preserve Mapbox attribution. Use the deck overlay's layer update API and the day model's bounds; respect reduced motion when fitting.
- [ ] **Step 5: Run the focused tests.** Expect PASS for normal setup, updates, failures, and cleanup.
- [ ] **Step 6: Commit only Task 3 files and the relevant dependency changes.**

### Task 4: Trajectory page, responsive interaction, and route

**Files:** Create `front/src/Trajectory.jsx`, `front/trajectory.css`, and `front/src/Trajectory.test.jsx`. Modify `front/src/App.jsx`, `front/src/App.route.test.jsx`, and the existing trajectory case in `front/tests/e2e/app.spec.cjs`.

**Interfaces:** Default export `Trajectory()` reads the two new JSON fixtures, calls `buildTrajectoryDays()`, owns selected date and event state, and lazy loads `TrajectoryMap` only while the route is visible. App mounts it at `#trajectory` and preserves heading focus on entry. The day model is the only prop passed to the map.

- [ ] **Step 1: Write failing page tests.** Assert initial September date and summary appear before map and timeline; first/last date buttons disable at boundaries; date select and previous/next update day details; rapid date changes show only the final day's events; timeline item selection sends the event ID to the map; token free map fallback leaves day controls and timeline usable; all controls have names and 44px targets. Update the e2e test to expect the populated trajectory on desktop and 375px without horizontal scroll.
- [ ] **Step 2: Run `cd front && npm test -- src/Trajectory.test.jsx src/App.route.test.jsx`.** Expect FAIL because the page and route are not wired.
- [ ] **Step 3: Implement `Trajectory` and `trajectory.css`.** Use `DESIGN.md` tokens and in-product density. Place date and day summary first, map/timeline side by side on desktop and stacked on phones, with a visible mode legend and permanent timeline alternative. Show the fixed demo label even when the DB has different records.
- [ ] **Step 4: Wire `Trajectory` into `App.jsx`.** Preserve current app navigation and focus behavior.
- [ ] **Step 5: Run `cd front && npm test -- src/Trajectory.test.jsx src/App.route.test.jsx`.** Expect PASS.
- [ ] **Step 6: Run `cd front && npm run build` and `cd front && npm run test:e2e -- --grep trajectory`.** Expect PASS and no sideways scrolling at 375px. If a live Mapbox token is unavailable, verify the map's explicit setup state and state that live tile rendering remains unverified.
- [ ] **Step 7: Commit only Task 4 files.**

### Task 5: End to end verification and setup documentation

**Files:** Create `docs/trajectory-mapbox-setup.md` and, only if verification exposes a concrete issue, the files from Tasks 1–4 and their owning tests.

**Interfaces:** No new product interface. The setup document explains `VITE_MAPBOX_ACCESS_TOKEN`, the three JSON files' roles, the fixed September 2026 demo, and the fact that existing DBs are unchanged.

- [ ] **Step 1: Add the setup and behavior document.** Verify Mapbox token wording against the official guide; leave the existing untracked README untouched.
- [ ] **Step 2: Run `cd front && npm test`.** Expect PASS; investigate only concrete failures.
- [ ] **Step 3: Run `cd front && npm run build`.** Expect PASS.
- [ ] **Step 4: Run the full existing e2e suite under the repository's documented local server procedure.** Expect PASS. If the browser can render tiles with an available token, inspect selected day and route on desktop and phone; otherwise record that limit.
- [ ] **Step 5: Inspect the first content after app navigation at desktop and 375px.** Confirm the selected date and day summary are visible without scrolling, the timeline remains usable without a map, focus is visible, and the map does not cover phone navigation.
- [ ] **Step 6: Run `git diff --check` and inspect the final diff.** Expect no whitespace errors and no unrelated edits in the task's commits.
- [ ] **Step 7: Commit Task 5 changes and report the feature, verification evidence, and any map token limitation.**
