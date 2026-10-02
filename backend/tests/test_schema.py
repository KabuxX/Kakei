import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.schema import ensure_schema


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

    def current_database(self):
        connection = self.connect()
        connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO meta VALUES ('initialized', '1')")
        connection.execute("""
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, date TEXT NOT NULL,
                type TEXT NOT NULL, category TEXT NOT NULL, amount INTEGER NOT NULL,
                merchant TEXT, payment_method TEXT
            )
        """)
        connection.executemany("""
            INSERT INTO transactions
                (id, title, date, type, category, amount, merchant, payment_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            ("c", "C", "2026-09-01", "income", "収入", 100, None, None),
            ("a", "A", "2026-09-01", "income", "収入", 100, None, None),
            ("b", "B", "2026-09-01", "income", "収入", 100, None, None),
            ("timed", "時刻あり", "2026-09-02T10:20", "income", "収入", 100, None, None),
        ])
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
        self.assertIn("time_estimated", transaction_columns)
        self.assertEqual(item_columns, {"transaction_id", "position", "name", "amount"})
        self.assertIn("CASCADE", foreign_key_delete_actions)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("""
                INSERT INTO transactions
                    (id, title, date, type, category, amount, time_estimated)
                VALUES ('invalid-estimate', 'x', '2026-09-01T12:00', 'income', '収入', 1, 2)
            """)

    def test_current_schema_backfills_date_only_rows(self):
        connection = self.current_database()

        ensure_schema(connection)
        connection.commit()

        rows = connection.execute(
            "SELECT id, date, time_estimated FROM transactions ORDER BY id"
        ).fetchall()
        self.assertEqual(rows, [
            ("a", "2026-09-01T11:30", 1),
            ("b", "2026-09-01T15:00", 1),
            ("c", "2026-09-01T18:30", 1),
            ("timed", "2026-09-02T10:20", 0),
        ])
        self.assertEqual(connection.execute(
            "SELECT value FROM meta WHERE key = 'initialized'"
        ).fetchone()[0], "1")

        ensure_schema(connection)
        connection.commit()
        self.assertEqual(connection.execute(
            "SELECT id, date, time_estimated FROM transactions ORDER BY id"
        ).fetchall(), rows)

    def test_fresh_schema_has_trajectory_tables(self):
        connection = self.connect()
        ensure_schema(connection)
        connection.commit()

        table_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({
            "trajectory_places", "trajectory_days", "trajectory_events",
            "trajectory_legs", "trajectory_leg_via_places",
        } <= table_names)
        connection.execute("INSERT INTO trajectory_days (date) VALUES ('2026-09-01')")
        connection.execute("""
            INSERT INTO trajectory_places (id, name, address, longitude, latitude, source_url)
            VALUES ('place', '店', '東京都', 139.7, 35.6, 'https://example.com')
        """)
        for position in (0, 1):
            connection.execute("""
                INSERT INTO trajectory_events (id, day_date, position, time, place_id)
                VALUES (?, '2026-09-01', ?, '09:00', 'place')
            """, (f"event-{position}", position))
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("""
                INSERT INTO trajectory_events (id, day_date, position, time, place_id)
                VALUES ('duplicate-position', '2026-09-01', 0, '10:00', 'place')
            """)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("""
                INSERT INTO trajectory_events (id, day_date, position, time, place_id)
                VALUES ('unknown-place', '2026-09-01', 2, '10:00', 'missing')
            """)
        connection.execute("""
            INSERT INTO trajectory_legs (day_date, position, from_event_id, to_event_id, has_via_places)
            VALUES ('2026-09-01', 0, 'event-0', 'event-1', 1)
        """)
        connection.execute("""
            INSERT INTO trajectory_leg_via_places (day_date, leg_position, via_position, place_id)
            VALUES ('2026-09-01', 0, 0, 'place')
        """)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("""
                INSERT INTO trajectory_leg_via_places (day_date, leg_position, via_position, place_id)
                VALUES ('2026-09-01', 0, 0, 'place')
            """)
        connection.execute("DELETE FROM trajectory_days WHERE date = '2026-09-01'")
        for table in ("trajectory_events", "trajectory_legs", "trajectory_leg_via_places"):
            self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_existing_current_schema_gains_trajectory_tables(self):
        connection = self.connect()
        ensure_schema(connection)
        connection.commit()
        for table in ("trajectory_leg_via_places", "trajectory_legs", "trajectory_events", "trajectory_days", "trajectory_places"):
            connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.commit()

        ensure_schema(connection)
        connection.commit()
        table_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertIn("trajectory_places", table_names)
        self.assertIn("trajectory_leg_via_places", table_names)

    def test_legacy_migration_keeps_trajectory_schema_and_transactions(self):
        connection = self.legacy_database()
        ensure_schema(connection)
        connection.commit()

        table_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({"trajectory_places", "trajectory_days", "trajectory_events", "trajectory_legs", "trajectory_leg_via_places"} <= table_names)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM transaction_items").fetchone()[0], 2)
        self.assertEqual(connection.execute("SELECT value FROM meta WHERE key = 'initialized'").fetchone()[0], "1")

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

    def test_legacy_migration_backfills_datetime_and_preserves_items(self):
        connection = self.legacy_database(second_items="[]")

        ensure_schema(connection)
        connection.commit()

        rows = connection.execute(
            "SELECT id, date, time_estimated FROM transactions ORDER BY id"
        ).fetchall()
        self.assertEqual(rows, [
            ("old-expense", "2026-09-01T12:00", 1),
            ("old-income", "2026-09-02T12:00", 1),
        ])
        self.assertEqual(connection.execute(
            "SELECT transaction_id, position, name, amount FROM transaction_items ORDER BY position"
        ).fetchall(), [
            ("old-expense", 0, "パン", 100),
            ("old-expense", 1, "パン", 100),
        ])
        self.assertEqual(connection.execute(
            "SELECT value FROM meta WHERE key = 'initialized'"
        ).fetchone()[0], "1")

    def test_migration_failure_rolls_back(self):
        connection = self.legacy_database(second_items="{broken")
        original_rows = connection.execute("SELECT * FROM transactions ORDER BY id").fetchall()

        with self.assertRaises(ValueError):
            ensure_schema(connection)
        connection.rollback()

        original_columns = {row[1] for row in connection.execute("PRAGMA table_info(transactions)")}
        rows_after_failure = connection.execute("SELECT * FROM transactions ORDER BY id").fetchall()
        self.assertIn("items_json", original_columns)
        self.assertNotIn("time_estimated", original_columns)
        self.assertEqual(original_rows, rows_after_failure)
        self.assertEqual(connection.execute(
            "SELECT date FROM transactions WHERE id = 'old-expense'"
        ).fetchone()[0], "2026-09-01")
        self.assertIsNone(connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'transaction_items'"
        ).fetchone())


if __name__ == "__main__":
    unittest.main()
