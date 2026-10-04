import asyncio, copy, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.runtime import AgentRunner as CurrentAgentRunner, TurnLimit
from agent.legacy_place_tools import legacy_place_tools_factory
from functools import partial
AgentRunner=partial(CurrentAgentRunner,place_tools_factory=legacy_place_tools_factory)
from db.store import Store
from test_agent_changes import DRAFT
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from pydantic import PrivateAttr

class ScriptModel(BaseChatModel):
    replies: list
    _index: int = PrivateAttr(default=0)
    _names: list = PrivateAttr(default_factory=list)
    _seen: list = PrivateAttr(default_factory=list)
    @property
    def _llm_type(self): return 'script'
    def bind_tools(self, tools, **kwargs):
        self._names = [tool.name for tool in tools]
        return self
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._seen.append(messages)
        message = self.replies[self._index]; self._index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name)/'db'); self.store.initialize([])

    async def test_runtime_registers_three_tools_and_stages_edits(self):
        model = ScriptModel(replies=[AIMessage(content='', tool_calls=[{'name':'edit_transaction','args':{'operation':'create','data':DRAFT},'id':'1','type':'tool_call'}]), AIMessage(content='確認してください')])
        result = await AgentRunner(self.store, model=model).run_turn('thread', [{'role':'user','text':'給与を記録'}])
        self.assertEqual(set(model._names), {'read_sql','edit_transaction','edit_trajectory','trajectory_context','search_place','read_place_search_history'})
        self.assertEqual(result['commands'][0]['data'], DRAFT)
        self.assertEqual(self.store.list_transactions(), [])

    async def test_tool_and_time_limits(self):
        calls = [{'name':'read_sql','args':{'sql':'SELECT 1'},'id':str(i),'type':'tool_call'} for i in range(9)]
        model = ScriptModel(replies=[AIMessage(content='', tool_calls=calls), AIMessage(content='done')])
        with self.assertRaises(TurnLimit):
            await AgentRunner(self.store, model=model).run_turn('t', [{'role':'user','text':'test'}])
        async def slow(*args, **kwargs): await asyncio.sleep(1)
        with patch('agent.runtime.TURN_SECONDS', 0.01), patch('langgraph.graph.state.CompiledStateGraph.ainvoke', side_effect=slow):
            with self.assertRaises(TimeoutError):
                await AgentRunner(self.store, model=ScriptModel(replies=[])).run_turn('t', [{'role':'user','text':'test'}])

    async def test_search_sources_without_proposal_survive_reload(self):
        import json
        from db.agent_store import AgentStore
        from db.agent_search_store import AgentSearchStore
        from test_agent_place_search import Provider, Verifier
        from agent_search_fixtures import SEARCH
        repository=AgentStore(self.store.db_path)
        thread=repository.create_thread()['id']; lease=repository.begin_turn(thread,'one','店舗を探して')
        ctx={'thread_id':thread,'client_message_id':'one','run_token':lease['token']}
        request={**SEARCH,'query':'ドトールコーヒーショップ 西鉄福岡駅店'}
        model=ScriptModel(replies=[AIMessage(content='',tool_calls=[{'name':'search_place','args':request,'id':'s','type':'tool_call'}]),AIMessage(content='候補です')])
        class FakeProvider(Provider):
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
        from test_geolonia_search import Geolonia
        geo=Geolonia();geo.status='unavailable'
        with patch('agent.web_places.WebPlaceProvider',FakeProvider), patch('agent.web_coordinates.WebCoordinateVerifier',lambda *args:Verifier()),patch('agent.geolonia_client.GeoloniaClient',lambda:geo):
            raw=await AgentRunner(self.store,model=model).run_turn(thread,repository.get_thread(thread)['messages'],turn_context=ctx)
        response=repository.complete_turn(thread,'one',lease,raw)
        self.assertIsNone(response['proposal'])
        self.assertTrue(response['message']['sources'])
        self.assertEqual(response['message']['sources'],repository.get_thread(thread)['messages'][-1]['sources'])
        history=AgentSearchStore(self.store.db_path).history(thread)
        self.assertEqual(len(history['records']),1)
        self.assertEqual(len(history['records'][0]['result']['candidates']),1)
        self.assertEqual(len(repository.get_thread(thread)['messages']),2)
        serialized=json.dumps([[m.model_dump() for m in turn] for turn in model._seen],ensure_ascii=False,default=str)
        self.assertNotIn(lease['token'],serialized)
        self.assertNotIn('run_token',serialized)

    async def test_runtime_geolonia_candidate_sources_survive_reload(self):
        import json
        from db.agent_store import AgentStore
        from db.agent_search_store import AgentSearchStore
        from test_geolonia_search import Geolonia
        from geolonia_fixtures import ADDRESS
        repository=AgentStore(self.store.db_path);thread=repository.create_thread()['id']
        lease=repository.begin_turn(thread,'one','合成テスト店舗 '+ADDRESS)
        messages=repository.get_thread(thread)['messages']
        request={'query':'合成テスト店舗','place_id':'p','address':ADDRESS,'evidence':[{'field':'address','source':'user_message','source_id':messages[-1]['id'],'value':ADDRESS}]}
        model=ScriptModel(replies=[AIMessage(content='',tool_calls=[{'name':'search_place','args':request,'id':'s','type':'tool_call'}]),AIMessage(content='住所に対応する座標です')])
        with patch('agent.geolonia_client.GeoloniaClient',Geolonia):
            raw=await AgentRunner(self.store,model=model).run_turn(thread,messages,turn_context={'thread_id':thread,'client_message_id':'one','run_token':lease['token']})
        response=repository.complete_turn(thread,'one',lease,raw)
        self.assertTrue(response['message']['sources'])
        record=AgentSearchStore(self.store.db_path).history(thread)['records'][0]['result']
        self.assertEqual(record['candidates'][0]['coordinateEvidence']['status'],'address_matched')
        self.assertEqual(response['message']['sources'],repository.get_thread(thread)['messages'][-1]['sources'])

    async def test_invalid_search_arguments_can_be_corrected_without_losing_draft(self):
        from db.agent_store import AgentStore
        from db.agent_search_store import AgentSearchStore
        from test_geolonia_search import Geolonia
        from geolonia_fixtures import ADDRESS
        repository=AgentStore(self.store.db_path);thread=repository.create_thread()['id']
        lease=repository.begin_turn(thread,'one','合成テスト店舗 '+ADDRESS)
        messages=repository.get_thread(thread)['messages']
        request={'query':'合成テスト店舗','place_id':'p','address':ADDRESS,'evidence':[{'field':'address','source':'user_message','source_id':messages[-1]['id'],'value':ADDRESS}]}
        command={'operation':'create','identity':{'kind':'day','date':'2027-03-01'},'data':{'events':[{'id':'visit','time':'12:00','timeEvidence':'exact','placeId':'p'}],'legs':[]}}
        def call(name,args,identifier):return AIMessage(content='',tool_calls=[{'name':name,'args':args,'id':identifier,'type':'tool_call'}])
        model=ScriptModel(replies=[call('search_place',request,'s1'),call('edit_trajectory',command,'draft'),
            call('search_place',{**request,'landmark':'根拠のない駅'},'bad'),call('search_place',request,'corrected'),AIMessage(content='変更案を確認してください')])
        with patch('agent.geolonia_client.GeoloniaClient',Geolonia):
            raw=await AgentRunner(self.store,model=model).run_turn(thread,messages,turn_context={'thread_id':thread,'client_message_id':'one','run_token':lease['token']})
        response=repository.complete_turn(thread,'one',lease,raw)
        feedback=next(m for m in model._seen[-1] if m.type=='tool' and m.tool_call_id=='bad')
        self.assertEqual(feedback.status,'error')
        self.assertEqual(json.loads(feedback.content)['field'],'landmark')
        self.assertEqual(response['proposal']['commands'][0]['data'],command['data'])
        self.assertTrue(response['message']['sources'])
        searches=AgentSearchStore(self.store.db_path).history(thread)['records']
        self.assertEqual(len(searches),2)
        self.assertTrue(all(r['result']['candidates'] for r in searches))
        self.assertEqual(self.store.list_trajectory_dates(),[])
        proposal=response['proposal'];candidate=proposal['metadata']['placeCandidates'][0]['candidates'][0]
        proposal=repository.select_place_candidate(proposal['id'],proposal['revision'],candidate['id'],confirmed=True)
        self.store.apply_agent_proposal(proposal['id'],proposal['revision'])
        self.assertEqual(self.store.get_trajectory_day('2027-03-01')['days'][0]['events'][0]['id'],'visit')

    async def test_invalid_visit_draft_is_corrected_in_same_turn(self):
        place={'name':'確認済みの店舗','address':None,'coordinates':[139,35],'sourceUrl':None,'placeEvidence':'user'}
        self.store.sync_trajectory({'places':{'p':place},'days':[]})
        valid={'operation':'create','identity':{'kind':'day','date':'2027-03-01'},'data':{'events':[{'id':'visit','time':'12:00','timeEvidence':'exact','placeId':'p'}],'legs':[]}}
        invalid=copy.deepcopy(valid);invalid['data']['events'][0].pop('id')
        model=ScriptModel(replies=[AIMessage(content='',tool_calls=[{'name':'edit_trajectory','args':invalid,'id':'bad','type':'tool_call'}]),
            AIMessage(content='',tool_calls=[{'name':'edit_trajectory','args':valid,'id':'fixed','type':'tool_call'}]),AIMessage(content='変更案を確認してください')])
        raw=await AgentRunner(self.store,model=model).run_turn('thread',[{'role':'user','text':'軌跡を作って'}])
        feedback=next(m for m in model._seen[-1] if m.type=='tool' and m.tool_call_id=='bad')
        self.assertEqual(feedback.status,'error')
        self.assertEqual(json.loads(feedback.content)['field'],'events')
        self.assertEqual(len(raw['commands']),1)
        self.assertEqual(raw['commands'][0]['data'],valid['data'])
        self.assertEqual(self.store.list_trajectory_dates(),[])

    async def test_history_overrides_unsupported_assistant_claim(self):
        import json
        from db.agent_store import AgentStore
        from db.agent_search_store import AgentSearchStore
        from agent_search_fixtures import REQUEST,result
        repo=AgentStore(self.store.db_path);thread=repo.create_thread()['id']
        lease=repo.begin_turn(thread,'one','検索')
        context={'thread_id':thread,'client_message_id':'one','run_token':lease['token']}
        history=AgentSearchStore(self.store.db_path);sid=history.start(context,REQUEST);history.finish(context,sid,result(sid))
        repo.complete_turn(thread,'one',lease,{'text':'東京の候補です','commands':[]})
        next_lease=repo.begin_turn(thread,'two','探した候補を教えて')
        model=ScriptModel(replies=[AIMessage(content='',tool_calls=[{'name':'read_place_search_history','args':{},'id':'h','type':'tool_call'}]),AIMessage(content='記録では0件です')])
        await AgentRunner(self.store,model=model).run_turn(thread,repo.get_thread(thread)['messages'],turn_context={**context,'client_message_id':'two','run_token':next_lease['token']})
        tools=[m for m in model._seen[-1] if m.type=='tool']
        self.assertEqual(json.loads(tools[-1].content)['records'][0]['result']['candidates'],[])
        data=[m for m in model._seen[0] if sid in str(m.content)]
        self.assertTrue(data);self.assertTrue(all(m.type!='system' for m in data))

    async def test_tool_evidence_cannot_cross_threads(self):
        from db.agent_store import AgentStore
        from db.agent_search_store import AgentSearchStore
        from db.store import TrajectoryNotFound
        from agent_search_fixtures import REQUEST,result
        repo=AgentStore(self.store.db_path);a=repo.create_thread()['id'];b=repo.create_thread()['id']
        lease=repo.begin_turn(a,'one','検索');ctx={'thread_id':a,'client_message_id':'one','run_token':lease['token']}
        searches=AgentSearchStore(self.store.db_path);sid=searches.start(ctx,REQUEST);searches.finish(ctx,sid,result(sid))
        other=repo.begin_turn(b,'one','検索')
        model=ScriptModel(replies=[AIMessage(content='',tool_calls=[{'name':'read_place_search_history','args':{'search_id':sid},'id':'h','type':'tool_call'}])])
        with self.assertRaises(TrajectoryNotFound):
            await AgentRunner(self.store,model=model).run_turn(b,repo.get_thread(b)['messages'],turn_context={'thread_id':b,'client_message_id':'one','run_token':other['token']})

    async def test_search_configuration_is_independent(self):
        from agent.runtime import configuration
        with patch.dict('os.environ',{'OPENAI_API_KEY':'secret','KAKEI_AGENT_MODEL':'test','GOOGLE_PLACES_API_KEY':'places-test'},clear=True):
            status=configuration()
            self.assertTrue(status['available']);self.assertTrue(status['placesAvailable'])
            self.assertEqual(status['placesMissing'],[])

    async def test_long_turn_keeps_lease_and_stale_retries_are_fenced(self):
        import time
        from agent.runtime import TURN_SECONDS
        from agent.limits import TURN_LEASE_SECONDS
        from db.agent_store import AgentStore
        from db.store import TrajectoryConflict
        self.assertEqual(TURN_SECONDS,180);self.assertEqual(TURN_LEASE_SECONDS,190)
        repo=AgentStore(self.store.db_path);thread=repo.create_thread()['id']
        lease=repo.begin_turn(thread,'one','search')
        with self.store._connection() as c:c.execute('UPDATE agent_turns SET started_at=?',(time.time()-80,))
        with self.assertRaises(TrajectoryConflict):repo.begin_turn(thread,'two','search again')
        with self.store._connection() as c:c.execute('UPDATE agent_turns SET started_at=?',(time.time()-191,))
        repo.begin_turn(thread,'two','search again')
        with self.assertRaises(TrajectoryConflict):repo.complete_turn(thread,'one',lease,{'text':'late'})
