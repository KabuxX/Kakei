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
        self.calls.append(('web',{**request,'strategy':kwargs.get('strategy')}))
        if self.error:raise self.error
        return {'text':'synthetic','sources':[],'actions':[],'usage':{},'retrievedAt':1}
    async def extract(self,report,**kwargs):self.calls.append(('extract',report));return copy.deepcopy(self.rows)
class Verifier:
    def __init__(self):self.calls=[];self.error=None;self.block=None
    async def __aexit__(self,*args):pass
    async def verify(self,place,**kwargs):
        self.calls.append(place['address'])
        if self.block:await self.block.wait()
        if self.error:raise self.error
        from coordinate_fixtures import PUBLISHED_PLACE
        candidate={**copy.deepcopy(PUBLISHED_PLACE),'name':place['name'],'address':place['address'],'sources':place['sources'],'matchReasons':['store_and_address_verified']}
        sid=place['sources'][0]['id'];candidate['coordinateEvidence']['sourceIds']=[sid];candidate['coordinateEvidence']['observations'][0]['sourceId']=sid
        return {'candidates':[candidate],'anchors':[],'verifiedHints':[],'unresolved':[]}


class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_visit_date_is_grounded_and_warns_before_selection(self):
        self.resolver.messages=[{'id':'dated','role':'user','text':'2026年10月2日の軌跡を作成して'}]
        dated={**self.req,'visit_date':'2026-10-02','evidence':[{'field':'visit_date','source':'user_message','source_id':'dated','value':'2026-10-02'}]}
        out=await self.service.search(dated)
        evidence=out['candidates'][0]['coordinateEvidence']
        self.assertIn('2026-10-02',evidence['note']);self.assertIn('当時の所在地は未確認',evidence['note'])
        self.assertEqual(evidence['verification'],'needs_confirmation')
        self.assertEqual(self.provider.calls[0][1]['visit_date'],'2026-10-02')
        self.assertEqual((await self.service.search({**dated,'visit_date':'2026-10-03'}))['status'],'needs_clarification')
        with self.assertRaises(ValidationError):await self.service.search({**self.req,'visit_date':'2026-10-02'})

    async def test_verification_deadline_preserves_page_result_and_history(self):
        from agent.web_coordinates import WebCoordinateVerifier
        from test_web_coordinates import page,article
        from coordinate_fixtures import STORE_ROW
        from web_place_fixtures import SOURCE
        budget=SearchBudget(time.monotonic()+15.02)
        class Pages:
            async def fetch(self,url,**kwargs):
                async def get(timeout):
                    if url==SOURCE['url']:return page(article())
                    await asyncio.sleep(1)
                return await budget.run('page',url,get)
        row={**STORE_ROW,'sources':[SOURCE,{**SOURCE,'id':'s2','url':'https://second.example/store'}]}
        try:
            out=await budget.verify('partial',lambda t:WebCoordinateVerifier(Pages(),budget).verify(row,timeout=t))
            self.assertEqual(len(out['candidates']),1);self.assertIn('timeout',out['unresolved'])
            self.assertEqual(out['pages'][1]['result'],'timeout')
        finally:await budget.close()

    async def test_verification_page_history_is_persisted(self):
        original=self.verifier.verify
        async def verify(*args,**kwargs):
            out=await original(*args,**kwargs)
            out['pages']=[{'url':'https://example.com/store','finalUrl':'https://example.com/map','redirects':['https://example.com/map'],'result':'verified','sourceId':'s1'}]
            return out
        self.verifier.verify=verify
        out=await self.service.search(self.req)
        attempt=next(a for a in self.searches.get(self.ctx['thread_id'],out['searchId'])['attempts'] if a['stage']=='verify')
        self.assertEqual(attempt['pages'][0]['finalUrl'],'https://example.com/map')

    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store,self.agent,self.ctx=active_turn(Path(self.tmp.name)/'db')
        self.searches=AgentSearchStore(self.store.db_path);self.provider=Provider();self.verifier=Verifier()
        self.resolver=EvidenceResolver(self.store,self.searches,self.ctx['thread_id'],[])
        self.budget=SearchBudget(time.monotonic()+120)
        self.service=PlaceSearchService(self.provider,self.verifier,self.searches,self.resolver,self.ctx,self.budget)
        self.req={**SEARCH,'query':'ドトールコーヒーショップ 西鉄福岡駅店'}
    async def asyncTearDown(self):await self.budget.close()
    async def test_web_failure_persists_partial_search(self):
        self.verifier.error=PlaceProviderError('network')
        out=await self.service.search(self.req)
        rec=self.searches.get(self.ctx['thread_id'],out['searchId'])
        self.assertEqual(out['pipelineVersion'],'geolonia-web-coordinates-v3');self.assertEqual(out['status'],'partial')
        self.assertEqual([a['stage'] for a in rec['attempts']][:3],['web','extract','verify'])
        self.assertEqual(out['unlocatedCandidates'][0]['address'],WEB_PLACE['address']);self.assertEqual(out['candidates'],[])
    async def test_parallel_duplicate_searches_have_distinct_ids_and_shared_requests(self):
        a,b=await asyncio.gather(self.service.search(self.req),self.service.search({**self.req,'place_id':'b'}))
        self.assertEqual(len(self.provider.calls),2);self.assertEqual(len(self.verifier.calls),1)
        self.assertNotEqual(a['candidates'][0]['id'],b['candidates'][0]['id']);self.assertNotEqual(a['sources'][0]['id'],b['sources'][0]['id'])
    async def test_shared_stage_budgets_and_deadlines(self):
        seen=[];running=0;maximum=0
        async def invoke(timeout):
            nonlocal running,maximum
            running+=1;maximum=max(maximum,running);seen.append(timeout);await asyncio.sleep(.001);running-=1;return []
        for stage,limit in (('web',6),('extract',6),('page',16)):
            out=await asyncio.gather(*(self.budget.run(stage,str(i),invoke) for i in range(limit+1)),return_exceptions=True)
            self.assertEqual(sum(isinstance(x,SearchLimit) for x in out),1)
        self.assertLessEqual(maximum,6)
        geo_only=SearchBudget(time.monotonic()+120);maximum=0
        await asyncio.gather(*(geo_only.run('page',str(i),invoke) for i in range(5)))
        self.assertEqual(maximum,3);await geo_only.close()
        late=SearchBudget(180,clock=lambda:166)
        with self.assertRaises(SearchLimit):await late.run('web','x',invoke)
        await late.close()
        clock=[0];timed=SearchBudget(200,clock=lambda:clock[0]);await timed.run('web','a',invoke);clock[0]=146
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
        self.verifier.block=asyncio.Event();task=asyncio.create_task(self.service.search(self.req))
        async def started():
            while not self.verifier.calls:
                if task.done():await task
                await asyncio.sleep(.001)
        await asyncio.wait_for(started(),1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        rec=self.searches.history(self.ctx['thread_id'])['records'][0]
        self.assertEqual(rec['status'],'cancelled');self.assertEqual(rec['attempts'][0]['status'],'complete');self.assertEqual(rec['attempts'][-1]['status'],'cancelled')
    async def test_rate_limit_stops_only_affected_provider(self):
        self.provider.error=PlaceProviderError('rate_limited',stop_turn=True)
        await self.service.search(self.req)
        await self.service.search({**self.req,'query':self.req['query']+'2'})
        self.assertEqual(len(self.verifier.calls),0);self.assertEqual(len(self.provider.calls),1)
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
            commands,metadata=choose(c,[],{'placeCandidates':[out]},candidate_id=candidate['id'],confirmed=True)
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
    async def test_address_format_is_ignored_by_new_search(self):
        self.verifier.error=PlaceProviderError('network')
        await self.service.search({**self.req,'address_format':'original'})
        await self.service.search({**self.req,'address_format':'japanese'})
        self.assertEqual(len(self.provider.calls),8)
        self.assertEqual(len(self.verifier.calls),1)
        with self.assertRaises(ValidationError):await self.service.search({**self.req,'address_format':'invented'})
    async def test_same_name_new_address_cannot_reuse_old_coordinates(self):
        from test_merchant_address import DRAFT
        record=self.store.create_transaction({**DRAFT,'merchantAddress':WEB_PLACE['address']})
        def req(address):return {**self.req,'address':address,'evidence':[{'field':'address','source':'transaction','source_id':record['id'],'value':address}]}
        first=await self.service.search(req(WEB_PLACE['address']))
        self.assertEqual(len(first['candidates']),1)
        self.store.update_transaction(record['id'],{**DRAFT,'merchantAddress':'福岡市中央区天神2-11-30'})
        second=await self.service.search(req('福岡市中央区天神2-11-30'))
        self.assertEqual(second['candidates'],[])
        self.assertIn('address_mismatch',second['unlocatedCandidates'][0]['unresolved'])
        self.assertEqual(len([c for c in self.provider.calls if c[0]=='web']),5)
        with self.assertRaises(ValidationError):await self.service.search({**req('福岡市中央区天神2-11-30'),'reuse_search_id':first['searchId']})

    async def test_conflicting_published_coordinates_are_not_averaged(self):
        from agent.place_search import compare_candidates
        from coordinate_fixtures import PUBLISHED_PLACE
        values=compare_candidates([PUBLISHED_PLACE,{**copy.deepcopy(PUBLISHED_PLACE),'coordinates':[131,34]}])
        self.assertEqual(len(values),2)
        self.assertTrue(all('coordinate_conflict' in c['matchReasons'] for c in values))
    async def test_maps_then_anchor_returns_grounded_estimate(self):
        from coordinate_fixtures import BUILDING_HINT,ANCHOR
        self.provider.rows[0]['hints']=[BUILDING_HINT]
        original=self.provider.research
        async def research(request,**kw):
            report=await original(request,**kw);report['strategy']=kw['strategy'];return report
        self.provider.research=research
        async def extract(report,**kw):
            if report['strategy']=='anchor':return [{**copy.deepcopy(WEB_PLACE),'role':'anchor','name':ANCHOR['name'],'address':ANCHOR['address'],'branch':''}]
            return copy.deepcopy(self.provider.rows)
        self.provider.extract=extract
        async def verify(place,**kw):
            return {'candidates':[],'anchors':[ANCHOR] if place.get('role')=='anchor' else [],'unresolved':[],'verifiedHints':[BUILDING_HINT] if place.get('role')!='anchor' else []}
        self.verifier.verify=verify
        out=await self.service.search(self.req)
        self.assertEqual(out['candidates'][0]['coordinateEvidence']['status'],'estimated')
        self.assertEqual(out['pipelineVersion'],'geolonia-web-coordinates-v3')
        self.assertEqual([call[1]['strategy'] for call in self.provider.calls if call[0]=='web'],['store','maps','address','anchor'])
    async def test_same_url_relationship_discovered_later_keeps_resolvable_ids(self):
        from agent.place_search import unique_stores
        from coordinate_fixtures import STORE_ROW,BUILDING_HINT,ANCHOR
        from agent.coordinate_estimation import estimate_coordinates
        first=copy.deepcopy(STORE_ROW)
        later={**copy.deepcopy(STORE_ROW),'sources':[{**first['sources'][0],'id':'s2'}],'verifiedHints':[{**copy.deepcopy(BUILDING_HINT),'relationSourceIds':['s2']}]}
        merged=unique_stores([first,later])[0]
        self.assertEqual(merged['verifiedHints'][0]['relationSourceIds'],['s1'])
        self.assertEqual(len(estimate_coordinates(merged,[ANCHOR])),1)

    async def test_same_url_estimate_sources_rebind_and_remain_selectable(self):
        from coordinate_fixtures import ESTIMATED_PLACE,SOURCE
        from services.coordinate_evidence import validate_coordinate_evidence
        from services.agent_places import choose
        candidate=copy.deepcopy(ESTIMATED_PLACE)
        candidate['sources'].append({**SOURCE,'id':'s2'})
        candidate['coordinateEvidence']['sourceIds'].append('s2')
        candidate['coordinateEvidence']['observations'][0]['sourceId']='s2'
        self.store.sync_trajectory({'places':{'saved':{**candidate,'placeEvidence':'provider'}},'days':[]})
        result=await self.service.search(self.req)
        selected=result['candidates'][0];validate_coordinate_evidence(selected)
        self.assertEqual(len(selected['coordinateEvidence']['sourceIds']),1)
        with self.store._connection() as c:
            commands,_=choose(c,[],{'placeCandidates':[result]},candidate_id=selected['id'],confirmed=True)
        self.assertEqual(commands,[])
