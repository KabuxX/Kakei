import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.store import Store
from services.validation import ValidationError

DEFAULTS = {'食費': 60000, '住まい': 90000, '日用品': 25000,
            '交通': 25000, '娯楽': 30000, 'その他': 20000}


class BudgetStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.store = Store(self.path)

    def test_default_and_persistence(self):
        self.assertEqual(self.store.get_budget(), DEFAULTS)
        self.assertEqual(sum(self.store.get_budget().values()), 250000)
        zeros = {name: 0 for name in DEFAULTS}
        self.assertEqual(self.store.update_budget({'categories': zeros}), zeros)
        self.assertEqual(Store(self.path).get_budget(), zeros)
        self.assertFalse(self.store.is_initialized())

    def test_validation_rejects_invalid_input(self):
        for payload in (None, [], {}, {'categories': []},
                        {'categories': {**DEFAULTS, '未知': 1}},
                        {'categories': {'食費': 1}}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                self.store.update_budget(payload)
        for value in (True, '100', -1, 0.5, 1000000000, None):
            with self.subTest(value=value), self.assertRaises(ValidationError) as caught:
                self.store.update_budget({'categories': {**DEFAULTS, '食費': value}})
            self.assertEqual(caught.exception.field, 'categories.食費')
        self.assertEqual(self.store.get_budget(), DEFAULTS)
        self.assertEqual(self.store.update_budget({'categories': {**DEFAULTS, '食費': 999999999}})['食費'], 999999999)

    def test_schema_preserves_saved_values(self):
        self.store.update_budget({'categories': {**DEFAULTS, '食費': 12345}})
        self.assertEqual(Store(self.path).get_budget()['食費'], 12345)
        with self.store._connection() as c:
            c.execute("DELETE FROM category_budgets WHERE category = '交通'")
        self.assertEqual(Store(self.path).get_budget(), {**DEFAULTS, '食費': 12345})

    def test_failed_update_rolls_back_all_categories(self):
        self.store.initialize([{'id': 'fixture', 'title': '給与', 'date': '2026-09-01',
                               'type': 'income', 'category': '収入', 'amount': 100}])
        before = self.store.list_transactions()
        with self.store._connection() as c:
            c.execute("INSERT INTO trajectory_days(date) VALUES ('2026-09-01')")
            c.execute("""CREATE TRIGGER fail_budget BEFORE UPDATE ON category_budgets
                WHEN NEW.category = '住まい' BEGIN SELECT RAISE(ABORT, 'fixture'); END""")
        with self.assertRaises(sqlite3.Error):
            self.store.update_budget({'categories': {name: 100 for name in DEFAULTS}})
        self.assertEqual(self.store.get_budget(), DEFAULTS)
        self.assertEqual(self.store.list_transactions(), before)
        with self.store._connection() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT date FROM trajectory_days')], ['2026-09-01'])
