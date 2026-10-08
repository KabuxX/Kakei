import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.store import Store, TrajectoryConflict, TrajectoryNotFound
from agent.receipt import ReceiptCandidate
from agent.google_places import GoogleCandidate, GooglePlacesError
from services.validation import ValidationError
from services.receipt_location import ReceiptLocationService


def candidate(name='店', address='東京都千代田区', pid='p', types=None):
    return GoogleCandidate(pid,name,address,[],None,['store'] if types is None else types,None,[])

class Client:
    def __init__(self):
        self.queries=[]; self.results=[candidate()]; self.error=None; self.gate=None; self.started=asyncio.Event(); self.detail=candidate(types=[])
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def search_text(self, query, *, region_code=None):
        self.queries.append(query); self.started.set()
        if self.gate: await self.gate.wait()
        if self.error: raise self.error
        return self.results
    async def details(self,pid):
        if self.error: raise self.error
        return self.detail

class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=Store(Path(temp.name)/'db');self.now=100.;self.mono=10.;self.client=Client()
        self.service=ReceiptLocationService(self.store,client_factory=lambda:self.client,wall_clock=lambda:self.now,monotonic=lambda:self.mono)
        self.input={'merchant':'店','locality':'千代田区'}
        with self.store._connection() as c:
            c.execute("INSERT INTO agent_threads VALUES ('t',0,'test')")
            c.execute("INSERT INTO receipt_assets VALUES ('r','t','image/png','hash',1,X'00',0,999999,NULL)")
            c.execute("INSERT INTO transactions (id,title,date,type,category,amount,merchant,merchant_address) VALUES ('tx','買物','2026-10-01T12:00','expense','食費',100,'店','住所')")
    async def test_printed_address_skips_google(self):
        printed=await self.service.initialize('t','r',ReceiptCandidate(merchant='店',merchant_address='印字住所'),deadline=190,turn_context=None)
        self.assertEqual(printed['method'],'receipt_address');self.assertEqual(self.client.queries,[])
    async def test_search_20_seconds_two_requests(self):
        result=await self.service.search('t','r',self.input,0)
        self.assertEqual(result['method'],'google_unique');self.assertLessEqual(len(self.client.queries),2)
        self.assertEqual(result['expiresAt'],86500)
    async def test_select_checks_current_candidates_and_details(self):
        result=await self.service.search('t','r',{'merchant':'店'},0)
        self.assertEqual(result['status'],'needs_selection')
        with self.assertRaises(ValidationError):await self.service.select('t','r',result['id'],result['revision'],'forged')
        self.client.detail=candidate(address='大阪府大阪市',types=[])
        selected=await self.service.select('t','r',result['id'],result['revision'],'p')
        self.assertEqual(selected['method'],'google_selected')
        with self.assertRaises(TrajectoryConflict):await self.service.select('t','r',result['id'],result['revision'],'p')
    async def test_configuration_not_found_timeout_distinct(self):
        for error,reason in [(GooglePlacesError('configuration'),'provider_configuration'),(GooglePlacesError('unavailable'),'provider_unavailable'),(TimeoutError(),'budget_exceeded')]:
            self.client.error=error
            current=self.service.get('t','r')
            result=await self.service.search('t','r',self.input,current['revision'] if current else 0)
            self.assertEqual(result['reason'],reason)
        self.client.error=None;self.client.results=[]
        missing=await self.service.search('t','r',self.input,result['revision'])
        self.assertEqual(missing['status'],'not_found')
    async def test_changed_input_discards_old_search(self):
        self.client.gate=asyncio.Event();task=asyncio.create_task(self.service.search('t','r',self.input,0))
        await self.client.started.wait();current=self.service.get('t','r')
        confirmed=self.service.confirm_address('t','r',{'merchant':'別店','merchantAddress':'別住所'},current['revision'])
        self.client.gate.set()
        with self.assertRaises(TrajectoryConflict):await task
        self.assertEqual(self.service.get('t','r'),confirmed)
    async def test_deleted_thread_does_not_resurrect(self):
        self.client.gate=asyncio.Event();task=asyncio.create_task(self.service.search('t','r',self.input,0))
        await self.client.started.wait()
        with self.store._connection() as c:
            before=[tuple(row) for row in c.execute('SELECT * FROM transactions')];c.execute("DELETE FROM agent_threads WHERE id='t'")
        self.client.gate.set()
        with self.assertRaises(TrajectoryNotFound):await task
        with self.store._connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM receipt_location_resolutions').fetchone()[0],0)
            self.assertEqual([tuple(row) for row in c.execute('SELECT * FROM transactions')],before)
    async def test_existing_target_requires_same_merchant(self):
        with self.assertRaises(ValidationError):self.service.confirm_address('t','r',{'merchant':'別店','merchantAddress':'住所'},0,source_transaction_id='tx')
        result=self.service.confirm_address('t','r',{'merchant':'店','merchantAddress':'住所'},0,source_transaction_id='tx')
        self.assertEqual((result['method'],result['sourceTransactionId']),('existing_address','tx'))
        with self.assertRaises(ValidationError):self.service.confirm_address('t','r',{'merchant':'店','merchantAddress':'偽住所'},result['revision'],source_transaction_id='tx')
    async def test_wrong_thread_and_expired_receipt_rejected(self):
        with self.assertRaises(TrajectoryNotFound):await self.service.search('other','r',self.input,0)
        self.now=999999
        with self.assertRaises(TrajectoryNotFound):self.service.confirm_address('t','r',{'merchant':'店','merchantAddress':'住所'},0)
    async def test_details_mismatch_preserves_candidates(self):
        result=await self.service.search('t','r',self.input,0)
        # Search with no locality forces selection.
        result=await self.service.search('t','r',{'merchant':'店'},result['revision'])
        self.client.detail=candidate(name='別店',types=[])
        with self.assertRaises(ValidationError):await self.service.select('t','r',result['id'],result['revision'],'p')
        self.assertEqual(self.service.get('t','r')['status'],'needs_selection')
    async def test_existing_google_is_bound_and_clears_address(self):
        from db.merchant_place_store import write_merchant_place
        with self.store._connection() as c:
            write_merchant_place(c,'tx',{'provider':'google','placeId':'saved','method':'google_unique','input':self.input,'confirmedAt':99})
        result=await self.service.search('t','r',{'merchant':'店','merchantAddress':'古い住所'},0,source_transaction_id='tx')
        self.assertEqual((result['method'],result['selectedPlaceId'],result['sourceTransactionId']),('existing_google','saved','tx'))
        self.assertIsNone(result['input']['merchantAddress'])
    async def test_deadline_recovers_without_late_success(self):
        original=self.client.search_text
        async def slow(query,**kwargs):
            result=await original(query,**kwargs)
            self.now+=21;self.mono+=21
            return result
        self.client.search_text=slow
        result=await self.service.search('t','r',self.input,0)
        self.assertEqual((result['status'],result['reason']),('unavailable','budget_exceeded'))
    async def test_initial_search_rejects_cancelled_turn(self):
        with self.store._connection() as c:
            c.execute("INSERT INTO agent_turns VALUES ('t','m','{}','new','processing',100,NULL)")
        with self.assertRaises(TrajectoryConflict):
            await self.service.initialize('t','r',ReceiptCandidate(merchant='店'),deadline=190,turn_context={'thread_id':'t','client_message_id':'m','run_token':'old'})
    async def test_confirm_renews_expiry_from_latest_event(self):
        first=self.service.confirm_address('t','r',{'merchant':'店','merchantAddress':'住所'},0)
        self.now=200
        renewed=self.service.confirm_address('t','r',first['input'],first['revision'])
        self.assertEqual(renewed['expiresAt'],86600)
    async def test_two_query_variants_and_ten_candidate_cap(self):
        self.client.results=[]
        result=await self.service.search('t','r',{'merchant':'店','merchantAddress':'〒100-0001 東京都千代田区'},0)
        self.assertEqual(result['status'],'not_found')
        self.assertEqual(len(self.client.queries),2)
        self.client.results=[candidate(pid='p'+str(i)) for i in range(12)]
        selected=await self.service.search('t','r',{'merchant':'店'},result['revision'])
        self.assertEqual(len(selected['placeIds']),10)
