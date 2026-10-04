import asyncio, sys, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.google_places import GoogleCandidate, GooglePlacesError
from services.google_place_resolution import VisitInput, VisitResolver
from google_places_fixtures import place

class Client:
    def __init__(self, responses): self.responses=responses; self.queries=[]; self.active=0; self.max_active=0
    async def search_text(self, query, **kwargs):
        self.queries.append(query); self.active+=1; self.max_active=max(self.max_active,self.active)
        try:
            await asyncio.sleep(0)
            value=self.responses[min(len(self.queries)-1,len(self.responses)-1)]
            if isinstance(value,Exception): raise value
            return [GoogleCandidate.from_payload(p) for p in value]
        finally: self.active-=1

class ResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def resolve(self, label, address, responses):
        client=Client(responses)
        return await VisitResolver(client,deadline=time.monotonic()+120).resolve(VisitInput('t',label,address)),client

    async def test_variants_preserve_branch_and_address(self):
        resolved,client=await self.resolve('ｾﾌﾞﾝ‐ｲﾚﾌﾞﾝ 千代田店','〒102-0084 東京都千代田区二番町８−８', [[],[place()]])
        self.assertEqual(resolved.provider_place_id,'fixture-chiyoda')
        self.assertEqual(len(client.queries),2)
        resolved,_=await self.resolve('ファミリーマート バスターミナル東京八重洲／Ｓ店', '東京都中央区八重洲二丁目二番一号 地下2階',
            [[place('yaesu','ファミリーマート バスターミナル東京八重洲/S店','東京都中央区八重洲2-2-1 東京ミッドタウン八重洲 B2F')]])
        self.assertEqual(resolved.provider_place_id,'yaesu')

    async def test_ambiguous_and_address_only_are_excluded(self):
        resolved,_=await self.resolve('セブン-イレブン 千代田店',None, [[place('a'),place('b')]])
        self.assertEqual(resolved.reason,'ambiguous')
        for candidate in [place('address','二番町8-8'), place('other','セブン-イレブン 麹町店'),place('wrong-address',address='東京都千代田区二番町9-9')]:
            result,_=await self.resolve('セブン-イレブン 千代田店','東京都千代田区二番町8-8', [[candidate]])
            self.assertEqual(result.reason,'identity_mismatch')
        result,_=await self.resolve('セブン-イレブン',None,[[place()]])
        self.assertEqual(result.reason,'insufficient_identity')

    async def test_reordered_full_page_and_duplicate_ids(self):
        candidates=[place(str(i),'別の店舗'+str(i)) for i in range(9)]+[place()]
        for row in [candidates,list(reversed(candidates)),[place(),place()]]:
            result,_=await self.resolve('セブン-イレブン 千代田店',None,[row])
            self.assertEqual(result.provider_place_id,'fixture-chiyoda')

    async def test_four_requests_three_workers_and_deadline(self):
        client=Client([[]]);resolver=VisitResolver(client,deadline=time.monotonic()+120)
        visits=[VisitInput(str(i),'セブン-イレブン 支店'+str(i)+'店','東京都千代田区二番町8-8 建物名 地下2階') for i in range(8)]
        results=await resolver.resolve_many(visits)
        self.assertTrue(all(r.reason=='not_found' for r in results))
        self.assertLessEqual(len(client.queries),32);self.assertLessEqual(client.max_active,3)
        expired=await VisitResolver(client,deadline=0).resolve(visits[0])
        self.assertEqual(expired.reason,'budget_exceeded')
        same=Client([[place()]]);resolver=VisitResolver(same,deadline=time.monotonic()+120)
        shared=await resolver.resolve_many([VisitInput('a','セブン-イレブン 千代田店',None),VisitInput('b','セブン-イレブン 千代田店',None)])
        self.assertEqual([r.transaction_id for r in shared],['a','b']);self.assertEqual(len(same.queries),1)

    async def test_transient_failure_and_configuration_stop(self):
        result,client=await self.resolve('セブン-イレブン 千代田店',None,[GooglePlacesError('unavailable'),[place()]])
        self.assertEqual(result.provider_place_id,'fixture-chiyoda');self.assertEqual(len(client.queries),2)
        result,client=await self.resolve('セブン-イレブン 千代田店',None,[GooglePlacesError('configuration'),[place()]])
        self.assertEqual(result.reason,'provider_configuration');self.assertEqual(len(client.queries),1)
        result,_=await self.resolve('セブン-イレブン 千代田店',None,[[place(coordinates=None)]])
        self.assertEqual(result.reason,'missing_coordinates')
