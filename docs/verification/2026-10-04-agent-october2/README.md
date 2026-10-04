# October 2 trajectory: recover model-generated argument errors

The user's request, `2026年10月2日の取引記録によって、軌跡を作って`, failed after two searches. The UI displayed `店舗名から確認できる名称か、その根拠を指定してください。`. `EvidenceResolver` rejects an unsupported brand, branch, or landmark without evidence. Its application `ValidationError` propagated through LangChain's default tool handler, aborting the turn instead of allowing the model to fix its arguments. The rejected arguments were not recorded, so their exact field cannot be established from the original search history.

An asynchronous tool middleware now returns application validation failures to the model as an error `ToolMessage` with `status=invalid_arguments`, the field, and the validation message. The prompt directs the model to correct its arguments using actual evidence, keep the original target, and retain already staged drafts and search results. Existing validation, source binding, approval, eight-tool budget, and deadlines remain enforced. Limits, timeouts, conflicts, cross-thread not-found errors, and unexpected exceptions are not caught by this middleware.

Two regressions exercise the real LangChain graph with a scripted model and synthetic external coordinate data. Both failed with the original uncaught validation exception before implementation:

- A valid search and staged trajectory survive an unsupported landmark request; corrected search arguments produce a reviewable proposal that can be selected and approved on disposable SQLite.
- A missing visit ID is returned as model feedback and corrected within the same turn, without duplicate staging or saving.

Verification:

- `backend/.venv/bin/python -m unittest discover -s backend/tests`: **369 passed**.
- `npx playwright test --config=playwright.agent.config.cjs tests/e2e/geolonia-coordinates.spec.cjs tests/e2e/web-coordinates.spec.cjs tests/e2e/agent-delete.spec.cjs`: **5 passed**, using disposable fixture SQLite.
- `git diff --check`: passed.
- Independent read-only review found no actionable issues and independently passed all 10 runtime tests. Scripted tests establish orchestration, not a guarantee that every production-model response follows the instructions.

After restarting the app, the existing failed October 2 request was retried in the same conversation using its original client message ID. It completed with HTTP 200 in **26.6 seconds**, producing a pending two-visit, one-leg draft with valid, unused visit IDs. Shinjuku Mines Tower has one Geolonia address-coordinate candidate. The Yaesu /S branch remains unlocated with three retained store results; it was not treated as verified. Existing search history was available to this retry, so this is not a fresh-search benchmark. Actual transactions and the saved October 2 trajectory remained unchanged.

The user's Chrome app tab was refreshed and the October 2 conversation opened. The recovered pending proposal is visibly present, and the previous internal error is gone. No candidate was selected or proposal approved on the user's behalf. The Yaesu location still needs resolution before this draft can be saved.

Existing SQLite ResourceWarnings, an asyncio slow-task diagnostic, and Playwright's color-environment warning do not fail these checks. Private live-request logs remain outside the repository.
