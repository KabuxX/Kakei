import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schema import ensure_schema


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "kakei.sqlite3"

    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        self.addCleanup(connection.close)
        return connection

    def legacy_database(self, *, second_items=None):
        connection = self.connect()
        connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO meta VALUES ('initialized', '1')")
        connection.execute("""
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, date TEXT NOT NULL,
                type TEXT NOT NULL, category TEXT NOT NULL, amount INTEGER NOT NULL,
                merchant TEXT, payment_method TEXT, items_json TEXT NOT NULL
            )
        """)
        connection.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("old-expense", "買い物", "2026-09-01", "expense", "食費", 200,
             "店", "cash", json.dumps([{"name": "パン", "amount": 100},
                                         {"name": "パン", "amount": 100}], ensure_ascii=False)),
        )
        if second_items is not None:
            connection.execute(
                "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("old-income", "給与", "2026-09-02", "income", "収入", 500,
                 None, None, second_items),
            )
        connection.commit()
        return connection

    def test_fresh_schema_has_child_table(self):
        connection = self.connect()
        ensure_schema(connection)
        connection.commit()

        transaction_columns = {row[1] for row in connection.execute("PRAGMA table_info(transactions)")}
        foreign_key_delete_actions = {row[6] for row in connection.execute("PRAGMA foreign_key_list(transaction_items)")}
        item_columns = {row[1] for row in connection.execute("PRAGMA table_info(transaction_items)")}
        self.assertNotIn("items_json", transaction_columns)
        self.assertEqual(item_columns, {"transaction_id", "position", "name", "amount"})
        self.assertIn("CASCADE", foreign_key_delete_actions)

    def test_legacy_migration_preserves_items_and_marker(self):
        connection = self.legacy_database(second_items="[]")
        ensure_schema(connection)
        connection.commit()

        items = connection.execute(
            "SELECT transaction_id, position, name, amount FROM transaction_items ORDER BY position"
        ).fetchall()
        initialized_value = connection.execute("SELECT value FROM meta WHERE key = 'initialized'").fetchone()[0]
        parent = connection.execute("SELECT title, merchant, payment_method FROM transactions WHERE id = 'old-expense'").fetchone()
        self.assertEqual(items, [("old-expense", 0, "パン", 100), ("old-expense", 1, "パン", 100)])
        self.assertEqual(initialized_value, "1")
        self.assertEqual(parent, ("買い物", "店", "cash"))
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 2)

        ensure_schema(connection)
        connection.commit()
        items_after_second_open = connection.execute(
            "SELECT transaction_id, position, name, amount FROM transaction_items ORDER BY position"
        ).fetchall()
        self.assertEqual(items_after_second_open, items)

    def test_migration_failure_rolls_back(self):
        connection = self.legacy_database(second_items="{broken")
        original_rows = connection.execute("SELECT * FROM transactions ORDER BY id").fetchall()

        with self.assertRaises(ValueError):
            ensure_schema(connection)
        connection.rollback()

        original_columns = {row[1] for row in connection.execute("PRAGMA table_info(transactions)")}
        rows_after_failure = connection.execute("SELECT * FROM transactions ORDER BY id").fetchall()
        self.assertIn("items_json", original_columns)
        self.assertEqual(original_rows, rows_after_failure)
        self.assertIsNone(connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'transaction_items'"
        ).fetchone())


if __name__ == "__main__":
    unittest.main()
