import asyncio,copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_agent_place_search as web_tests
from geolonia_fixtures import DETAILED_RESULT,COARSE_RESULT,ADDRESS,GEOLONIA_PLACE
from coordinate_fixtures import STORE_ROW

class Geolonia:
    def __init__(self):self.status='matched';self.results={}
    def session(self,key,budget):return self
    async def lookup(self,address,**kwargs):
        if address not in self.results:
            raw=copy.deepcopy(COARSE_RESULT if self.status=='coarse' else DETAILED_RESULT)
            self.results[address]={**raw,'status':self.status,'originalAddress':address,'matchedVariant':{'address':address,'strategies':['original']},'libraryVersion':'3.1.3','attempts':[{'inputAddress':address,'queryAddress':address,'strategies':['original'],'status':'complete'}],'unresolved':[] if self.status=='matched' else ['address_precision_unconfirmed' if self.status=='coarse' else 'geolonia_network']}
        return copy.deepcopy(self.results[address])
    async def close(self):pass

class GeoloniaSearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await web_tests.SearchTests.asyncSetUp(self)
        self.geo=Geolonia();self.service.geolonia=self.geo
        self.req={'query':'合成テスト店舗','place_id':'p'}
        self.provider.rows=[{**copy.deepcopy(STORE_ROW),'name':'合成テスト店舗','address':ADDRESS,'branch':''}]
        self.resolver.messages=[{'id':'u','role':'user','text':'合成テスト店舗 '+ADDRESS}]
        self.grounded={**self.req,'address':ADDRESS,'evidence':[{'field':'address','source':'user_message','source_id':'u','value':ADDRESS}]}

    async def asyncTearDown(self):await self.budget.close()

    async def test_discovered_abbreviated_branch_uses_detailed_geolonia_match(self):
        self.provider.rows[0].update(name='セブン-イレブン 千代田二番町店',branch='千代田二番町店')
        self.resolver.messages=[{'id':'u','role':'user','text':ADDRESS}]
        out=await self.service.search({**self.grounded,'query':'セブン-イレブン 千代田店','brand':'セブン-イレブン','branch':'千代田店'})
        self.assertEqual(out['candidates'][0]['coordinateEvidence']['status'],'address_matched')
        self.assertIn('branch_unconfirmed',out['candidates'][0]['matchReasons'])
        self.assertIn('入力の支店名',out['candidates'][0]['coordinateEvidence']['note'])
        self.assertEqual(self.verifier.calls,[])

    async def test_transaction_brand_alias_keeps_geolonia_first(self):
        from test_merchant_address import DRAFT
        transaction=self.store.create_transaction({**DRAFT,'merchant':'FamilyMart','merchantAddress':ADDRESS})
        out=await self.service.search({'query':'ファミリーマート','brand':'ファミリーマート','place_id':'p','address':ADDRESS,'evidence':[{'field':'address','source':'transaction','source_id':transaction['id'],'value':ADDRESS}]})
        self.assertEqual(out['candidates'][0]['coordinateEvidence']['status'],'address_matched')
        self.assertEqual(self.provider.calls,[])

    async def test_grounded_address_uses_geolonia_before_web(self):
        out=await self.service.search(self.grounded)
        self.assertEqual(out['candidates'][0]['coordinateEvidence']['status'],'address_matched')
        self.assertEqual(self.provider.calls,[])
        self.assertEqual(out['status'],'found')

    async def test_unknown_address_researches_store_then_geolonia(self):
        out=await self.service.search(self.req)
        self.assertEqual(out['candidates'][0]['coordinateEvidence']['status'],'address_matched')
        self.assertEqual([a[0] for a in self.provider.calls],['web','extract'])
        self.assertEqual(self.verifier.calls,[])

    async def test_coarse_or_geolonia_failure_falls_back_to_web(self):
        for status in ('coarse','failed','unavailable'):
            self.geo=Geolonia();self.geo.status=status;self.service.geolonia=self.geo
            out=await self.service.search(self.grounded)
            self.assertEqual(out['candidates'][0]['coordinateEvidence']['version'],1)
            self.assertEqual(out['status'],'found')
            self.assertNotIn('openai',self.budget.stopped)

    async def test_supplemental_history_survives_and_is_not_selectable(self):
        self.geo.status='coarse'
        out=await self.service.search(self.grounded)
        saved=self.searches.get(self.ctx['thread_id'],out['searchId'])['result']
        self.assertEqual(saved['geolonia']['supplementalMatches'][0]['pointLevel'],3)
        self.assertNotIn('id',saved['geolonia']['supplementalMatches'][0])
        self.assertTrue(all(c['coordinateEvidence']['version']==1 for c in saved['candidates']))
        attempts=self.searches.get(self.ctx['thread_id'],out['searchId'])['attempts']
        self.assertTrue(any(a['stage']=='geolonia' for a in attempts))

    async def test_saved_and_explicit_reuse_do_not_fetch(self):
        first=await self.service.search(self.grounded)
        self.geo.results={}
        reused=await self.service.search({**self.grounded,'reuse_search_id':first['searchId']})
        self.assertEqual(self.geo.results,{})
        self.assertEqual(reused['reusedFrom']['searchId'],first['searchId'])
        self.store.sync_trajectory({'places':{'existing':GEOLONIA_PLACE},'days':[]})
        saved=await self.service.search(self.grounded)
        self.assertEqual(saved['candidates'][0]['savedPlaceId'],'existing')
        self.assertEqual(self.geo.results,{})

    async def test_old_pipeline_reuse_requires_research(self):
        first=await self.service.search(self.grounded)
        old=copy.deepcopy(first);old['pipelineVersion']='web-coordinates-v1'
        sid=self.searches.start(self.ctx,self.grounded);self.searches.finish(self.ctx,sid,old)
        self.assertEqual((await self.service.search({**self.grounded,'reuse_search_id':sid}))['status'],'needs_clarification')

    async def test_parallel_searches_share_geo_but_rebind_ids(self):
        first,second=await asyncio.gather(self.service.search(self.grounded),self.service.search({**self.grounded,'place_id':'second'}))
        self.assertNotEqual(first['searchId'],second['searchId'])
        self.assertNotEqual(first['candidates'][0]['coordinateEvidence']['addressMatch']['fetches'][0]['sourceId'],second['candidates'][0]['coordinateEvidence']['addressMatch']['fetches'][0]['sourceId'])

    async def test_address_without_store_association_cannot_be_direct_candidate(self):
        self.resolver.messages=[{'id':'u','role':'user','text':ADDRESS}]
        self.provider.rows=[]
        out=await self.service.search(self.grounded)
        self.assertEqual(out['candidates'],[])
        self.assertTrue(self.provider.calls)

    async def test_unrelated_or_negated_user_addresses_require_web_discovery(self):
        for message in (
            '合成テスト店舗の住所は分かりません。別の店の住所は'+ADDRESS+'です。',
            '合成テスト店舗と別の店。別の店の住所: '+ADDRESS,
            '合成テスト店舗の住所は'+ADDRESS+'ではありません。',
        ):
            with self.subTest(message=message):
                await self.budget.close()
                import time
                self.budget=web_tests.SearchBudget(time.monotonic()+180)
                self.service.budget=self.budget
                self.resolver.messages=[{'id':'u','role':'user','text':message}]
                self.provider.calls=[]
                out=await self.service.search(self.grounded)
                self.assertTrue(self.provider.calls)
                self.assertEqual(out['status'],'found')

    async def test_direct_affirmative_user_address_pair_can_skip_web(self):
        self.resolver.messages=[{'id':'u','role':'user','text':'合成テスト店舗の住所は'+ADDRESS+'です。'}]
        out=await self.service.search(self.grounded)
        self.assertEqual(out['candidates'][0]['coordinateEvidence']['version'],2)
        self.assertEqual(self.provider.calls,[])

    async def test_nested_malformed_worker_response_falls_back_to_web(self):
        import tempfile
        from agent.geolonia_client import GeoloniaClient
        with tempfile.TemporaryDirectory() as directory:
            worker=Path(directory)/'worker.py'
            worker.write_text('import json,sys\nfor line in sys.stdin:\n r=json.loads(line)\n print(json.dumps({"id":r["id"],"status":"ok","bytesRead":0,"libraryVersion":"3.1.3","match":{"point":"bad"},"proof":{}}),flush=True)\n')
            client=GeoloniaClient(executable=sys.executable,worker_path=worker)
            self.service.geolonia=client
            try:
                out=await self.service.search(self.grounded)
                self.assertEqual(out['candidates'][0]['coordinateEvidence']['version'],1)
                self.assertTrue(self.provider.calls)
                self.assertIn('geolonia_invalid_response',out['geolonia']['unresolved'])
                self.assertTrue(all(s.process is None for s in client.sessions.values()))
            finally:await client.close()

    async def test_country_outside_japan_skips_geolonia(self):
        self.resolver.messages=[{'id':'u','role':'user','text':'us'}]
        out=await self.service.search({**self.req,'country_code':'us','evidence':[{'field':'country_code','source':'user_message','source_id':'u','value':'us'}]})
        self.assertEqual(self.geo.results,{})

    # The inherited tests use their original fixtures, not our synthetic Tokyo store.
    async def test_geolonia_failure_does_not_stop_web_provider(self):
        self.geo.status='failed'
        out=await self.service.search(self.grounded)
        self.assertEqual(out['status'],'found');self.assertTrue(out['candidates'])
