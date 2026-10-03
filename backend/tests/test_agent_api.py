import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api.app import create_app
from test_agent_changes import DRAFT

class FakeRunner:
    calls = 0
    async def run_turn(self, thread_id, messages, receipt_id=None, *, turn_context=None):
        self.calls += 1
        return {'text': '保存前に確認してください。', 'commands': [{'kind': 'transaction.create', 'identity': {}, 'data': DRAFT}]}

class AgentAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.runner = FakeRunner()
        self.app = create_app(root / 'db', root, runner_factory=lambda store: self.runner)
        self.app.state.store.initialize([])
        self.client = TestClient(self.app, base_url='http://localhost:8765', headers={'Origin': 'http://localhost:8765'})
        self.addCleanup(self.client.close)

    def test_thread_and_proposal_http_lifecycle(self):
        thread = self.client.post('/api/agent/threads', json={}).json()['thread']
        url = '/api/agent/threads/' + thread['id']
        body = {'clientMessageId': 'one', 'text': '給与を記録'}
        result = self.client.post(url + '/messages', json=body)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.client.post(url + '/messages', json=body).json(), result.json())
        self.assertEqual(self.runner.calls, 1)
        self.assertEqual(self.app.state.store.list_transactions(), [])
        proposal = result.json()['proposal']; purl = '/api/agent/proposals/' + proposal['id']
        revised = self.client.put(purl, json={'revision': 1, 'commands': proposal['commands']})
        self.assertEqual(revised.json()['proposal']['revision'], 2)
        self.assertEqual(self.client.post(purl + '/approve', json={'revision': 1}).status_code, 409)
        first = self.client.post(purl + '/approve', json={'revision': 2})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), self.client.post(purl + '/approve', json={'revision': 2}).json())
        self.assertEqual(len(self.app.state.store.list_transactions()), 1)
        self.assertEqual(len(self.client.get(url).json()['thread']['messages']), 2)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_origin_and_malformed_body_guards(self):
        self.assertEqual(self.client.post('/api/agent/threads', json={}, headers={'Origin': 'https://evil.example'}).status_code, 403)
        thread = self.client.post('/api/agent/threads', json={}).json()['thread']['id']
        self.assertEqual(self.client.post(f'/api/agent/threads/{thread}/messages', json=[]).status_code, 400)
        self.assertEqual(self.client.post(f'/api/agent/threads/{thread}/messages', json={'clientMessageId':'x','text':''}).status_code, 400)

    def test_missing_model_key_reports_unavailable(self):
        with patch.dict('os.environ', {}, clear=True):
            app = create_app(Path(self.temp.name)/'missing', Path(self.temp.name))
            app.state.store.initialize([])
            with TestClient(app, base_url='http://localhost:8765', headers={'Origin':'http://localhost:8765'}) as client:
                self.assertFalse(client.get('/api/agent/status').json()['available'])
                thread = client.post('/api/agent/threads', json={}).json()['thread']['id']
                reply = client.post(f'/api/agent/threads/{thread}/messages', json={'clientMessageId':'x','text':'こんにちは'})
                self.assertEqual(reply.status_code, 503)
                self.assertIn('KAKEI_AGENT_MODEL', reply.text)

    def test_changed_source_during_turn_retries_without_duplicate_messages(self):
        thread = self.client.post('/api/agent/threads', json={}).json()['thread']['id']
        async def change_source(*args, **kwargs):
            self.app.state.store.create_transaction(DRAFT)
            return {'text':'確認', 'commands':[{'kind':'transaction.create','identity':{},'data':DRAFT}]}
        url = f'/api/agent/threads/{thread}/messages'
        body = {'clientMessageId':'retry','text':'追加'}
        with patch.object(self.runner, 'run_turn', side_effect=change_source):
            self.assertEqual(self.client.post(url, json=body).status_code, 409)
        result = self.client.post(url, json=body)
        self.assertEqual(result.status_code, 200, result.text)
        proposal = result.json()['proposal']
        rejected = self.client.post('/api/agent/proposals/'+proposal['id']+'/reject', json={'revision':1})
        self.assertEqual(rejected.json()['proposal']['status'], 'rejected')
        self.assertEqual(len(self.client.get(f'/api/agent/threads/{thread}').json()['thread']['messages']), 2)

    def test_deleted_thread_rejects_late_runner_output(self):
        thread=self.client.post('/api/agent/threads',json={}).json()['thread']['id']
        async def deleted(*args,**kwargs):
            self.assertEqual(kwargs['turn_context']['thread_id'],thread)
            from db.agent_store import AgentStore
            AgentStore(self.app.state.store.db_path).delete_thread(thread)
            return {'text':'完了','commands':[]}
        with patch.object(self.runner,'run_turn',side_effect=deleted):
            response=self.client.post(f'/api/agent/threads/{thread}/messages',json={'clientMessageId':'late','text':'検索'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.client.get(f'/api/agent/threads/{thread}').status_code,404)
