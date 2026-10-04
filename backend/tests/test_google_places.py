import asyncio, json, sys, unittest
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.google_places import GooglePlacesClient, GooglePlacesError
from google_places_fixtures import place

class GooglePlacesTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_search_contract(self):
        seen=[]
        def handle(request):
            seen.append(request)
            return httpx.Response(200, json={'places':[place()]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            async with GooglePlacesClient(client=http, api_key='server-secret') as client:
                results=await client.search_text('セブン-イレブン 千代田店 東京都千代田区二番町8-8', region_code='JP')
        request=seen[0]; body=json.loads(request.content)
        self.assertEqual(str(request.url), 'https://places.googleapis.com/v1/places:searchText')
        self.assertEqual(body['pageSize'],10); self.assertEqual(body['languageCode'],'ja')
        self.assertEqual(body['regionCode'],'JP')
        self.assertFalse(body['includePureServiceAreaBusinesses'])
        self.assertEqual(request.headers['x-goog-api-key'],'server-secret')
        self.assertEqual(set(request.headers['x-goog-fieldmask'].split(',')),{
            'places.id','places.displayName','places.formattedAddress','places.addressComponents',
            'places.location','places.types','places.googleMapsUri','places.attributions'})
        self.assertEqual(results[0].place_id,'fixture-chiyoda')
        self.assertEqual(results[0].coordinates,(139.737,35.685))

    async def test_details_and_errors(self):
        seen=[]
        def handle(request):
            seen.append(request); return httpx.Response(200,json=place())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            async with GooglePlacesClient(client=http,api_key='server-secret') as client:
                candidate=await client.details('fixture-chiyoda')
            self.assertFalse(http.is_closed)
        self.assertEqual(seen[0].method,'GET')
        self.assertEqual(seen[0].url.path,'/v1/places/fixture-chiyoda')
        self.assertEqual(candidate.display_name,'セブン-イレブン 千代田店')
        for status,code in [(401,'configuration'),(403,'configuration'),(429,'rate_limited'),(500,'unavailable'),(404,'not_found')]:
            with self.subTest(status=status):
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(status,json={'error':{'message':'server-secret'}}))) as http:
                    with self.assertRaises(GooglePlacesError) as caught:
                        await GooglePlacesClient(client=http,api_key='server-secret').details('p')
                self.assertEqual(caught.exception.code,code)
                self.assertNotIn('server-secret',str(caught.exception))

    async def test_invalid_response_and_coordinates(self):
        for content in [b'bad-json', b'{"places":NaN}', b'x'*524289, b'[]']:
            with self.subTest(content_size=len(content)):
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=content))) as http:
                    with self.assertRaises(GooglePlacesError):
                        await GooglePlacesClient(client=http,api_key='secret').search_text('店舗')
        for coordinates in [(200,35),(139,91),(True,35),(139,float('inf'))]:
            payload=place(coordinates=coordinates)
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=json.dumps({'places':[payload]})))) as http:
                with self.assertRaises(GooglePlacesError):
                    await GooglePlacesClient(client=http,api_key='secret').search_text('店舗')

    async def test_timeout_no_redirects_and_missing_key(self):
        async def timeout(request): raise httpx.ReadTimeout('secret',request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as http:
            with self.assertRaises(GooglePlacesError) as caught:
                await GooglePlacesClient(client=http,api_key='secret').search_text('店')
            self.assertEqual(caught.exception.code,'unavailable')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(302,headers={'Location':'https://example.org/secret'}))) as http:
            with self.assertRaises(GooglePlacesError):
                await GooglePlacesClient(client=http,api_key='secret').search_text('店')
        with self.assertRaises(GooglePlacesError) as caught:
            await GooglePlacesClient(api_key='').search_text('店')
        self.assertEqual(caught.exception.code,'configuration')

    async def test_details_identifier_cannot_change_endpoint(self):
        for identifier in ['../other','x?key=secret','x/y','']:
            with self.assertRaises(GooglePlacesError):
                await GooglePlacesClient(api_key='secret').details(identifier)
