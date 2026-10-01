# React Front Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the browser UI with React while preserving its appearance, behavior, URLs, data, and FastAPI-only everyday startup.

**Architecture:** Vite builds `front/src/` into tracked `front/dist/`; FastAPI serves that directory at `/` and keeps its existing API. React owns view state and DOM; pure data and API functions remain separate modules. The server remains the source of truth after the existing one-time browser-storage import.

**Tech Stack:** React, React DOM, Vite, JavaScript/JSX, npm lockfile, existing FastAPI/Python 3.14, browser tests.

**Spec:** `docs/superpowers/specs/2026-10-02-react-front-refactor-design.md`

## Global Constraints

- Keep visible layout, text, behavior, `http://localhost:8765/`, hash URLs, API JSON, and SQLite data handling the same.
- Keep `front/dist/` in Git so the documented `fastapi run backend/server.py --host 127.0.0.1 --port 8765` works without Node.js at runtime.
- Use `DESIGN.md` for visual styling, `design-system/household-budget-app/pages/dashboard.md` for dashboard order/density, and `MASTER.md` for remaining app UX.
- The first content after navigation must show the selected month and financial state or recording action at desktop and phone widths.
- Preserve the current same-origin writes, one-time `kakei-transactions-v1` import, stale-after-write recovery, CSV format, and keyboard/focus behavior.

## File Map

- `front/package.json`, `front/package-lock.json`, `front/vite.config.js`: pinned build and test commands; output `front/dist/`.
- `front/index.html`, `front/src/main.jsx`: original metadata and SVG sprite, React mount, CSS import.
- `front/src/lib/{api,transaction-data,transaction-detail,sample-data,dashboard}.js`: ES module API and pure calculations; no DOM writes.
- `front/src/useTransactions.js`: API lifecycle, single source of server data, loading/write/stale states.
- `front/src/{App,AppShell,Dashboard,TransactionDetail,TransactionDialog}.jsx`: app state and the four screen regions; split dashboard display-only sections further if a file becomes difficult to review.
- `front/styles.css`: preserve existing rules; change only selectors required by identical rendered structure.
- `backend/server.py`, `backend/tests/test_server.py`, `backend/README.md`: serve the built directory by default and document build/update flow.
- `front/src/**/*.test.*`, `front/tests/e2e/*`: pure, component, and browser behavior checks; replace relevant legacy CommonJS tests after coverage is equivalent.

## Review Focus

1. Missing, empty, or malformed `kakei-transactions-v1` on a new DB must keep the current initial-import and error behavior (Task 2 test).
2. Unicode, slash, and percent in transaction IDs must retain detail deep links and back navigation (Task 4 test).
3. A successful write followed by failed refresh must show a stale state without repeating that write (Task 5 test).
4. Older expense records without new detail fields must still render and export without invented values (Task 2 and Task 4 tests).
5. Modal close/focus restoration and the first visible dashboard content must hold at 375px and desktop width (Task 5 and Task 6 tests).

---

### Task 1: Baseline and production build path

**Files:** Create `front/package.json`, `front/package-lock.json`, `front/vite.config.js`, `front/src/main.jsx`; modify `front/index.html`, `backend/server.py`, `backend/tests/test_server.py`; create initial `front/dist/`.

**Interfaces:** Produce `front/dist/index.html` and assets from `npm run build`; preserve `create_app(db_path: Path, front_dir: Path, *, port: int = 8765)`; default `app` serves `front/dist`.

- [ ] Capture pre-change desktop and 375px screenshots with fixed date/data for normal, empty, detail, dialog, loading, and error states; save verification artifacts outside the served source tree.
- [ ] Write a backend test: the default app serves a built index and its referenced assets, while `create_app(..., front_dir)` still serves a test fixture directory.
- [ ] Run the backend test and confirm it fails because the default app points at `front/`.
- [ ] Add the Vite/React build, minimal mount, tracked output, and static-directory switch; keep FastAPI API routing ahead of static mounting.
- [ ] Run `npm run build` and the backend test; verify `GET /`, built JS/CSS, and `GET /api/status` through FastAPI. Commit the task.

### Task 2: ES modules and transaction contracts

**Files:** Create `front/src/lib/{api,transaction-data,transaction-detail,sample-data,dashboard}.js` and focused tests; retire the legacy global modules when consumers are migrated.

**Interfaces:** Keep named API operations `listTransactions`, `loadInitialTransactions`, `addTransaction`, `removeTransaction`, `removeSamples`; keep `parseExpenseDraft`, `readExpenseDetails`, `serializeTransactionsCsv`, `detailHref`, `detailIdFromHash`, `createSampleTransactions`; expose `dashboardForMonth(records, month)` for sums, category totals, weekly totals, and sorted rows.

- [ ] Move existing contract tests to the module test runner; add assertions for absent/empty/malformed storage, import conflict, unusual IDs, old expense fields, CSV escaping, and exact month totals.
- [ ] Run those tests and confirm missing ES module exports fail.
- [ ] Convert the existing pure logic and API client without changing request paths, payloads, errors, sample values, or CSV output; remove unused browser-storage write helpers.
- [ ] Run the module tests and existing backend suite; compare sample output and commit the task.

### Task 3: Dashboard and server data lifecycle

**Files:** Create `front/src/useTransactions.js`, `front/src/{App,AppShell,Dashboard}.jsx` and component tests; adapt `front/src/main.jsx`.

**Interfaces:** `useTransactions()` returns `{transactions, status, error, writePending, load, refresh, addTransaction, deleteTransaction, deleteSamples}` where `status` is `loading`, `ready`, `loadError`, or `stale`. `refresh()` returns `Promise<boolean>`; each write method returns `Promise<boolean>` (`true` when saved and refreshed, `false` when saved but stale) and throws on write failure. `Dashboard` receives the selected month, derived data, filters, status, and callbacks as props.

- [ ] Write failing component tests for initial loading, selected month/financial summary, month navigation, search/type filtering, sample label, initial import, and retry after load error.
- [ ] Run focused tests and confirm the components/hook are absent.
- [ ] Render the existing app shell and dashboard markup/classes in React; use the Task 2 model and API, including visibility-change refresh and disabled states.
- [ ] Run component and module tests, build, and inspect desktop/phone first content against the baseline; commit the task.

### Task 4: Detail URL and return behavior

**Files:** Create `front/src/TransactionDetail.jsx` and tests; modify `front/src/App.jsx`.

**Interfaces:** Hash routes remain `#overview`, `#transactions`, `#budget`, `#insights`, `#transaction/{encoded-id}`; `TransactionDetail` receives the matched transaction and delete callback.

- [ ] Write failing tests for direct detail URL, missing record, legacy expense fields, encoded ID, active navigation, and returning to the original list row/scroll position with focus.
- [ ] Run focused tests and confirm route/detail behavior is missing.
- [ ] Implement hash listening and detail rendering without a router library; preserve heading focus and list return state.
- [ ] Run focused and dashboard tests, then check a deep link in the browser; commit the task.

### Task 5: Transaction form and mutations

**Files:** Create `front/src/TransactionDialog.jsx` and tests; modify `front/src/App.jsx`, `front/src/useTransactions.js`, and component tests.

**Interfaces:** `TransactionDialog` receives `{open, selectedMonth, busy, onClose, onSubmit}`; `onSubmit(draft)` returns `Promise<boolean>` with the Task 3 saved/refresh semantics. Delete and sample-delete callbacks use the Task 3 hook.

- [ ] Write failing tests for income/expense fields, item sum and manual amount restoration, validation focus, server field error, Escape/close focus return, successful add/delete/sample removal, failed write, and successful write with failed refresh and no duplicate request.
- [ ] Run focused tests and confirm behavior is missing.
- [ ] Implement the existing native dialog/form DOM and React state; wire writes, confirmations, toast, CSV export, and stale-state retry to the existing API contract.
- [ ] Run all front tests and the backend suite, then exercise keyboard and touch flows in the browser; commit the task.

### Task 6: Visual parity and release verification

**Files:** Update `front/dist/`, `front/styles.css` only where parity requires it, `backend/README.md`, and browser tests/fixtures; remove superseded `front/*.js` and legacy tests after equivalent coverage is green.

**Interfaces:** Runtime remains one FastAPI command; source changes require `npm ci && npm run build` and committed `front/dist/`.

- [ ] Add browser checks for first viewport at desktop/375px, no horizontal scroll, modal focus, detail return, API import/write/delete, and all specified error/retry states.
- [ ] Run the browser checks against the pre-migration baseline and fix only observed layout/behavior differences.
- [ ] Verify `npm ci`, full front tests, `npm run build`, built-output consistency, backend tests, and a real FastAPI start with an isolated DB; confirm `GET /` and `/api/status` and a saved transaction.
- [ ] Update README with build workflow and FastAPI-only everyday startup, review the final diff and screenshot comparisons, then commit the task.
