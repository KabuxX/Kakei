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

    def test_web_search_to_approval_and_thread_deletion(self):
        from agent.runtime import AgentRunner
        from test_agent_runtime import ScriptModel
        from test_agent_place_search import Provider, Geocoder
        from langchain_core.messages import AIMessage
        from agent_search_fixtures import SEARCH, SHOP
        from db.agent_search_store import AgentSearchStore
        from db.agent_store import AgentStore
        class FakeProvider(Provider):
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
        tx=self.app.state.store.create_transaction({'title':'ドトール','date':'2026-10-02T12:19','type':'expense','category':'食費','amount':250,'merchant':'ドトールコーヒーショップ 西鉄福岡駅店','paymentMethod':'cash'})
        args={'operation':'create','identity':{'kind':'day','date':'2026-10-02'},'data':{'events':[{'id':'visit','placeId':'p','transactionId':tx['id'],'time':'12:19','timeEvidence':'exact'}],'legs':[]}}
        def call(name,args,identifier): return AIMessage(content='',tool_calls=[{'name':name,'args':args,'id':identifier,'type':'tool_call'}])
        model=ScriptModel(replies=[call('search_place',{**SEARCH,'query':'ドトールコーヒーショップ 西鉄福岡駅店'},'s'),call('edit_trajectory',args,'e'),AIMessage(content='支店未確認の候補です。保存前に確認してください。'),call('read_place_search_history',{},'h'),AIMessage(content='福岡市の候補を取得しました。支店は未確認です。')])
        app=create_app(self.app.state.store.db_path,Path(self.temp.name),runner_factory=lambda store:AgentRunner(store,model=model))
        with TestClient(app,base_url='http://localhost:8765',headers={'Origin':'http://localhost:8765'}) as client, patch('agent.web_places.WebPlaceProvider',FakeProvider), patch('agent.geocoding.MapboxGeocoder',Geocoder):
            thread=client.post('/api/agent/threads',json={}).json()['thread']['id'];url=f'/api/agent/threads/{thread}'
            response=client.post(url+'/messages',json={'clientMessageId':'one','text':'2026年10月2日の取引記録によって、軌跡を作成して'})
            self.assertEqual(response.status_code,200,response.text)
            proposal=response.json()['proposal'];purl='/api/agent/proposals/'+proposal['id']
            candidates=proposal['metadata']['placeCandidates'][0]['candidates']
            self.assertIn('address_verified',candidates[0]['matchReasons'])
            follow=client.post(url+'/messages',json={'clientMessageId':'two','text':'探した候補を教えて'})
            self.assertEqual(follow.status_code,200,follow.text);self.assertIsNone(follow.json()['proposal'])
            self.assertEqual(client.post(purl+'/places/selection',json={'revision':1,'candidateId':'forged'}).status_code,400)
            selected=client.post(purl+'/places/selection',json={'revision':1,'candidateId':candidates[0]['id']})
            self.assertEqual(selected.status_code,200,selected.text)
            version=selected.json()['proposal']['revision']
            self.assertEqual(client.post(purl+'/approve',json={'revision':version}).status_code,200)
            day=app.state.store.get_trajectory_day('2026-10-02')
            self.assertEqual(day['places']['p']['coordinates'],[130.4,33.59])
            self.assertEqual(day['places']['p']['geocoding']['provider'],'mapbox')
            self.assertEqual(client.delete(url).status_code,204)
            with app.state.store._connection() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_place_searches').fetchone()[0],0)
            self.assertEqual(len(app.state.store.list_transactions()),1)
            self.assertEqual(AgentStore(app.state.store.db_path).get_proposal(proposal['id'])['status'],'applied')
