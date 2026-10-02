import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from store import AlreadyInitialized, NotInitialized, Store
from validation import ValidationError


def income(transaction_id, *, day="2026-09-01", amount=100):
    return {
        "id": transaction_id, "title": "収入", "date": day,
        "type": "income", "category": "収入", "amount": amount,
    }


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "kakei.sqlite3"
        self.store = Store(self.path)

    def test_initialize_empty_survives_reopen(self):
        self.assertFalse(self.store.is_initialized())
        with self.assertRaises(NotInitialized):
            self.store.list_transactions()
        self.assertEqual(self.store.initialize([]), 0)

        reopened = Store(self.path)
        self.assertTrue(reopened.is_initialized())
        self.assertEqual(reopened.list_transactions(), [])
        with self.assertRaises(AlreadyInitialized):
            reopened.initialize([income("late")])
        self.assertEqual(reopened.list_transactions(), [])

    def test_initialize_is_atomic_for_invalid_or_duplicate_ids(self):
        with self.assertRaises(ValidationError):
            self.store.initialize([income("first"), income("bad", day="2026-02-30")])
        self.assertFalse(self.store.is_initialized())
        with self.assertRaises(ValidationError):
            self.store.initialize([income("same"), income("same")])
        self.assertFalse(self.store.is_initialized())
        self.assertEqual(self.store.initialize([income("good")]), 1)
        self.assertEqual([item["id"] for item in self.store.list_transactions()], ["good"])

    def test_competing_initialize_only_one_wins(self):
        first = [income("first-a"), income("first-b")]
        second = [income("second-a", amount=200)]

        def attempt(records):
            try:
                return ("created", self.store.initialize(records))
            except AlreadyInitialized:
                return ("conflict", None)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (first, second)))
        self.assertEqual(sorted(result[0] for result in results), ["conflict", "created"])
        ids = {item["id"] for item in self.store.list_transactions()}
        self.assertIn(ids, ({"first-a", "first-b"}, {"second-a"}))

    def test_create_list_get_delete_and_samples(self):
        self.store.initialize([
            income("sample-0", day="2026-09-03"),
            {"id": "old-1", "title": "旧支出", "date": "2026-09-01",
             "type": "expense", "category": "食費", "amount": 500},
        ])
        created = self.store.create_transaction({
            "title": "買い物", "date": "2026-09-02", "type": "expense",
            "category": "食費", "amount": 300, "merchant": "店",
            "paymentMethod": "cash", "items": [{"name": "パン", "amount": 300}],
        })
        self.assertTrue(created["id"])
        self.assertEqual(self.store.get_transaction(created["id"]), created)
        self.assertEqual([item["id"] for item in self.store.list_transactions()],
                         ["sample-0", created["id"], "old-1"])
        self.assertIsNone(self.store.get_transaction("missing"))
        self.assertFalse(self.store.delete_transaction("missing"))
        self.assertEqual(self.store.delete_samples(), 1)
        self.assertEqual(self.store.delete_samples(), 0)
        self.assertTrue(self.store.delete_transaction(created["id"]))
        self.assertEqual([item["id"] for item in Store(self.path).list_transactions()], ["old-1"])

    def test_sample_deletion_is_case_sensitive(self):
        self.store.initialize([income("sample-remove"), income("Sample-keep")])
        self.assertEqual(self.store.delete_samples(), 1)
        self.assertEqual([item["id"] for item in self.store.list_transactions()], ["Sample-keep"])

    def test_item_round_trip(self):
        items = [{"name": "パン", "amount": 100}, {"name": "パン", "amount": 100}]
        self.store.initialize([
            {"id": "old-expense", "title": "買い物", "date": "2026-09-03",
             "type": "expense", "category": "食費", "amount": 200,
             "merchant": "店", "paymentMethod": "cash", "items": items},
            {"id": "itemless", "title": "買い物", "date": "2026-09-02",
             "type": "expense", "category": "食費", "amount": 300},
            income("income", day="2026-09-01"),
        ])
        created = self.store.create_transaction({
            "title": "買い物2", "date": "2026-09-04", "type": "expense",
            "category": "食費", "amount": 200, "merchant": "店",
            "paymentMethod": "cash", "items": items,
        })
        reopened = Store(self.path)
        self.assertEqual(reopened.get_transaction("old-expense")["items"], items)
        self.assertEqual(reopened.get_transaction(created["id"])["items"], items)
        self.assertEqual(reopened.get_transaction("itemless")["items"], [])
        self.assertNotIn("items", reopened.get_transaction("income"))
        self.assertEqual([row["id"] for row in reopened.list_transactions()],
                         [created["id"], "old-expense", "itemless", "income"])
        with reopened._connection() as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_deletes_cascade_items(self):
        item = [{"name": "食材", "amount": 200}]
        self.store.initialize([
            {"id": "sample-remove", "title": "サンプル", "date": "2026-09-01",
             "type": "expense", "category": "食費", "amount": 200, "items": item},
            {"id": "keep", "title": "保存", "date": "2026-09-02",
             "type": "expense", "category": "食費", "amount": 200, "items": item},
        ])
        created = self.store.create_transaction({
            "title": "削除", "date": "2026-09-03", "type": "expense",
            "category": "食費", "amount": 200, "merchant": "店",
            "paymentMethod": "cash", "items": item,
        })
        self.assertEqual(self.store.delete_samples(), 1)
        self.assertTrue(self.store.delete_transaction(created["id"]))
        with sqlite3.connect(self.path) as connection:
            children = connection.execute(
                "SELECT transaction_id, name, amount FROM transaction_items"
            ).fetchall()
        self.assertEqual(children, [("keep", "食材", 200)])

    def test_item_insert_failure_rolls_back_parent(self):
        self.store.initialize([])
        with sqlite3.connect(self.path) as connection:
            connection.execute("""
                CREATE TRIGGER reject_items BEFORE INSERT ON transaction_items
                BEGIN SELECT RAISE(ABORT, 'item insert failed'); END
            """)
        draft = {"title": "買い物", "date": "2026-09-01", "type": "expense",
                 "category": "食費", "amount": 100, "merchant": "店",
                 "paymentMethod": "cash", "items": [{"name": "パン", "amount": 100}]}
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create_transaction(draft)
        with sqlite3.connect(self.path) as connection:
            parents = connection.execute("SELECT id FROM transactions").fetchall()
            children = connection.execute("SELECT transaction_id FROM transaction_items").fetchall()
        self.assertEqual(parents, [])
        self.assertEqual(children, [])

    def _read_while_deleting(self, read):
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
        original_connection = self.store._connection
        deletes = []

        @contextmanager
        def instrumented_connection():
            with original_connection() as connection:
                def before_statement(sql):
                    if "FROM transaction_items" in sql and not deletes:
                        with sqlite3.connect(self.path) as writer:
                            writer.execute("PRAGMA foreign_keys = ON")
                            writer.execute("DELETE FROM transactions WHERE id = 'during-read'")
                        deletes.append(True)

                connection.set_trace_callback(before_statement)
                try:
                    yield connection
                finally:
                    connection.set_trace_callback(None)

        with patch.object(self.store, "_connection", instrumented_connection):
            result = read()
        self.assertEqual(deletes, [True])
        self.assertIsNone(self.store.get_transaction("during-read"))
        return result

    def test_list_keeps_items_when_deleted_during_read(self):
        items = [{"name": "パン", "amount": 100}]
        self.store.initialize([
            {"id": "during-read", "title": "買い物", "date": "2026-09-01",
             "type": "expense", "category": "食費", "amount": 100, "items": items},
        ])
        records = self._read_while_deleting(self.store.list_transactions)
        self.assertEqual(records[0]["id"], "during-read")
        self.assertEqual(records[0]["items"], items)

    def test_get_keeps_items_when_deleted_during_read(self):
        items = [{"name": "パン", "amount": 100}]
        self.store.initialize([
            {"id": "during-read", "title": "買い物", "date": "2026-09-01",
             "type": "expense", "category": "食費", "amount": 100, "items": items},
        ])
        record = self._read_while_deleting(lambda: self.store.get_transaction("during-read"))
        self.assertEqual(record["id"], "during-read")
        self.assertEqual(record["items"], items)


if __name__ == "__main__":
    unittest.main()
