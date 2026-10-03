import asyncio,copy,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.place_search import PlaceSearchService,SearchBudget,SearchLimit
from agent.place_matching import EvidenceResolver
from agent.place_http import PlaceProviderError
from db.agent_search_store import AgentSearchStore
from services.validation import ValidationError
from agent_search_fixtures import active_turn,SEARCH,SHOP
from web_place_fixtures import WEB_PLACE,GEOCODING,PLACE

class Provider:
    def __init__(self):self.calls=[];self.rows=[copy.deepcopy(WEB_PLACE)];self.error=None
    async def __aexit__(self,*args):pass
    async def research(self,request,**kwargs):
        self.calls.append(('web',request))
        if self.error:raise self.error
        return {'text':'synthetic','sources':[],'actions':[],'usage':{},'retrievedAt':1}
    async def extract(self,report,**kwargs):self.calls.append(('extract',report));return copy.deepcopy(self.rows)
class Geocoder:
    def __init__(self):self.calls=[];self.error=None;self.block=None
    async def __aexit__(self,*args):pass
    async def geocode(self,place,**kwargs):
        self.calls.append(place['address'])
        if self.block:await self.block.wait()
        if self.error:raise self.error
        return {'candidates':[{'coordinates':[130.4,33.59],'geocoding':copy.deepcopy(GEOCODING)}],'unresolved':[]}

class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store,self.agent,self.ctx=active_turn(Path(self.tmp.name)/'db')
        self.searches=AgentSearchStore(self.store.db_path);self.provider=Provider();self.geocoder=Geocoder()
        self.resolver=EvidenceResolver(self.store,self.searches,self.ctx['thread_id'],[])
        self.budget=SearchBudget(time.monotonic()+120)
        self.service=PlaceSearchService(self.provider,self.geocoder,self.searches,self.resolver,self.ctx,self.budget)
        self.req={**SEARCH,'query':'ドトールコーヒーショップ 西鉄福岡駅店'}
    async def asyncTearDown(self):await self.budget.close()
    async def test_web_to_mapbox_persists_partial_search(self):
        self.geocoder.error=PlaceProviderError('network')
        out=await self.service.search(self.req)
        rec=self.searches.get(self.ctx['thread_id'],out['searchId'])
        self.assertEqual(out['pipelineVersion'],'web-mapbox-v1');self.assertEqual(out['status'],'partial')
        self.assertEqual([a['stage'] for a in rec['attempts']],['web','extract','geocode'])
        self.assertEqual(out['unlocatedCandidates'][0]['address'],WEB_PLACE['address']);self.assertEqual(out['candidates'],[])
    async def test_parallel_duplicate_searches_have_distinct_ids_and_shared_requests(self):
        a,b=await asyncio.gather(self.service.search(self.req),self.service.search({**self.req,'place_id':'b'}))
        self.assertEqual(len(self.provider.calls),2);self.assertEqual(len(self.geocoder.calls),1)
        self.assertNotEqual(a['candidates'][0]['id'],b['candidates'][0]['id']);self.assertNotEqual(a['sources'][0]['id'],b['sources'][0]['id'])
    async def test_shared_stage_budgets_and_deadlines(self):
        seen=[];running=0;maximum=0
        async def invoke(timeout):
            nonlocal running,maximum
            running+=1;maximum=max(maximum,running);seen.append(timeout);await asyncio.sleep(.001);running-=1;return []
        for stage,limit in (('web',3),('extract',3),('geocode',10)):
            out=await asyncio.gather(*(self.budget.run(stage,str(i),invoke) for i in range(limit+1)),return_exceptions=True)
            self.assertEqual(sum(isinstance(x,SearchLimit) for x in out),1)
        self.assertLessEqual(maximum,3)
        geo_only=SearchBudget(time.monotonic()+120);maximum=0
        await asyncio.gather(*(geo_only.run('geocode',str(i),invoke) for i in range(5)))
        self.assertEqual(maximum,2);await geo_only.close()
        late=SearchBudget(120,clock=lambda:111)
        with self.assertRaises(SearchLimit):await late.run('web','x',invoke)
        await late.close()
        clock=[0];timed=SearchBudget(200,clock=lambda:clock[0]);await timed.run('web','a',invoke);clock[0]=86
        with self.assertRaises(SearchLimit):await timed.run('web','b',invoke)
        await timed.close()
    async def test_refresh_reuse_and_latest_region(self):
        first=await self.service.search(self.req);n=len(self.provider.calls)
        again=await self.service.search({**self.req,'place_id':'b','reuse_search_id':first['searchId']})
        self.assertEqual(len(self.provider.calls),n);self.assertEqual(again['reusedFrom']['searchId'],first['searchId'])
        self.assertNotEqual(first['candidates'][0]['id'],again['candidates'][0]['id'])
        with self.assertRaises(ValidationError):await self.service.search({**self.req,'refresh':True,'reuse_search_id':first['searchId']})
        sid=self.searches.start(self.ctx,self.req);self.searches.finish(self.ctx,sid,{'status':'empty','candidates':[]})
        self.assertEqual((await self.service.search({**self.req,'reuse_search_id':sid}))['status'],'needs_clarification')
        self.store.sync_trajectory({'places':{'saved':PLACE},'days':[]})
        self.provider.calls=[]
        await self.service.search(self.req);self.assertEqual(self.provider.calls,[])
        await self.budget.close();self.service.budget=SearchBudget(time.monotonic()+120)
        await self.service.search({**self.req,'refresh':True});self.assertTrue(self.provider.calls);await self.service.budget.close()
    async def test_dedup_preserves_cotenant_stores(self):
        self.provider.rows += [{**copy.deepcopy(WEB_PLACE),'id':'duplicate','sources':[{**WEB_PLACE['sources'][0],'id':'another','url':'https://another.example/shop'}]}]
        out=await self.service.search(self.req);self.assertEqual(len(out['candidates']),1);self.assertEqual(len(out['candidates'][0]['sources']),2)
    async def test_different_stores_in_same_building_are_not_merged(self):
        self.provider.rows.append({**copy.deepcopy(WEB_PLACE),'id':'second','name':'ドトール 別店舗','branch':'別店舗'})
        out=await self.service.search({'query':'ドトール','brand':'ドトール','place_id':'p'})
        self.assertEqual(len(out['candidates']),2)

    async def test_cancel_preserves_finished_attempts(self):
        self.geocoder.block=asyncio.Event();task=asyncio.create_task(self.service.search(self.req))
        while not self.geocoder.calls:await asyncio.sleep(.001)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        rec=self.searches.history(self.ctx['thread_id'])['records'][0]
        self.assertEqual(rec['status'],'cancelled');self.assertEqual(rec['attempts'][0]['status'],'complete');self.assertEqual(rec['attempts'][-1]['status'],'cancelled')
    async def test_rate_limit_stops_only_affected_provider(self):
        self.geocoder.error=PlaceProviderError('rate_limited',stop_turn=True)
        await self.service.search(self.req)
        await self.service.search({**self.req,'query':self.req['query']+'2'})
        self.assertEqual(len(self.geocoder.calls),1);self.assertEqual(len(self.provider.calls),4)
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
    async def test_duplicate_url_citations_remain_selectable(self):
        from services.place_evidence import validate_sources
        from services.agent_places import choose
        self.provider.rows[0]['sources'].append({**self.provider.rows[0]['sources'][0],'id':'another'})
        out=await self.service.search(self.req)
        candidate=out['candidates'][0]
        self.assertEqual(len(candidate['sources']),1)
        validate_sources(candidate['sources'])
        with self.store._connection() as c:
            commands,metadata=choose(c,[],{'placeCandidates':[out]},candidate_id=candidate['id'])
        self.assertEqual(commands[0]['data']['name'],candidate['name'])

    async def test_result_size_omissions_are_partial_and_explicit(self):
        from web_place_fixtures import SOURCE
        from services.place_evidence import validate_sources
        from db.agent_search_store import size
        self.provider.rows=[]
        for i in range(5):
            refs=[{**SOURCE,'id':f's{i}{j}','title':'日本語の店舗出典'*20,'url':f'https://example.com/{i}/{j}?data='+'x'*1400} for j in range(3)]
            validate_sources(refs)
            self.provider.rows.append({**copy.deepcopy(WEB_PLACE),'name':f'店舗{i}','sources':refs})
        out=await self.service.search({'query':'店舗','place_id':'p'})
        self.assertLessEqual(size(out),40*1024)
        self.assertTrue(out['truncated'])
        self.assertEqual(out['status'],'partial')
        self.assertIn('省略',out['error'])
        self.assertGreater(out.get('omittedCandidates',0)+out.get('omittedSources',0),0)
        self.assertEqual({s['id'] for s in out['sources']},{s['id'] for c in out['candidates'] for s in c['sources']})
        for c in out['candidates']:validate_sources(c['sources'])
    async def test_format_retry_reuses_web_facts_but_retries_geocoding(self):
        self.geocoder.error=PlaceProviderError('network')
        await self.service.search({**self.req,'address_format':'original'})
        await self.service.search({**self.req,'address_format':'japanese'})
        self.assertEqual(len(self.provider.calls),2)
        self.assertEqual(len(self.geocoder.calls),2)
        with self.assertRaises(ValidationError):await self.service.search({**self.req,'address_format':'invented'})
