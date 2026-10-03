import asyncio, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpcore
from agent.public_pages import PublicPageClient
from agent.place_http import PlaceProviderError

class FakeBudget:
    def __init__(self):self.calls=[]
    async def run(self,stage,key,call):
        self.calls.append((stage,key));return await call(5)

class Stream(httpcore.AsyncNetworkStream):
    def __init__(self,owner):self.owner=owner;self.request=b'';self.buffer=b'';self.closed=False
    async def write(self,buffer,timeout=None):
        self.request+=buffer
        if b'\r\n\r\n' in self.request:
            head=self.request.decode('ascii');self.owner.requests.append(head)
            path=head.split(' ')[1]
            status,headers,body=self.owner.routes.get(path,(200,{},b'hello'))
            headers={'Content-Type':'text/html','Content-Length':str(len(body)),**headers}
            self.buffer=(f'HTTP/1.1 {status} status\r\n'+''.join(f'{k}: {v}\r\n' for k,v in headers.items())+'\r\n').encode()+body
    async def read(self,max_bytes,timeout=None):
        if self.owner.slow:await self.owner.release.wait()
        data=self.buffer[:max_bytes];self.buffer=self.buffer[max_bytes:];return data
    async def aclose(self):self.closed=True
    async def start_tls(self,ssl_context,server_hostname=None,timeout=None):
        self.owner.sni.append(server_hostname);return self

class Backend(httpcore.AsyncNetworkBackend):
    def __init__(self,routes=None):self.routes=routes or {};self.connections=[];self.requests=[];self.sni=[];self.streams=[];self.slow=False;self.release=asyncio.Event()
    async def connect_tcp(self,host,port,**kwargs):
        self.connections.append((host,port));stream=Stream(self);self.streams.append(stream);return stream
    async def sleep(self,seconds):await asyncio.sleep(seconds)

class PublicPageTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_redirect_keeps_bounded_request_history(self):
        backend=Backend({'/shop':(302,{'Location':'/two'},b''),'/two':(200,{'Content-Type':'image/png'},b'x')})
        with self.assertRaises(PlaceProviderError) as got:await self.fetch(backend)
        trace=got.exception.page_requests
        self.assertEqual([r['url'] for r in trace],['https://example.com/shop','https://example.com/two'])
        self.assertEqual(trace[0]['result'],'redirect');self.assertEqual(trace[1]['result'],'unsupported_content')
        self.assertNotIn('body',trace[1])

    async def fetch(self,backend,url='https://example.com/shop',ips=None,timeout=5):
        async def resolve(host):return ips or ['93.184.216.34']
        budget=FakeBudget()
        async with PublicPageClient(resolver=resolve,network_backend=backend) as pages:
            result=await pages.fetch(url,allowed_urls={url},budget=budget,timeout=timeout)
        return result,budget

    async def test_private_dns_is_rejected_before_connect(self):
        for ips in (['127.0.0.1'],['::1'],['93.184.216.34','10.0.0.1'],['169.254.169.254'],['::ffff:127.0.0.1']):
            backend=Backend()
            with self.subTest(ips=ips),self.assertRaises(PlaceProviderError) as got:await self.fetch(backend,ips=ips)
            self.assertEqual(got.exception.code,'unsafe_address');self.assertEqual(backend.connections,[])

    async def test_connection_is_pinned_and_credentials_are_not_sent(self):
        calls=[]
        async def rebinding(host):
            calls.append(host);return ['93.184.216.34'] if len(calls)==1 else ['127.0.0.1']
        backend=Backend()
        async with PublicPageClient(resolver=rebinding,network_backend=backend) as pages:
            page=await pages.fetch('https://example.com/shop',allowed_urls={'https://example.com/shop'},budget=FakeBudget(),timeout=5)
        self.assertEqual(page['body'],b'hello');self.assertEqual(backend.connections,[('93.184.216.34',443)])
        self.assertEqual(backend.sni,['example.com']);self.assertEqual(calls,['example.com'])
        self.assertIn('Host: example.com',backend.requests[0]);self.assertNotIn('Authorization:',backend.requests[0]);self.assertNotIn('Cookie:',backend.requests[0])

    async def test_redirects_are_revalidated_and_counted(self):
        backend=Backend({'/shop':(302,{'Location':'/two'},b''),'/two':(302,{'Location':'/three'},b''),'/three':(302,{'Location':'/four'},b''),'/four':(200,{},b'final')})
        page,budget=await self.fetch(backend)
        self.assertEqual(page['final_url'],'https://example.com/four');self.assertEqual(len(page['redirects']),3);self.assertEqual(len(budget.calls),4)
        backend.routes['/four']=(302,{'Location':'/five'},b'')
        with self.assertRaises(PlaceProviderError) as got:await self.fetch(backend)
        self.assertEqual(got.exception.code,'redirect_limit')
        backend=Backend({'/shop':(302,{'Location':'https://127.0.0.1/private'},b'')})
        with self.assertRaises(PlaceProviderError):await self.fetch(backend)
        self.assertEqual(len(backend.connections),1)

    async def test_redirect_dns_cannot_enter_private_network(self):
        backend=Backend({'/shop':(302,{'Location':'https://other.example/path'},b'')})
        async def resolve(host):return ['93.184.216.34'] if host=='example.com' else ['10.1.2.3']
        async with PublicPageClient(resolver=resolve,network_backend=backend) as pages:
            with self.assertRaises(PlaceProviderError) as got:await pages.fetch('https://example.com/shop',allowed_urls={'https://example.com/shop'},budget=FakeBudget(),timeout=5)
        self.assertEqual(got.exception.code,'unsafe_address');self.assertEqual(len(backend.connections),1)

    async def test_source_binding_and_geographic_endpoints(self):
        async def resolve(host):return ['93.184.216.34']
        backend=Backend()
        async with PublicPageClient(resolver=resolve,network_backend=backend) as pages:
            for url in ('https://unknown.example/shop','https://api.mapbox.com/search/geocode/v6/forward','https://api.geoapify.com/v1/geocode/search','https://maps.googleapis.com/maps/api/geocode/json','https://www.google.com/maps/rpc/search','https://user:password@example.com/shop','http://example.com/shop'):
                with self.subTest(url=url),self.assertRaises(PlaceProviderError):await pages.fetch(url,allowed_urls={'https://example.com/shop',url} if 'unknown' not in url else {'https://example.com/shop'},budget=FakeBudget(),timeout=5)
        self.assertEqual(backend.connections,[])

    async def test_size_and_content_limits_close_streams(self):
        backend=Backend({'/shop':(200,{},b'x'*524288)})
        page,_=await self.fetch(backend);self.assertEqual(len(page['body']),524288)
        for headers,body,code in (({},b'x'*524289,'page_too_large'),({'Content-Type':'image/png'},b'x','unsupported_content')):
            backend=Backend({'/shop':(200,headers,body)})
            with self.subTest(code=code),self.assertRaises(PlaceProviderError) as got:await self.fetch(backend)
            self.assertEqual(got.exception.code,code);self.assertTrue(all(s.closed for s in backend.streams))

    async def test_timeout_and_cancellation_close_resources(self):
        backend=Backend();backend.slow=True
        with self.assertRaises(PlaceProviderError) as got:await self.fetch(backend,timeout=.01)
        self.assertEqual(got.exception.code,'timeout')
        backend=Backend();backend.slow=True
        task=asyncio.create_task(self.fetch(backend))
        while not backend.streams:await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(all(s.closed for s in backend.streams))
