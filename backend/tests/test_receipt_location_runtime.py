import asyncio,json,sys,tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.runtime import AgentRunner
from agent.receipt import ReceiptCandidate
from db.agent_store import AgentStore
from db.receipt_store import ReceiptStore
from services.receipt_location import ReceiptLocationService
from services.receipt_validation import validate_receipt
from test_receipt_upload import png
from test_agent_runtime import ScriptModel
from langchain_core.messages import AIMessage
from agent.google_places import GoogleCandidate

class Client:
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def search_text(self,*args,**kwargs):
        return [GoogleCandidate('p','具体店舗駅前店','Google専用の住所文字列',[],None,['store'],None,[])]

class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().slow_callback_duration=1
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.repo=AgentStore(Path(tmp.name)/'db');self.store=self.repo.store;self.store.initialize([])
        self.thread=self.repo.create_thread()['id'];self.receipt=ReceiptStore(self.store.db_path).create_pending(self.thread,validate_receipt(png(),'r.png'))['id']
        self.lease=self.repo.begin_turn(self.thread,'read','レシート',self.receipt)
        self.ctx={'thread_id':self.thread,'client_message_id':'read','run_token':self.lease['token']}
    def runner(self,model):return AgentRunner(self.store,model=model,receipt_location_service_factory=lambda store:ReceiptLocationService(store,client_factory=Client))
    async def test_google_content_not_in_model_or_json(self):
        model=ScriptModel(replies=[AIMessage(content='',tool_calls=[{'name':'read_receipt','args':{},'id':'r','type':'tool_call'}]),AIMessage(content='確認してください')])
        with patch('agent.receipt.extract_receipt',return_value=ReceiptCandidate(merchant='具体店舗駅前店')):
            result=await self.runner(model).run_turn(self.thread,self.repo.get_thread(self.thread)['messages'],self.receipt,turn_context=self.ctx)
        self.assertEqual(result['receiptReview']['locationResolution']['status'],'needs_selection')
        self.repo.complete_turn(self.thread,'read',self.lease,result)
        serialized=json.dumps([[m.model_dump() for m in turn] for turn in model._seen],ensure_ascii=False,default=str)
        with self.store._connection() as c:
            for table in ('receipt_location_resolutions','agent_messages','agent_turns','agent_proposals'):
                serialized+=str([tuple(row) for row in c.execute('SELECT * FROM '+table)])
        self.assertNotIn('Google専用の住所文字列',serialized)
    async def test_initial_search_shares_turn_deadline(self):
        model=ScriptModel(replies=[])
        class SlowClient(Client):
            async def search_text(self,*args,**kwargs):await asyncio.sleep(.1);return []
        runner=AgentRunner(self.store,model=model,receipt_location_service_factory=lambda store:ReceiptLocationService(store,client_factory=SlowClient))
        with patch('agent.runtime.TURN_SECONDS',.08),patch('agent.runtime.RECEIPT_RESPONSE_RESERVE',.02),patch('agent.receipt.extract_receipt',return_value=ReceiptCandidate(merchant='具体店舗駅前店')):
            start=time.monotonic();result=await runner.run_turn(self.thread,[],self.receipt,turn_context=self.ctx)
        self.assertLess(time.monotonic()-start,.15)
        self.assertEqual(result['receiptReview']['locationResolution']['reason'],'budget_exceeded')
        self.assertEqual(model._seen,[])
    async def test_late_extraction_returns_researchable_review(self):
        model=ScriptModel(replies=[])
        async def extract(*args):await asyncio.sleep(.06);return ReceiptCandidate(merchant='具体店舗駅前店')
        with patch('agent.runtime.TURN_SECONDS',.08),patch('agent.runtime.RECEIPT_RESPONSE_RESERVE',.03),patch('agent.receipt.extract_receipt',side_effect=extract):
            result=await self.runner(model).run_turn(self.thread,[],self.receipt,turn_context=self.ctx)
        self.assertEqual(result['receiptReview']['locationResolution']['reason'],'budget_exceeded');self.assertEqual(model._seen,[])
    async def test_slow_model_keeps_review_before_outer_deadline(self):
        async def slow(*args,**kwargs):await asyncio.sleep(.2)
        model=ScriptModel(replies=[])
        with patch('agent.runtime.TURN_SECONDS',.12),patch('agent.runtime.RECEIPT_RESPONSE_RESERVE',.03),patch('agent.receipt.extract_receipt',return_value=ReceiptCandidate(merchant='店',merchant_address='本人住所')),patch('langgraph.graph.state.CompiledStateGraph.ainvoke',side_effect=slow):
            start=time.monotonic();result=await self.runner(model).run_turn(self.thread,[],self.receipt,turn_context=self.ctx)
        self.assertLess(time.monotonic()-start,.11);self.assertIn('receiptReview',result)
    async def test_app_injects_location_service_into_default_runner(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        from functools import partial
        model=ScriptModel(replies=[AIMessage(content='確認してください')])
        app=create_app(self.store.db_path,Path(self.store.db_path).parent,receipt_location_service_factory=lambda store:ReceiptLocationService(store,client_factory=Client))
        # Default API runner still executes the actual graph, with an offline model.
        with patch('api.agent.AgentRunner',partial(AgentRunner,model=model)),patch('agent.receipt.extract_receipt',return_value=ReceiptCandidate(merchant='具体店舗駅前店')):
            with TestClient(app,base_url='http://localhost:8765',headers={'origin':'http://localhost:8765'}) as client:
                other=self.repo.create_thread()['id'];receipt=ReceiptStore(self.store.db_path).create_pending(other,validate_receipt(png(),'a.png'))['id']
                response=client.post('/api/agent/threads/'+other+'/messages',json={'clientMessageId':'read','text':'レシート','receiptId':receipt})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['receiptReview']['locationResolution']['placeIds'],['p'])
