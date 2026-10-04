import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.app import create_app

DEFAULTS = {'食費': 60000, '住まい': 90000, '日用品': 25000,
            '交通': 25000, '娯楽': 30000, 'その他': 20000}
HEADERS = {'Host': 'localhost:8765', 'Origin': 'http://localhost:8765'}


class BudgetAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        front = root / 'front'
        front.mkdir()
        (front / 'index.html').write_text('fixture')
        self.app = create_app(root / 'test.sqlite3', front)
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def test_get_put_before_transaction_initialization(self):
        response = self.client.get('/api/budget', headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'categories': DEFAULTS})
        changed = {'categories': {**DEFAULTS, '食費': 70000}}
        response = self.client.put('/api/budget', headers=HEADERS, json=changed)
        self.assertEqual((response.status_code, response.json()), (200, changed))
        self.assertEqual(self.client.get('/api/budget', headers=HEADERS).json(), changed)
        self.assertFalse(self.app.state.store.is_initialized())
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_rejected_put_does_not_change_budget(self):
        response = self.client.put('/api/budget', headers=HEADERS,
                                   json={'categories': {**DEFAULTS, '食費': -1}})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['field'], 'categories.食費')
        self.assertEqual(self.client.get('/api/budget', headers=HEADERS).json(), {'categories': DEFAULTS})

    def test_access_and_database_errors(self):
        for headers in ({'Host': 'localhost:8765'},
                        {**HEADERS, 'Origin': 'https://other.example'},
                        {**HEADERS, 'Host': 'other.example'}):
            self.assertEqual(self.client.put('/api/budget', headers=headers,
                             json={'categories': DEFAULTS}).status_code, 403)
        with patch.object(self.app.state.store, 'get_budget', side_effect=sqlite3.OperationalError('fixture')):
            response = self.client.get('/api/budget', headers=HEADERS)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()['error']['code'], 'database_error')

    def test_body_and_method_validation(self):
        headers = {**HEADERS, 'Content-Type': 'application/json'}
        self.assertEqual(self.client.put('/api/budget', headers=headers, content='{').status_code, 400)
        self.assertEqual(self.client.put('/api/budget', headers=headers, content='x' * 16385).status_code, 413)
        self.assertEqual(self.client.post('/api/budget', headers=HEADERS, json={}).status_code, 405)
