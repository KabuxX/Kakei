import asyncio,copy,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.geocoding import MapboxGeocoder,match_address
from agent.place_http import PlaceProviderError
from web_place_fixtures import WEB_PLACE,ADDRESS,feature

class GeocodeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        e=patch.dict(os.environ,{'MAPBOX_GEOCODING_ACCESS_TOKEN':'secret'});e.start();self.addCleanup(e.stop)
    async def test_permanent_geocoding_for_japan_and_overseas(self):
        for place in (WEB_PLACE,{**WEB_PLACE,'address':'10 Downing Street, London','locality':'London','country_code':'gb'}):
            seen=[]
            def handle(req):seen.append(dict(req.url.params));return httpx.Response(200,json={'features':[feature(place['address'],place['country_code'])]})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:out=await MapboxGeocoder(c).geocode(place,timeout=1)
            self.assertEqual(seen[0]['permanent'],'true');self.assertEqual(seen[0]['autocomplete'],'false');self.assertEqual(seen[0]['language'],'ja');self.assertEqual(seen[0]['country'],place['country_code']);self.assertEqual(len(out['candidates']),1)
            self.assertNotIn('secret',str(out))
    async def test_address_number_and_precision_gate(self):
        self.assertEqual(match_address({**WEB_PLACE,'address':ADDRESS.replace('1丁目2-3','１丁目２－３')},feature()),[])
        self.assertEqual(match_address({**WEB_PLACE,'address':ADDRESS.replace('1丁目','一丁目')},feature()),[])
        cases=[feature(ADDRESS+'0'),feature(feature_type='block'),feature(feature_type='place'),feature(country='gb'),feature(match_code={}),feature(match_code={'confidence':'exact','address_number':'inferred'}),feature(coordinates={'longitude':True,'latitude':33,'accuracy':'rooftop'}),feature(coordinates={'longitude':float('nan'),'latitude':33,'accuracy':'rooftop'})]
        for f in cases:
            with self.subTest(f=f):self.assertTrue(match_address(WEB_PLACE,f))
        f=feature(coordinates={'longitude':130.4,'latitude':33.59,'accuracy':'interpolated'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'features':[f]}))) as c:
            out=await MapboxGeocoder(c).geocode(WEB_PLACE,timeout=1)
        self.assertEqual(out['candidates'][0]['geocoding']['accuracy'],'interpolated')
    async def test_ambiguous_address_remains_unlocated(self):
        other=feature(coordinates={'longitude':131,'latitude':33.59,'accuracy':'rooftop'},mapbox_id='other')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'features':[feature(),other]}))) as c:
            out=await MapboxGeocoder(c).geocode(WEB_PLACE,timeout=1)
        self.assertEqual(out['candidates'],[]);self.assertIn('ambiguous_address',out['unresolved'])
    async def test_mapbox_failure_never_uses_temporary_mode(self):
        for status in (401,403,429):
            requests=[]
            def handle(req):requests.append(req);return httpx.Response(status,json={})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
                with self.assertRaises(PlaceProviderError):await MapboxGeocoder(c).geocode(WEB_PLACE,timeout=1)
            self.assertEqual(len(requests),1);self.assertEqual(requests[0].url.params['permanent'],'true')
    async def test_invalid_inputs_make_no_request(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:self.fail('unexpected request'))) as c:
            for p in ({**WEB_PLACE,'country_code':''},{**WEB_PLACE,'address':'長'*257}):
                out=await MapboxGeocoder(c).geocode(p,timeout=1);self.assertEqual(out['candidates'],[])
    async def test_address_suffix_cannot_hide_a_missing_house_number(self):
        partial=ADDRESS.replace('2-3','2')
        self.assertIn('address_mismatch',match_address({**WEB_PLACE,'address':partial+'の3'},feature(partial)))
        self.assertIn('address_mismatch',match_address({**WEB_PLACE,'address':partial+'番外地3'},feature(partial)))
        self.assertEqual(match_address({**WEB_PLACE,'address':ADDRESS+' 天神ビル'},feature()),[])
    async def test_japanese_address_equivalence_and_review_gate(self):
        place={**WEB_PLACE,'address':'〒810-0001 福岡県福岡市中央区天神2-11-3','locality':'福岡市中央区'}
        address='日本, 〒810-0001 福岡県福岡市中央区天神２丁目１１番３号'
        good=feature(address)
        self.assertEqual(match_address(place,good),[])
        self.assertEqual(match_address({**place,'address':place['address'].replace('2-11-3','二丁目11の3')},good),[])
        real=feature(address,match_code={'address_number':'unmatched','block':'unmatched','neighborhood':'unmatched','place':'matched','country':'matched'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'features':[real]}))) as c:
            out=await MapboxGeocoder(c).geocode(place,timeout=1)
        self.assertEqual(out['candidates'][0]['geocoding']['verification'],'needs_confirmation')
        self.assertEqual(out['candidates'][0]['geocoding']['matchCode']['address_number'],'unmatched')
        for bad in (feature(address.replace('３号','２号')),feature(address.replace('810-0001','810-0002')),feature(address,feature_type='block'),feature(address,country='gb')):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'features':[bad]}))) as c:
                self.assertEqual((await MapboxGeocoder(c).geocode(place,timeout=1))['candidates'],[])
    async def test_agent_can_choose_equivalent_geocoding_query_formats(self):
        place={**WEB_PLACE,'address':'〒810-0001 福岡県福岡市中央区天神2-11-3'}
        seen=[]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:(seen.append(req.url.params['q']) or httpx.Response(200,json={'features':[]})))) as c:
            for fmt in ('original','without_postcode','japanese'):
                await MapboxGeocoder(c).geocode({**place,'address_format':fmt},timeout=1)
        self.assertEqual(seen,[place['address'],'福岡県福岡市中央区天神2-11-3','福岡県福岡市中央区天神2丁目11番3号'])

    async def test_missing_match_code_is_reviewable_without_fabricating_provider_confidence(self):
        f=feature();f['properties'].pop('match_code')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'features':[f]}))) as c:
            out=await MapboxGeocoder(c).geocode(WEB_PLACE,timeout=1)
        self.assertEqual(out['candidates'][0]['geocoding']['matchCode'],{})
        self.assertEqual(out['candidates'][0]['geocoding']['verification'],'needs_confirmation')

    async def test_structured_postcode_conflicts_are_not_reviewable(self):
        place={**WEB_PLACE,'address':'〒810-0001 '+ADDRESS}
        for address in (ADDRESS,'日本, 〒810-0001 '+ADDRESS):
            f=feature(address,match_code={'address_number':'matched','postcode':'unmatched'})
            f['properties']['context']['postcode']={'name':'810-9999'}
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'features':[f]}))) as c:
                out=await MapboxGeocoder(c).geocode(place,timeout=1)
            self.assertEqual(out['candidates'],[])
            self.assertIn('postcode_mismatch',out['unresolved'])

    async def test_malformed_match_codes_are_rejected_without_crashing(self):
        for code in ('unexpected',['matched'],True,0):
            with self.subTest(code=code):
                f=feature(match_code=code)
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'features':[f]}))) as c:
                    out=await MapboxGeocoder(c).geocode(WEB_PLACE,timeout=1)
                self.assertEqual(out['candidates'],[])
                self.assertIn('invalid_record',out['unresolved'])
