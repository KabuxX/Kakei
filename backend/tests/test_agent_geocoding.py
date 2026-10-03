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
