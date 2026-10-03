# Agent Chat implementation record

Branch: feature/agent-chat. Isolated worktree; no user database or API keys used.

## foundation

Ruling: Use the already-authorized isolated worktree at .worktrees/agent-chat without another consent prompt — reversible implementation setup is authorized by the task and developer instructions — cost if wrong: work is on a separate branch.
Ruling: Foundation Task 3 generalizes the display before the later storage migration; global-coordinate persistence lands in trajectory Task 1 — keeps schema migration in one place — cost if wrong: interim foundation does not yet accept new global places.
Task 4: Ruling: Disallow CTE syntax, including nested WITH — SQLite authorizer context names alone must not allow a CTE to impersonate a public view; the spec requires SELECT, not CTE support — cost if wrong: some read queries need rewriting as joins/subqueries. Runtime limit is tested with a large SELECT cross join instead of recursive CTE.
Task 1: complete (commits 32a268a..b4df086, tests: backend/.venv/bin/python -m unittest discover -s backend/tests → OK)
Task 2: complete (commits b4df086..2eca483, tests: backend/.venv/bin/python -m unittest discover -s backend/tests → OK)
Task 3: complete (commits 2eca483..cfe1392, tests: npm --prefix front test -- src/lib/trajectory-model.test.js src/Trajectory.test.jsx src/TrajectoryMap.test.jsx src/App.route.test.jsx src/Trajectory.failure.test.jsx →    Duration  1.33s (environment 54%, tests 31%, import 8%, transform 6%))
Task 4: complete (commits cfe1392..f6a0703, tests: backend/.venv/bin/python -m unittest discover -s backend/tests → OK)
Task 5: complete (commits f6a0703..cacb874, tests: backend/.venv/bin/python -m unittest discover -s backend/tests → OK)
Task 6: complete (commits cacb874..851b9ab, tests: backend/.venv/bin/python -m unittest discover -s backend/tests → OK)
Task 7: complete (commits 851b9ab..63d1054, tests: backend/.venv/bin/python -m unittest discover -s backend/tests -p test_agent_*.py → OK)
Ruling (Task 7): Persist a turn lease and cached HTTP result atomically with assistant message/proposal. Compare a local-only full domain hash across generation. This rejects unrelated concurrent changes conservatively; it prevents stale generated edits and never sends that snapshot to the model. Cross-command created transaction links use new:<zero-based command index>, resolved to stable IDs at approval.
Task 8: complete (commits 63d1054..e744929, tests: npm --prefix front test -- --run src/AgentChat.test.jsx src/App.route.test.jsx src/AppShell.test.jsx →    Duration  1.46s (environment 48%, tests 35%, import 9%, transform 7%))

## receipts

Task 1: complete (commits e744929..7e67101, tests: backend/.venv/bin/python -m unittest discover -s backend/tests -p test_receipt_upload.py → OK)
Ruling (Task 2): Receipt extraction always opens a user-editable review before creating a proposal. The user explicitly selects create or an existing transaction. This keeps unreadable fields and item discrepancies editable, and prevents the model from choosing a duplicate target. Cost: one extra review step even for a complete receipt. Read_receipt returns the cached structured extraction, with no write tools exposed to the extraction model.
Task 2: complete (commits 7e67101..79c0b1e, tests: backend/.venv/bin/python -m unittest discover -s backend/tests -p test_receipt_*.py → OK)
Task 3: complete (commits 79c0b1e..84e5c34, tests: backend/.venv/bin/python -m unittest discover -s backend/tests -p test_receipt_upload.py → OK)
Task 4: complete (commits 84e5c34..932842f, tests: npm --prefix front test -- --run src/ReceiptReview.test.jsx src/AgentChat.test.jsx src/TransactionDetail.test.jsx →    Duration  828ms (environment 64%, tests 17%, import 11%, transform 7%, worker 1%))

## trajectory

Task 1: complete (commits 932842f..41d7edd, tests: backend/.venv/bin/python -m unittest discover -s backend/tests -p test_trajectory*.py → OK)
Ruling (Task 1): Legacy event-only mutations retain the prior automatic time sort for API compatibility. Explicit evidence uses the submitted order and rejects reversed known times. Migration rebuilds all dependent trajectory tables in one transaction, preserving references and all legacy values; evidence defaults are added.
Ruling (Task 2): Unresolved place proposals persist review data without invented coordinates and cannot be approved. Candidate selection binds a target place ID, checks the generation source version, and increments the revision. A full domain snapshot hash conservatively rejects concurrent edits while location selection is pending.
Task 2: complete (commits 41d7edd..71ea21d, tests: backend/.venv/bin/python -m unittest discover -s backend/tests -p test_agent_places.py → OK)
Task 3: complete (commits 71ea21d..1a7a9b4, tests: backend/.venv/bin/python -m unittest discover -s backend/tests -p test_agent_*.py → OK)
Ruling (Task 4): Missing transaction references in the display model show an unavailable-reference note rather than aborting the whole timeline. Pending/unresolved places have no map coordinates. Why: an uninitialized transaction collection and a saved seed can coexist; inventing coordinates or hiding the full day is incorrect. Cost if wrong: upstream missing-data issues are surfaced as per-event notes rather than blocking the view.
Task 4: complete (commits 1a7a9b4..c98643a, tests: npm --prefix front test -- --run src/App.route.test.jsx src/AgentPlaces.test.jsx src/Trajectory.test.jsx src/TrajectoryMap.test.jsx src/lib/trajectory-model.test.js →    Duration  1.39s (environment 57%, tests 26%, import 8%, transform 8%))

## Verification

- Backend: 174/174 tests passed, fake model and mocked HTTP transport.
- Frontend: 84/84 tests passed. Local-port tests rerun outside the sandbox after its EPERM binding restriction.
- Isolated browser: 14 tests passed. Receipts, discrepancy correction, approval, attached bytes; candidate selection, visit order confirmation, saved trajectory display; lost approval response recovery through proposal reload and dashboard refresh.
- Desktop 1440x900 and phone 390x844 screenshots inspected. Dashboard period and financial state appear first.
- Live OpenAI/Geoapify/Mapbox calls were not exercised. Missing-map-token fallback verified.
- Build passes. Existing Mapbox chunk size warning and legacy test-connection ResourceWarnings remain.

## Final review

Final review: fresh gpt-6-astra reviewer, branch 32a268a..c98643a. Regraded: five Important findings stand (manual reference integrity, recovery refresh, place reselection, receipt source visibility, deletion impact disclosure). One Minor remains because ordinary before/after approval still reviews the complete visit order.
Final: minor (deferred): Mixed exact/unknown visit times do not trigger the additional order-confirmation button; the final proposal still shows the order for approval.
Final: Ruling: Live provider quality and model compatibility remain unverified; fake-model/HTTP contract tests cover deterministic behavior, and paid/live calls were not authorized. Cost if wrong: configured models or real responses may need adjustment after setup.
Final: Ruling: Visit time need not equal payment time; arrival can precede payment, so preserve independent evidence. Cost if wrong: a time correction may also require explicit trajectory correction.
Final: Ruling: Local single-user deployment remains the supported scope; no public authentication is added. Cost if wrong: shared or public deployment requires a separate authentication/authorization design.
Final: fixed manual reference integrity — test_manual_edit_cannot_break_fare_or_merchant_evidence RED→GREEN, backend suite 174/174. Manual updates now use the same proposal preview validation as agent edits.
Final: fixed committed-approval recovery refresh — refreshes application data when proposal reload discovers committed approval RED→GREEN; frontend suite 84/84; browser recovery and dashboard check passed.
Final: fixed place reselection — test_reselection_preserves_edits_and_resolves_saved_place_without_duplicates and keeps candidate choices available after selection while allowing approval RED→GREEN; backend 174/174, frontend 84/84, browser candidate reselection passed.
Final: fixed receipt evidence visibility — keeps receipt source and destination context in the final approval and edit card RED→GREEN; frontend 84/84, browser preview byte access passed.
Final: fixed deletion impact disclosure — confirms sample deletion before one request and shows a dedicated confirmation before deleting the selected transaction RED→GREEN; frontend 84/84.
Final verification: backend 174/174, frontend 84/84, isolated browser 14/14, production build passes, git diff --check passes. Desktop and phone dashboard first content and updated review screenshots inspected. No live paid APIs or user DB accessed.


## Reproduce verification

From the isolated worktree root:

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests
npm --prefix front test
npm --prefix front run build
cd front
npm run test:e2e -- --config=playwright.agent.config.cjs tests/e2e/app.spec.cjs
```

The browser configuration starts its own temporary database and fake runner. The receipt fixture is a 4x4 PNG; its tiny preview does not demonstrate real OCR quality. Full-page screenshots capture fixed navigation at its viewport position. Both dashboard viewport screenshots show the selected period and financial state without scrolling.

## Setup

Set server-only `OPENAI_API_KEY`, `KAKEI_AGENT_MODEL`, and optionally `GEOAPIFY_API_KEY` as documented in `backend/README.md`. No real provider keys were configured during implementation. `Trajectory.jsx` now reads saved date/day APIs; the previous production component directly imported the fixed JSON fixture, which was why API changes did not appear.


## Live provider verification follow-up

User supplied the root `.env` and selected `gpt-6-luna`. The ignored local file now includes `KAKEI_AGENT_MODEL=gpt-6-luna`; no credentials are committed or printed. Server startup now loads root `.env`, independently of the current working directory, while preserving exported values. Two environment-loading tests failed before implementation and passed afterward.

- OpenAI `gpt-6-luna`: actual LangChain agent tool call generated a valid transaction proposal in a temporary DB; zero business records existed before approval.
- Image input and structured extraction: a synthetic receipt matched all seven checks (merchant, date, time, total, currency, payment method, item sum). This does not establish accuracy for real-world receipts.
- Geoapify: HTTP 200 with coordinates and attribution. The production adapter returned five candidates after increasing the request timeout to 15 seconds.
- Diagnosis: the identical provider query repeatedly exceeded the original 5-second read timeout; changing only the timeout to 15 seconds succeeded. The turn remains bounded at 60 seconds, and the response limit remains 64 KiB.
- Ruling: increase the Geoapify request timeout from 5 to 15 seconds based on live evidence. Cost: a failed search can take up to 10 seconds longer to report.
- The earlier no-live-provider limitation records the initial implementation phase and is superseded by these targeted smoke checks. Real receipt quality, PDF extraction with this model, and live Mapbox rendering remain unverified.

Final follow-up verification: backend 176/176 passed; git diff --check passed. Worktree `.env` is an ignored symlink to the main checkout `.env`, so local startup uses the same settings without copying secrets.
