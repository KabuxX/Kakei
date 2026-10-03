import asyncio, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.runtime import AgentRunner, TurnLimit
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
        from test_agent_place_search import Provider, Geocoder
        from agent_search_fixtures import SEARCH
        repository=AgentStore(self.store.db_path)
        thread=repository.create_thread()['id']; lease=repository.begin_turn(thread,'one','店舗を探して')
        ctx={'thread_id':thread,'client_message_id':'one','run_token':lease['token']}
        request={**SEARCH,'query':'ドトールコーヒーショップ 西鉄福岡駅店'}
        model=ScriptModel(replies=[AIMessage(content='',tool_calls=[{'name':'search_place','args':request,'id':'s','type':'tool_call'}]),AIMessage(content='候補です')])
        class FakeProvider(Provider):
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
        with patch('agent.web_places.WebPlaceProvider',FakeProvider), patch('agent.geocoding.MapboxGeocoder',Geocoder):
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
        with patch.dict('os.environ',{'OPENAI_API_KEY':'secret','KAKEI_AGENT_MODEL':'test'},clear=True):
            status=configuration()
            self.assertTrue(status['available']);self.assertFalse(status['placesAvailable'])
            self.assertEqual(status['placesMissing'],['MAPBOX_GEOCODING_ACCESS_TOKEN'])

    async def test_long_turn_keeps_lease_and_stale_retries_are_fenced(self):
        import time
        from agent.runtime import TURN_SECONDS
        from agent.limits import TURN_LEASE_SECONDS
        from db.agent_store import AgentStore
        from db.store import TrajectoryConflict
        self.assertEqual(TURN_SECONDS,120);self.assertEqual(TURN_LEASE_SECONDS,130)
        repo=AgentStore(self.store.db_path);thread=repo.create_thread()['id']
        lease=repo.begin_turn(thread,'one','search')
        with self.store._connection() as c:c.execute('UPDATE agent_turns SET started_at=?',(time.time()-80,))
        with self.assertRaises(TrajectoryConflict):repo.begin_turn(thread,'two','search again')
        with self.store._connection() as c:c.execute('UPDATE agent_turns SET started_at=?',(time.time()-131,))
        repo.begin_turn(thread,'two','search again')
        with self.assertRaises(TrajectoryConflict):repo.complete_turn(thread,'one',lease,{'text':'late'})
