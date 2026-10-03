# Agent Chat UI refresh

Approved bounded design, implemented on `feature/agent-chat`.

## Changes

- Removed the introductory and welcome blocks from the visible page.
- Moved conversation history beneath Agent Chat in the desktop sidebar. Narrow screens and a collapsed sidebar use a history dialog with native focus handling.
- Combined receipt selection, attachment preview, message entry and icon-only submission into one composer.
- New conversations center the local-time greeting and composer. Greetings use 05:00 / 11:00 / 18:00 boundaries and update on a minute timer and tab visibility changes.
- Active conversations scroll above a stationary composer. Short landscape screens use a smaller input height. Visual viewport resize events account for the onscreen keyboard.
- Draft text, receipt selection and retry identity live at the app boundary and survive conversation/route changes while the app is open. Reloading the browser clears these in-memory drafts.
- Plain Enter inserts a newline. Command/Ctrl+Enter submits, except during IME composition. Existing proposal approval still requires its explicit action.

## Evidence

- Four new behavior tests were observed failing before implementation: history placement/composer, draft preservation, keyboard shortcut/IME, live greeting changes.
- Frontend: **88/88 passed**, `npm --prefix front test`.
- Browser: **15/15 passed**, `npm run test:e2e -- --config=playwright.agent.config.cjs tests/e2e/app.spec.cjs tests/e2e/agent-layout.spec.cjs` from `front/`.
- Production build and `git diff --check` passed. The existing Mapbox chunk-size warning remains.
- Browser tests use a temporary database and fake AI runner; no user data was changed and no paid model calls were made for this UI verification.
- Screenshots inspected at desktop 1440x900, phone 375x812, and landscape 812x375. Existing dashboard first content still exposes the selected month and financial state at desktop and phone widths.
- A visualViewport resize was simulated to verify that the composer fits above a 470px visible viewport. This is browser-level emulation, not a physical-device keyboard test.
- Original receipt review, proposal edits, lost-response recovery, explicit approval, and trajectory updates continue to pass browser tests.
