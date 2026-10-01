# Transaction Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Kakei user open one transaction from the dashboard, confirm its five recorded fields, and delete it after confirmation.

**Architecture:** Keep the existing static app and localStorage schema. A small browser-compatible helper handles detail URLs and atomic deletion; `front/app.js` switches between the mounted dashboard and a detail view using the hash, so returning can restore the list state.

**Tech Stack:** Plain HTML, CSS, browser JavaScript, localStorage, Node.js built-in `node:test`; no product or test packages.

**Spec:** `docs/superpowers/specs/2026-10-01-transaction-detail-design.md`

## Global Constraints

- The detail is an in-product screen; `DESIGN.md` governs visual styling and `design-system/household-budget-app/MASTER.md` supplies remaining UX guidance.
- Display only `title`, `amount`, `date`, `type`, and `category`; do not add stored fields or migration.
- Use `#transaction/<encodeURIComponent(id)>` for detail URLs; keep existing dashboard anchors.
- Keep the dashboard mounted, its month/search/type inputs intact, and restore scroll and focus when returning from its list.
- A failed localStorage write must leave the transaction and detail view unchanged.
- Preserve visible focus, keyboard access, readable mobile layout, and the existing app navigation.

## Review Focus

- IDs with `/`, `#`, spaces, or Japanese characters must round-trip through the URL (Task 1 test).
- A malformed percent escape in a hash must show the missing-transaction state rather than stop the app (Task 1 test; Task 2 browser check).
- A user-entered title containing HTML markup must display as text, never as executable HTML (Task 2 browser check).
- A very long title or large amount must wrap within a 375px viewport without horizontal page scrolling (Task 2 browser check).
- A storage quota or security exception during deletion must leave the original array intact (Task 1 test; Task 3 browser check).

---

### Task 1: URL and deletion helpers

**Files:**
- Create: `front/transaction-detail.js`
- Create: `tests/transaction-detail.test.cjs`

**Interfaces:**
- Produces `KakeiDetail.detailHref(id: string): string` and `KakeiDetail.detailIdFromHash(hash: string): string | null` on `globalThis`, with CommonJS export for Node tests.
- Produces `KakeiDetail.removePersistedTransaction(items: object[], id: string, storage: Storage, key: string): object[]`; it writes the candidate array before returning it, throws on storage failure, and never mutates `items`.

- [ ] **Step 1: Write failing `node:test` cases** for URL round-trip (including special characters), non-detail and malformed hashes, successful deletion persistence, and a throwing `setItem` that leaves the original array unchanged.
- [ ] **Step 2: Run `node --test tests/transaction-detail.test.cjs`** and confirm failure because the helper does not exist.
- [ ] **Step 3: Implement the three helper functions** in `front/transaction-detail.js`; expose the same object to the browser and CommonJS without dependencies.
- [ ] **Step 4: Run `node --test tests/transaction-detail.test.cjs`** and confirm all cases pass.
- [ ] **Step 5: Commit** only the helper and its tests as `feat: add transaction detail URL and storage helpers`.

### Task 2: Detail display and navigation

**Files:**
- Modify: `front/index.html`
- Modify: `front/app.js`
- Modify: `front/styles.css`

**Interfaces:**
- Consumes `KakeiDetail.detailHref` and `KakeiDetail.detailIdFromHash` from Task 1, loaded before `app.js`.
- Produces `renderRoute(): void` in `app.js`; it switches `#dashboard-view` and `#detail-view` and renders either the matching transaction or an explicit missing state.

- [ ] **Step 1: Record browser checks** for list link, direct hash, reload, malformed hash, browser back, preserved month/search/type/scroll, focus restoration, markup-like title, and 375px long-content layout.
- [ ] **Step 2: Add the semantic detail markup and script order** in `front/index.html`: a labeled back link, focusable heading, signed amount and type, title, labeled date/category, sample marker, deletion control, and missing state. Keep dashboard content mounted.
- [ ] **Step 3: Implement routing in `front/app.js`**: transaction-name links; `hashchange` and initial rendering; `textContent` for user fields; saved scroll/focus from list navigation; fallback to `#transactions` for direct entry; document title and nav state updates. An unrelated dashboard hash keeps its anchor behavior.
- [ ] **Step 4: Style detail and responsive states in `front/styles.css`** with existing tokens. Ensure hidden views are actually removed from layout, controls meet 44px targets, long content wraps, and the fixed mobile navigation does not cover content.
- [ ] **Step 5: Run the Step 1 browser checks** at desktop and 375px; fix any failed behavior or visual constraint, then commit only these three files as `feat: show transaction details with back navigation`.

### Task 3: Confirmed deletion and external changes

**Files:**
- Modify: `front/app.js`
- Modify: `tests/transaction-detail.test.cjs` if an additional helper edge case is found

**Interfaces:**
- Consumes `KakeiDetail.removePersistedTransaction` from Task 1 and `renderRoute` from Task 2.
- The existing `transactions` array changes only after persistence succeeds.

- [ ] **Step 1: Record browser checks** for cancel, successful delete with recomputed dashboard totals, a simulated throwing storage write, and deletion from another tab while detail is open.
- [ ] **Step 2: Move deletion to the detail control** in `front/app.js`; remove the row button, use a confirmation naming the transaction, persist before replacing `transactions`, and return to the list only on success.
- [ ] **Step 3: Handle `storage` events** for `kakei-transactions-v1`; parse valid arrays through `isValidTransaction`, treat a removed key as an empty array, rerender the current route, and show the missing state when its transaction disappeared.
- [ ] **Step 4: Run `node --test tests/transaction-detail.test.cjs` and the Step 1 browser checks**; confirm cancel and write failure keep the detail and data, then commit `front/app.js` (and any changed test) as `feat: safely delete transaction from detail`.

### Task 4: Final verification

**Files:** None expected.

**Interfaces:** No new interface.

- [ ] **Step 1: Run `node --test tests/transaction-detail.test.cjs` and `git diff --check`**; both must pass.
- [ ] **Step 2: Inspect the first visible content after navigation** on the dashboard at desktop and 375px: selected month and financial state or an action must be visible immediately, as `AGENTS.md` requires.
- [ ] **Step 3: Inspect detail at desktop and 375px**, keyboard-only and with reduced motion; confirm data hierarchy, focus, return path, and no horizontal scroll.
- [ ] **Step 4: Report the verified result and any browser-preview limit** without claiming an unrun check passed.
