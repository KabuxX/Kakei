import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.store import Store
from services.validation import ValidationError

class ReadSQLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'db.sqlite3'
        self.store = Store(self.path)
        self.store.initialize([{'id': str(i), 'title': '給与', 'date': '2026-10-01',
                               'type': 'income', 'category': '収入', 'amount': 100} for i in range(120)])

    def run_sql(self, sql):
        from agent.read_sql import run_read_sql
        return run_read_sql(self.path, sql)

    def test_select_from_public_views(self):
        self.assertEqual(self.run_sql("SELECT amount, ';' AS marker FROM agent_transactions WHERE id = '1'"),
                         [{'amount': 100, 'marker': ';'}])
        self.assertEqual(self.run_sql('SELECT sum(amount) AS total FROM agent_transactions'), [{'total': 12000}])
        self.assertEqual(self.run_sql('SELECT count(*) AS total FROM agent_transactions'), [{'total': 120}])

    def test_reject_write_pragma_attach_and_multiple_statements(self):
        for sql in ['DELETE FROM transactions', 'PRAGMA user_version', "ATTACH DATABASE ':memory:' AS x",
                    'SELECT 1; SELECT 2', 'EXPLAIN SELECT 1']:
            with self.subTest(sql=sql), self.assertRaises(ValidationError):
                self.run_sql(sql)
        self.assertEqual(len(self.store.list_transactions()), 120)

    def test_reject_private_table_and_disallowed_function(self):
        for sql in ['SELECT * FROM transactions', 'SELECT * FROM sqlite_master', 'SELECT * FROM receipt_assets',
                    "SELECT load_extension('x')", 'SELECT randomblob(100)',
                    'WITH agent_transactions AS (SELECT * FROM transactions) SELECT * FROM agent_transactions',
                    'SELECT * FROM (WITH agent_transactions AS (SELECT * FROM transactions) SELECT * FROM agent_transactions)']:
            with self.subTest(sql=sql), self.assertRaises(ValidationError):
                self.run_sql(sql)

    def test_limit_rows_bytes_and_runtime(self):
        self.assertEqual(len(self.run_sql('SELECT id FROM agent_transactions')), 100)
        self.assertLessEqual(len(json.dumps(self.run_sql('SELECT title FROM agent_transactions')).encode()), 65536)
        with self.store._connection() as connection:
            connection.execute('UPDATE transactions SET title = ?', ('x' * 1000,))
        bounded = self.run_sql('SELECT title FROM agent_transactions')
        self.assertLess(len(bounded), 100)
        self.assertLessEqual(len(json.dumps(bounded).encode()), 65536)
        started = time.monotonic()
        with self.assertRaises(ValidationError):
            self.run_sql('SELECT sum(a.amount + b.amount + c.amount + d.amount) FROM agent_transactions a CROSS JOIN agent_transactions b CROSS JOIN agent_transactions c CROSS JOIN agent_transactions d')
        self.assertLess(time.monotonic() - started, 3.5)
        with self.assertRaises(ValidationError):
            self.run_sql("SELECT '" + 'x' * 65537 + "'")
