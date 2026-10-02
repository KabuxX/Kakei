# Transaction Items Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move expense items from `transactions.items_json` into a child SQLite table while preserving existing data and the current API.

**Architecture:** A focused schema module creates new databases and migrates legacy databases atomically. `Store` writes and reads parent and child rows in one database transaction, then assembles the existing API shape.

**Tech Stack:** Python 3.14, standard-library `sqlite3`, FastAPI, `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-02-transaction-items-table-design.md`

## Global Constraints

- Keep the UI and HTTP endpoints unchanged; expense responses retain `items: [{name, amount}, ...]` in input order.
- Keep transaction order `date DESC, id DESC`; income responses have no `items` field.
- Preserve all valid legacy records and the `meta.initialized` marker; migration runs once and rolls back completely on failure.
- Use `transaction_items(transaction_id, position, name, amount)` with primary key `(transaction_id, position)` and `ON DELETE CASCADE`.
- Continue validating writes with `normalize_transaction`; items are optional, and a nonempty item list must sum to the transaction amount.
- Run API tests with `KAKEI_DB_PATH` set to a disposable path so importing `backend/server.py` does not migrate the user's default DB.

## Review Focus

- A malformed JSON value after a valid legacy row leaves the old schema and every row intact: Task 1 `test_migration_failure_rolls_back`.
- Duplicate names and equal amounts keep their separate positions: Task 1 `test_legacy_migration_preserves_items_and_marker`, Task 2 `test_item_round_trip`.
- Expense records with no items and income records do not acquire phantom children: Task 2 `test_item_round_trip`.
- Reopening a migrated database does not duplicate children: Task 1 `test_legacy_migration_preserves_items_and_marker`.
- Deleting sample records removes only their children: Task 2 `test_deletes_cascade_items`.

## File Structure

- Create `backend/schema.py`: new schema creation and one-time legacy migration; expose `ensure_schema(connection: sqlite3.Connection) -> None`.
- Create `backend/tests/test_schema.py`: direct tests of fresh schema, migration, and rollback.
- Modify `backend/store.py`: enable foreign keys on each connection, call `ensure_schema`, write/read child rows, preserve public Store methods.
- Modify `backend/tests/test_store.py`: storage round trips, write rollback, and cascade checks.
- Modify `backend/tests/test_server.py`: verify API responses containing ordered items through the new storage.

---

### Task 1: Create and migrate the schema

**Files:**
- Create: `backend/schema.py`
- Create: `backend/tests/test_schema.py`

**Interfaces:**
- Consumes: an open `sqlite3.Connection` whose `PRAGMA foreign_keys` is `ON`.
- Produces: `ensure_schema(connection: sqlite3.Connection) -> None`, called before the Store reads or writes. It starts `BEGIN IMMEDIATE` and leaves commit/rollback to the caller. On malformed legacy items it raises `ValueError`.

- [ ] **Step 1: Write failing schema tests.** Add `test_fresh_schema_has_child_table`, `test_legacy_migration_preserves_items_and_marker`, and `test_migration_failure_rolls_back` to `backend/tests/test_schema.py`. Use temporary DBs and direct SQL to construct the legacy schema. Assert `PRAGMA table_info(transactions)` excludes `items_json`; `PRAGMA foreign_key_list(transaction_items)` has `ON DELETE CASCADE`; a legacy expense with two identical items creates positions 0 and 1; `meta.initialized` remains `1`; a second `ensure_schema` call adds no rows; and malformed JSON in a later row raises `ValueError` while `items_json` and all old rows remain after rollback.

  ```python
  def test_fresh_schema_has_child_table(self):
      self.assertNotIn("items_json", transaction_columns)
      self.assertIn("CASCADE", foreign_key_delete_actions)

  def test_legacy_migration_preserves_items_and_marker(self):
      self.assertEqual(items, [("old-expense", 0, "パン", 100), ("old-expense", 1, "パン", 100)])
      self.assertEqual(initialized_value, "1")
      self.assertEqual(items_after_second_open, items)

  def test_migration_failure_rolls_back(self):
      with self.assertRaises(ValueError):
          ensure_schema(connection)
      connection.rollback()
      self.assertIn("items_json", original_columns)
      self.assertEqual(original_rows, rows_after_failure)
  ```

- [ ] **Step 2: Verify the tests fail.** Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_schema.py -v`. Expected: import failure for missing `schema` module.

- [ ] **Step 3: Implement `ensure_schema(connection: sqlite3.Connection) -> None` in `backend/schema.py`.** Under `BEGIN IMMEDIATE`, create `meta`; inspect `PRAGMA table_info(transactions)`. For a new DB create `transactions` without `items_json` and `transaction_items` with the spec's key, checks, and cascade. For a legacy DB, parse every `items_json` before changing tables; require a list of `{name: nonblank str, amount: int from 1 to 999999999}` (reject bool), and require a nonempty list only on expenses and its sum to equal parent `amount`. Rebuild `transactions` without `items_json`, create `transaction_items`, and insert children in list order. Preserve all other parent columns and `meta`. Do not commit internally.

- [ ] **Step 4: Verify the tests pass.** Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_schema.py -v`. Expected: all schema tests pass.

- [ ] **Step 5: Commit this independently tested schema unit.** Stage only `backend/schema.py` and `backend/tests/test_schema.py`; commit as `Add transaction items schema migration`.

### Task 2: Use child rows in storage and preserve API behavior

**Files:**
- Modify: `backend/store.py:21-151`
- Modify: `backend/tests/test_store.py:20-94`
- Modify: `backend/tests/test_server.py:63-93`

**Interfaces:**
- Consumes: `schema.ensure_schema(connection: sqlite3.Connection) -> None` from Task 1, with the same connection used by Store.
- Produces: unchanged public `Store` methods and unchanged JSON endpoints. Private `_insert(connection, record)` writes the parent and ordered items; `_record(row, items: list[dict]) -> dict` assembles the response.

- [ ] **Step 1: Write failing storage tests.** Add `test_item_round_trip`, `test_deletes_cascade_items`, and `test_item_insert_failure_rolls_back_parent` to `backend/tests/test_store.py`. Assert duplicate items keep their order across `initialize`, `create_transaction`, `list_transactions`, `get_transaction`, and reopen; itemless expense returns `items: []`; income has no `items`; both delete methods leave zero children for deleted transactions and preserve unrelated children. For write rollback, create a SQLite trigger that aborts a `transaction_items` insert, assert `create_transaction` raises `sqlite3.IntegrityError`, and assert neither the parent nor child was saved. Assert `PRAGMA foreign_keys` is `1` on Store connections.

  ```python
  def test_item_round_trip(self):
      self.assertEqual(reopened.get_transaction(expense_id)["items"], expected_ordered_items)
      self.assertEqual(reopened.get_transaction(itemless_id)["items"], [])
      self.assertNotIn("items", reopened.get_transaction(income_id))

  def test_deletes_cascade_items(self):
      self.assertEqual(children_for_deleted_ids, [])
      self.assertEqual(children_for_kept_id, expected_ordered_items)

  def test_item_insert_failure_rolls_back_parent(self):
      with self.assertRaises(sqlite3.IntegrityError):
          self.store.create_transaction(draft)
      self.assertEqual(parent_rows_after_failure, [])
      self.assertEqual(child_rows_after_failure, [])
  ```

- [ ] **Step 2: Write a failing API contract test.** In `backend/tests/test_server.py`, add `test_ordered_items_api_round_trip`: initialize an expense with two equal items, GET list and detail with identical ordered arrays, POST another expense with two items, and confirm the POST response and subsequent GET have the same shape. Use the existing request helper and a temporary DB.

  ```python
  def test_ordered_items_api_round_trip(self):
      self.assertEqual(list_record["items"], expected_ordered_items)
      self.assertEqual(detail_record["items"], expected_ordered_items)
      self.assertEqual(created_record["items"], created_items)
      self.assertEqual(reloaded_record["items"], created_items)
  ```

- [ ] **Step 3: Verify new tests fail.** Run `KAKEI_DB_PATH=/private/tmp/kakei-items-plan-test.sqlite3 backend/.venv/bin/python -m unittest discover -s backend/tests -v`. Expected: failures because `Store` still uses `items_json` on the new schema.

- [ ] **Step 4: Connect Store to the new schema.** In `Store.__init__`, replace inline DDL with `ensure_schema(connection)`. In `_connection`, execute `PRAGMA foreign_keys = ON` before yielding. Change `_insert` to insert the parent then `(transaction_id, position, name, amount)` children on the same connection. Change `_record` to accept an ordered item list. For `list_transactions`, read ordered parents and all child rows, group children by transaction ID, then assemble records. For `get_transaction`, select child rows with `ORDER BY position`. Keep `initialize`, `create_transaction`, and both delete methods' public behavior and transaction boundaries.

- [ ] **Step 5: Verify the backend.** Run `KAKEI_DB_PATH=/private/tmp/kakei-items-plan-test.sqlite3 backend/.venv/bin/python -m unittest discover -s backend/tests -v`. Expected: all backend tests pass, including existing API and validation tests.

- [ ] **Step 6: Commit the storage and API tests.** Stage only `backend/store.py`, `backend/tests/test_store.py`, and `backend/tests/test_server.py`; commit as `Store transaction items in child rows`.
