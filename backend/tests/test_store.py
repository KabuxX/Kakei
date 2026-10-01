import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
