import asyncio,copy,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.place_search import PlaceSearchService, SearchBudget
from agent.place_matching import EvidenceResolver
from agent.places import PlaceProviderError
from db.agent_search_store import AgentSearchStore
from services.validation import ValidationError
from agent_search_fixtures import active_turn, SEARCH, SHOP, STATION

class Provider:
    def __init__(self): self.calls=[];self.block=None;self.error=None
    async def geocode(self,query,**kwargs):
        self.calls.append((query,kwargs))
        if query=='西鉄福岡駅': return [copy.deepcopy(STATION)]
        if '福岡市 天神' in query:
            if self.block: await self.block.wait()
            return [copy.deepcopy(SHOP)]
        return []
    async def nearby(self,name,**kwargs):
        self.calls.append((name,kwargs))
        if self.error: raise self.error
        return [copy.deepcopy(SHOP)]

class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store,self.agent,self.ctx=active_turn(Path(self.tmp.name)/'db')
        self.searches=AgentSearchStore(self.store.db_path);self.provider=Provider()
        self.resolver=EvidenceResolver(self.store,self.searches,self.ctx['thread_id'],[])
        self.budget=SearchBudget(time.monotonic()+60)
        self.service=PlaceSearchService(self.provider,self.searches,self.resolver,self.ctx,self.budget)
        self.req={**SEARCH,'query':'ドトールコーヒーショップ 西鉄福岡駅店'}

    async def asyncTearDown(self): await self.budget.close()

    async def test_fukuoka_fallback_records_all_attempts(self):
        out=await self.service.search(self.req)
        rec=self.searches.get(self.ctx['thread_id'],out['searchId'])
        self.assertEqual([a['stage'] for a in rec['attempts']],['formal','region','short','nearby'])
        self.assertEqual(len(self.provider.calls),4)
        self.assertEqual(len(out['candidates']),1)
        self.assertIn('branch_unconfirmed',out['candidates'][0]['matchReasons'])
        self.assertTrue(all(call[1]['timeout']<=5 for call in self.provider.calls))

    async def test_parallel_budget_and_duplicate_requests(self):
        a,b=await asyncio.gather(self.service.search({**self.req,'place_id':'a'}), self.service.search({**self.req,'place_id':'b'}))
        self.assertEqual(len(self.provider.calls),4)
        self.assertEqual((a['placeId'],b['placeId']),('a','b'))
        self.assertNotEqual(a['candidates'][0]['id'],b['candidates'][0]['id'])
        await asyncio.gather(*(self.service.search({**self.req,'query':self.req['query']+str(i)}) for i in range(10)))
        self.assertLessEqual(len(self.provider.calls),8)

    async def test_reuse_is_scoped_and_preserves_origin(self):
        first=await self.service.search(self.req);n=len(self.provider.calls)
        again=await self.service.search({**self.req,'place_id':'b','reuse_search_id':first['searchId']})
        self.assertEqual(len(self.provider.calls),n)
        self.assertEqual(again['reusedFrom']['searchId'],first['searchId'])
        self.assertNotEqual(again['candidates'][0]['id'],first['candidates'][0]['id'])
        with self.assertRaises(ValidationError): await self.service.search({**self.req,'query':'別店','reuse_search_id':first['searchId']})

    async def test_cancel_preserves_finished_attempts(self):
        self.provider.block=asyncio.Event()
        task=asyncio.create_task(self.service.search(self.req))
        while len(self.provider.calls)<3: await asyncio.sleep(.001)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        rec=self.searches.history(self.ctx['thread_id'])['records'][0]
        self.assertEqual(rec['status'],'cancelled')
        self.assertEqual(rec['attempts'][0]['status'],'complete')
        self.assertEqual(rec['attempts'][-1]['status'],'cancelled')

    async def test_partial_rate_limit_and_unknown_region(self):
        self.provider.error=PlaceProviderError('rate_limited',stop_turn=True)
        out=await self.service.search(self.req)
        self.assertEqual(out['status'],'partial');self.assertEqual(len(out['candidates']),1)
        self.assertTrue(out['error'])
        count=len(self.provider.calls)
        await self.service.search({**self.req,'query':self.req['query']+'2'})
        self.assertEqual(len(self.provider.calls),count)
        fresh=PlaceSearchService(Provider(),self.searches,self.resolver,self.ctx,SearchBudget(time.monotonic()+60))
        unknown=await fresh.search({'query':'知らない店','place_id':'x'})
        self.assertEqual(unknown['status'],'needs_region');self.assertEqual(unknown['candidates'],[])
        await fresh.budget.close()

    async def test_deadlines_never_issue_late_request(self):
        self.budget=SearchBudget(60,clock=lambda:56)
        self.service.budget=self.budget
        out=await self.service.search(self.req)
        self.assertEqual(self.provider.calls,[])
        self.assertEqual(out['status'],'partial')

    async def test_reuse_does_not_bypass_conflicting_evidence(self):
        messages=[{'id':'f','role':'user','text':'福岡市'},{'id':'t','role':'user','text':'東京'}]
        self.resolver.messages=messages
        evidence={'field':'locality','source':'user_message','source_id':'f','value':'福岡市'}
        request={**self.req,'locality':'福岡市','evidence':[evidence]}
        first=await self.service.search(request)
        second=await self.service.search({**request,'reuse_search_id':first['searchId'],'evidence':[evidence,{'field':'locality','source':'user_message','source_id':'t','value':'東京'}]})
        self.assertEqual(second['status'],'needs_clarification')
        self.assertEqual(second['candidates'],[])
        self.assertTrue(second['unresolved'])

    async def test_reuse_checks_effective_saved_region(self):
        place={k:SHOP[k] for k in ('name','address','coordinates','sourceUrl','attribution')}
        place['name']='西鉄福岡駅';place['placeEvidence']='user'
        self.store.sync_trajectory({'places':{'anchor':place},'days':[]})
        request={**self.req,'evidence':[{'field':'landmark','source':'saved_place','source_id':'anchor','value':'西鉄福岡駅'}]}
        first=await self.service.search(request)
        place={**place,'coordinates':[139.7,35.7],'address':'東京'}
        self.store.sync_trajectory({'places':{'anchor':place},'days':[]})
        second=await self.service.search({**request,'reuse_search_id':first['searchId']})
        self.assertEqual(second['status'],'needs_clarification')
        self.assertEqual(second['candidates'],[])
