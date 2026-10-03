import asyncio,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.places import GeoapifyProvider, PlaceProviderError

class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env=patch.dict('os.environ',{'GEOAPIFY_API_KEY':'secret'});self.env.start();self.addCleanup(self.env.stop)

    async def test_japanese_geocoding_and_scoped_places(self):
        def serve(r):
            self.assertEqual(r.url.params['lang'],'ja')
            if r.url.path.endswith('places'):
                self.assertEqual(r.url.params['limit'],'20')
                self.assertEqual(r.url.params['filter'],'circle:130.4,33.59,1000')
                return httpx.Response(200,json={'features':[{'properties':{'name':'店','lon':130.4,'lat':33.59,'city':'福岡市','datasource':{'url':'https://user:secret@www.openstreetmap.org/copyright?apiKey=secret'}}}]})
            self.assertEqual(r.url.params['limit'],'5');self.assertNotIn('filter',r.url.params)
            return httpx.Response(200,json={'results':[]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as c:
            async with GeoapifyProvider(c) as p:
                self.assertEqual(await p.geocode('店',timeout=1),[])
                results=await p.nearby('店',category='catering.cafe',region={'kind':'point','coordinates':[130.4,33.59]},timeout=1)
            self.assertFalse(c.is_closed)
        self.assertEqual(results[0]['city'],'福岡市')
        self.assertNotIn('secret',json.dumps(results))

    async def test_partial_stream_timeout_and_cancellation(self):
        async def slow(r): await asyncio.sleep(10)
        async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as c:
            p=GeoapifyProvider(c)
            with self.assertRaises(PlaceProviderError) as got: await p.geocode('店',timeout=.01)
            self.assertEqual(got.exception.code,'timeout')
            task=asyncio.create_task(p.geocode('店',timeout=5)); await asyncio.sleep(0);task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task

    async def test_malformed_and_oversized_payload(self):
        for payload in ({'results':'wrong'}, ['wrong'], {'results':[{'name':'x','lon':float('inf'),'lat':0}]}, {'results':[], 'big':'x'*65536}):
            raw=json.dumps(payload).encode()
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=raw))) as c:
                p=GeoapifyProvider(c)
                if isinstance(payload,dict) and payload.get('results') and isinstance(payload['results'],list):
                    rows=await p.geocode('店',timeout=1); self.assertIn('invalid_coordinates',rows[0]['validationErrors'])
                else:
                    with self.assertRaises(PlaceProviderError) as got: await p.geocode('店',timeout=1)
                    self.assertEqual(got.exception.code,'invalid_response')

    async def test_errors_and_boundary(self):
        for status,code,stop in [(401,'auth',True),(403,'auth',True),(429,'rate_limited',True),(500,'network',False)]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(status))) as c:
                with self.assertRaises(PlaceProviderError) as got: await GeoapifyProvider(c).geocode('店',timeout=1)
                self.assertEqual((got.exception.code,got.exception.stop_turn),(code,stop))
        def serve(r):
            self.assertEqual(r.url.params['filter'],'place:boundary-1')
            return httpx.Response(200,json={'features':[]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as c:
            self.assertEqual(await GeoapifyProvider(c).nearby('cafe',category='catering.cafe',region={'kind':'boundary','provider_id':'boundary-1'},timeout=1),[])
