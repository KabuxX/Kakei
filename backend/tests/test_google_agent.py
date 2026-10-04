import copy, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api.app import create_app
from agent.runtime import AgentRunner
from agent.google_places import GoogleCandidate
from google_places_fixtures import place
from test_trajectory_creation import transaction
from test_agent_runtime import ScriptModel
from langchain_core.messages import AIMessage

class Google:
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def search_text(self,query,**kwargs):
        label=next((name for name in ('合成店舗a','合成店舗b','合成店舗c') if name in query),'合成店舗a')
        ids=['a','b'] if label.endswith('c') else ['one']
        return [GoogleCandidate.from_payload(place('fixture-'+label[-1]+i,label)) for i in ids]
    async def details(self,identifier):
        return GoogleCandidate.from_payload(place(identifier,'Googleから取得した名称'))

class GoogleAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);seed=root/'seed.json';seed.write_text('{"places":{},"days":[]}')
        self.app=create_app(root/'db',root,timeline_path=seed)
        self.store=self.app.state.store
        self.store.initialize([transaction('a'),transaction('b','13:00'),transaction('c','14:00')])
        from db.agent_store import AgentStore
        self.repo=AgentStore(self.store.db_path);self.thread=self.repo.create_thread()['id']

    async def test_explicit_creation_uses_current_message_only(self):
        lease=self.repo.begin_turn(self.thread,'one','2027年3月1日の取引で軌跡を作って')
        with patch('agent.google_places.GooglePlacesClient',Google):
            raw=await AgentRunner(self.store).run_turn(self.thread,self.repo.get_thread(self.thread)['messages'],turn_context={'thread_id':self.thread,'client_message_id':'one','run_token':lease['token']})
        response=self.repo.complete_turn(self.thread,'one',lease,raw)
        self.assertEqual(response['trajectoryCreation']['status'],'partial')
        self.assertEqual(response['trajectoryCreation']['counts']['saved'],2)
        model=ScriptModel(replies=[AIMessage(content='相談に答えます')])
        with patch('agent.google_places.GooglePlacesClient',Google):
            normal=await AgentRunner(self.store,model=model).run_turn(self.thread,[{'role':'user','text':'2027年3月1日の軌跡を作って'},{'role':'user','text':'いくら使った？'}])
        self.assertNotIn('preparedCreation',normal)

    async def test_google_only_no_legacy_constructor(self):
        with patch('agent.google_places.GooglePlacesClient',Google),patch('agent.web_places.WebPlaceProvider',side_effect=AssertionError('legacy web used')),patch('agent.geolonia_client.GeoloniaClient',side_effect=AssertionError('legacy geolonia used')):
            raw=await AgentRunner(self.store).run_turn(self.thread,[{'role':'user','text':'2027-03-01の軌跡を作って'}])
        self.assertEqual(raw['preparedCreation'].result['counts']['saved'],2)

    async def test_google_search_only_never_saves(self):
        model=ScriptModel(replies=[AIMessage(content='',tool_calls=[{'name':'search_place','args':{'query':'合成店舗a','place_id':'p'},'id':'s','type':'tool_call'}]),AIMessage(content='検索結果です')])
        lease=self.repo.begin_turn(self.thread,'search','合成店舗aを検索して')
        with patch('agent.google_places.GooglePlacesClient',Google):
            raw=await AgentRunner(self.store,model=model).run_turn(self.thread,self.repo.get_thread(self.thread)['messages'],turn_context={'thread_id':self.thread,'client_message_id':'search','run_token':lease['token']})
        response=self.repo.complete_turn(self.thread,'search',lease,raw)
        self.assertIsNone(response['proposal']);self.assertEqual(self.store.list_trajectory_dates(),[])
        self.assertEqual(response['message']['placeSearch']['placeIds'],['fixture-aone'])
        serialized=json.dumps([[m.model_dump() for m in turn] for turn in model._seen],ensure_ascii=False,default=str)
        self.assertNotIn('二番町8-8',serialized)

    async def test_missing_maps_key_does_not_block_creation(self):
        with TestClient(self.app,base_url='http://127.0.0.1:8765',headers={'Origin':'http://127.0.0.1:8765'}) as client,patch('agent.google_places.GooglePlacesClient',Google),patch.dict('os.environ',{'GOOGLE_PLACES_API_KEY':'server-secret','GOOGLE_MAPS_BROWSER_API_KEY':''}):
            response=client.post(f'/api/agent/threads/{self.thread}/messages',json={'text':'2027年3月1日の軌跡を作って','clientMessageId':'one'})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['trajectoryCreation']['counts']['saved'],2)
            config=client.get('/api/map-config').json()
            self.assertIsNone(config['googleMapsBrowserKey'])
            self.assertNotIn('server-secret',json.dumps(config))
            day=client.get('/api/trajectory/2027-03-01').json()
            self.assertEqual(day['places']['google:fixture-aone']['coordinates'],[139.737,35.685])

    async def test_reprepare_once_without_extending_deadline(self):
        original=self.repo.complete_turn
        from db.agent_store import AgentStore
        from db.store import TrajectoryConflict
        calls=[]
        def conflict_once(repo,thread,client_id,lease,result):
            calls.append(result['preparedCreation'].source_version)
            if len(calls)==1:
                repo.store.create_transaction({k:v for k,v in transaction('late','15:00').items() if k!='id'})
            return original(thread,client_id,lease,result)
        with TestClient(self.app,base_url='http://127.0.0.1:8765',headers={'Origin':'http://127.0.0.1:8765'}) as client,patch('agent.google_places.GooglePlacesClient',Google),patch.object(AgentStore,'complete_turn',conflict_once):
            response=client.post(f'/api/agent/threads/{self.thread}/messages',json={'text':'2027-03-01の軌跡を作って','clientMessageId':'one'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(calls),2)
        self.assertNotEqual(calls[0],calls[1])
