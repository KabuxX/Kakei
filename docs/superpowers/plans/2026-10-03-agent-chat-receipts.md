# Agent Chat Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user upload a receipt, review an extracted transaction create or edit proposal, approve it, and reopen the saved receipt from that transaction.

**Architecture:** Extend the working Agent Chat from the [foundation plan](2026-10-03-agent-chat-foundation.md). FastAPI validates uploads and stores bounded BLOBs in SQLite; a receipt reader presents only the current file to the OpenAI model, while matching and transaction validation stay deterministic. Approval attaches the receipt and applies the transaction in one database transaction.

**Tech Stack:** Python 3.14, FastAPI `UploadFile`, SQLite, Pillow, pypdf, LangChain, `langchain-openai`, React 19, Vitest, `unittest`, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-agent-chat-design.md`

## Global Constraints

- Depends on the completed foundation plan and its `AgentStore`, `AgentCommand`, `AgentRunner.run_turn`, `Store.apply_agent_proposal`, and Agent Chat HTTP contracts.
- Accept exactly one JPEG, PNG, WebP, or PDF per upload; limit the full file to 10 MiB and PDF to 3 pages. Check bytes and document structure, not filename alone.
- Keep uploaded bytes in local SQLite, attach to a transaction only on approval, and delete unattached bytes on rejection, expiry after 24 hours, or thread deletion. Delete unreferenced attachments when a transaction is deleted.
- Expose `read_receipt` as a read tool. Receipt text is untrusted data; it cannot instruct tool use. Never log file bytes, extracted text, or API keys.
- Show duplicate candidates by SHA-256 and nearby date, merchant, and amount; the user chooses create or target transaction before an edit is approved.
- Missing required fields and mismatch between item sum and total require user correction. Tax or discounts are never fabricated as balancing line items.
- All business writes still require a versioned, explicit approval and use the foundation's atomic, idempotent apply path. Build and commit `front/dist/` for UI changes.

## Review Focus

- A valid image renamed `.pdf`, a corrupt image, or a polyglot file is rejected by content inspection before it reaches the model (Task 1).
- An encrypted, corrupt, or four-page PDF returns a clear validation error and never creates a pending asset (Task 1).
- A receipt without a readable payment method, date, or total produces a question or editable incomplete proposal rather than a guessed transaction (Task 2).
- An extracted discount that makes item sum differ from total presents the discrepancy and saves only corrected items or an empty item list (Tasks 2 and 4).
- Upload retry of the same bytes is detected, while a lost approval response returns the original transaction and receipt IDs without duplicating either (Tasks 1 and 3).

## File map

- `backend/services/receipt_validation.py`: byte limits, signature and parser checks, MIME, PDF page count.
- `backend/db/receipt_store.py`, `backend/db/schema.py`: asset rows, SHA-256, lifecycle, transaction links.
- `backend/api/receipts.py`, `backend/api/app.py`: upload, attachment list, authenticated local file response.
- `backend/agent/receipt.py`: structured extraction and the `read_receipt` tool's file input.
- `backend/services/receipt_matching.py`: duplicate and near-match candidates.
- `backend/agent/runtime.py`, `backend/db/store.py`, `backend/services/agent_changes.py`: receipt context and atomic attachment.
- `front/src/AgentChat.jsx`, `front/src/lib/agent-api.js`, `front/src/TransactionDetail.jsx`: upload, discrepancy and duplicate review, saved receipt access.
- `backend/requirements.txt`, `backend/API.md`, `backend/README.md`, `front/README.md`, `front/dist/`: dependencies, contracts, configuration, shipped UI.

---

### Task 1: Validated upload and pending asset lifecycle

**Files:** Create `backend/services/receipt_validation.py`, `backend/db/receipt_store.py`, `backend/api/receipts.py`, `backend/tests/test_receipt_upload.py`; modify `backend/db/schema.py`, `backend/api/app.py`, `backend/requirements.txt`, `backend/API.md`.

**Interfaces:** Produce `validate_receipt(data: bytes, filename: str | None) -> ReceiptFile` with `data`, `mime_type`, `sha256`, and `page_count`; `ReceiptStore(db_path: Path)` with `create_pending(thread_id: str, file: ReceiptFile) -> dict`, `get_asset(receipt_id: str) -> dict | None`, `expire_pending(now: datetime) -> int`. `POST /api/agent/threads/{id}/receipts` returns `{id, mimeType, sha256, duplicateReceiptIds}`; `GET /api/agent/threads/{id}/receipts/{receiptId}` streams that thread's pending preview; `GET /api/receipts/{id}` streams approved assets only. Both file routes use the stored MIME type and `Cache-Control: no-store`.

- [ ] **Step 1: Write failing tests.** `test_upload_png_and_pdf`, `test_reject_spoofed_corrupt_encrypted_and_four_page_files`, `test_10_mib_limit_does_not_store_asset`, `test_duplicate_hash_reports_existing_receipt`, and `test_pending_expiry_and_thread_delete`. Assert a pending preview is available only through its thread, pending bytes cannot be fetched through the approved receipt route, valid PDFs have at most 3 pages, and retrying identical bytes in the same thread returns the pending ID without storing a second BLOB.
- [ ] **Step 2: Run the focused tests; expect failure.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_receipt_upload.py' -v`.
- [ ] **Step 3: Implement validation, persistence, and HTTP.** Read `UploadFile` in bounded chunks; use Pillow to verify images and pypdf to parse unencrypted PDFs, then check actual format and page count. Store the exact accepted bytes and SHA-256 in SQLite; use the existing Host/Origin guards and error envelope. Invoke pending cleanup on upload and thread/proposal lifecycle paths.
- [ ] **Step 4: Rerun focused and schema tests; expect PASS.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_receipt_upload.py' -v` and `-p 'test_schema.py' -v`.
- [ ] **Step 5: Commit.** Stage the listed files; `git commit -m "feat: validate and store pending receipts"`.

### Task 2: Extraction and duplicate matching

**Files:** Create `backend/agent/receipt.py`, `backend/services/receipt_matching.py`, `backend/tests/test_receipt_extraction.py`, `backend/tests/test_receipt_matching.py`; modify `backend/agent/runtime.py`, `backend/agent/contracts.py`.

**Interfaces:** Produce `ReceiptCandidate` with nullable `merchant`, `date`, `time`, `total`, `currency`, `payment_method`, `items`, `tax`, `discount`, and `unreadable_fields`; `extract_receipt(file: ReceiptFile, model: BaseChatModel) -> ReceiptCandidate`; `find_receipt_matches(connection: sqlite3.Connection, candidate: ReceiptCandidate, sha256: str) -> list[dict]`. `AgentRunner.run_turn(..., receipt_id: str | None = None)` loads only that thread's receipt, registers `read_receipt`, and returns extraction plus match evidence with a staged `transaction.create` or `transaction.update` command only when required fields are complete.

- [ ] **Step 1: Write failing tests.** `test_image_and_pdf_model_blocks`, `test_missing_required_fields_do_not_stage_valid_transaction`, `test_receipt_text_cannot_instruct_tools`, `test_hash_and_near_match_candidates`, and `test_discount_mismatch_requires_item_correction`. Assert a missing date, time, total, or payment method is not invented, a mismatched item list is not silently balanced, and an existing match is presented without selecting it as edit target automatically.
- [ ] **Step 2: Run the focused tests; expect failure.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_receipt_*.py' -v`.
- [ ] **Step 3: Implement extraction and matching.** Supply image or PDF bytes as supported multimodal content blocks to the configured model; validate its structured response before using it. Pass only the current receipt and necessary transaction matches, with receipt content marked as data. Match exact SHA-256 first, then transactions within 3 calendar days with equal amount and NFKC/casefold merchant match or containment; keep incomplete candidates in the thread response for user correction.
- [ ] **Step 4: Rerun focused and agent runtime tests; expect PASS.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_receipt_*.py' -v` and `-p 'test_agent_runtime.py' -v`.
- [ ] **Step 5: Commit.** Stage the listed files; `git commit -m "feat: extract receipt candidates and find matches"`.

### Task 3: Atomic receipt attachment and retrieval by transaction

**Files:** Modify `backend/db/receipt_store.py`, `backend/db/store.py`, `backend/db/agent_store.py`, `backend/services/agent_changes.py`, `backend/api/receipts.py`, `backend/api/transactions.py`, `backend/tests/test_agent_changes.py`, `backend/tests/test_receipt_upload.py`, `backend/API.md`.

**Interfaces:** Extend `AgentCommand.data` for transaction commands with `receiptIds: list[str]`; produce `ReceiptStore.attach(connection: sqlite3.Connection, receipt_ids: list[str], transaction_id: str, thread_id: str) -> None` and `ReceiptStore.list_for_transaction(transaction_id: str) -> list[dict]`. `GET /api/transactions/{id}/receipts` returns metadata; `GET /api/receipts/{id}` returns approved bytes. `Store.apply_agent_proposal` attaches inside the same `BEGIN IMMEDIATE` as its transaction and audit update.

- [ ] **Step 1: Write failing tests.** `test_approval_attaches_receipt_once`, `test_edit_attaches_to_selected_existing_transaction`, `test_reject_and_expire_discard_unattached_bytes`, `test_transaction_delete_removes_unreferenced_receipt`, and `test_rollback_keeps_pending_receipt`. Assert approval retry returns the same IDs, a wrong-thread receipt ID fails, and no attachment is visible after a failed apply.
- [ ] **Step 2: Run focused tests; expect failure.** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_changes.py' -v` and `-p 'test_receipt_upload.py' -v`.
- [ ] **Step 3: Extend the shared approval transaction.** Validate asset ownership, pending status, and proposal revision before applying; attach after obtaining the created or updated transaction ID, then persist the approval result and commit together. Remove unreferenced assets on transaction deletion and pending assets on rejection, expiry, and thread deletion.
- [ ] **Step 4: Rerun focused and full backend tests; expect PASS.** `backend/.venv/bin/python -m unittest discover -s backend/tests -v`.
- [ ] **Step 5: Commit.** Stage the listed files; `git commit -m "feat: attach approved receipts to transactions"`.

### Task 4: Receipt review in Agent Chat and transaction detail

**Files:** Modify `front/src/AgentChat.jsx`, `front/src/lib/agent-api.js`, `front/src/TransactionDetail.jsx`, `front/src/AgentChat.test.jsx`, `front/src/TransactionDetail.test.jsx`, `front/tests/e2e/app.spec.cjs`, `front/README.md`, `front/dist/`.

**Interfaces:** `uploadReceipt(threadId: string, file: File) -> Promise<ReceiptMetadata>`, `listTransactionReceipts(transactionId: string) -> Promise<ReceiptMetadata[]>`; review card exposes extraction gaps, duplicate choices (`create` or a specific transaction ID), before/after values, image/PDF preview, item discrepancy, and revisioned approve/reject actions.

- [ ] **Step 1: Write failing UI tests.** `test_upload_and_preview_receipt`, `test_duplicate_requires_explicit_target_selection`, `test_missing_field_and_item_discrepancy`, `test_approved_receipt_opens_from_transaction`, and `test_keyboard_upload_review_approve`. Use a fake backend in the browser test and assert no approval occurs from Enter in the composer or file picker.
- [ ] **Step 2: Run focused Vitest; expect failure.** `cd front && npm test -- src/AgentChat.test.jsx src/TransactionDetail.test.jsx`.
- [ ] **Step 3: Implement the review UI.** Follow the approved in-product hierarchy, `DESIGN.md`, `MASTER.md`, and `ui-ux-pro-max`. Show upload and model progress, validation errors, duplicates and missing fields; send corrected proposals through `PUT` before enabling approval. Render an approved receipt from its server URL with an accessible download/open link.
- [ ] **Step 4: Run Vitest, isolated browser test, and build; expect PASS.** `cd front && npm test`, `npm run build`, then `npm run test:e2e -- --config=playwright.agent.config.cjs tests/e2e/app.spec.cjs`; extend the fake-runner temporary-DB server from the foundation plan for receipt cases. Inspect desktop and phone upload/review flows. Run `git diff --check`.
- [ ] **Step 5: Commit.** Stage the listed files; `git commit -m "feat: review receipt changes in agent chat"`.
