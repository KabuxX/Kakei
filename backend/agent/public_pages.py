"""Public, source-bound HTTPS reads with DNS-pinned connections and no credentials."""
import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlsplit, urljoin
import httpcore
import httpx
from agent.place_http import PlaceProviderError
from agent.limits import SearchLimit
from services.place_evidence import safe_source_url
from services.validation import ValidationError

MAX_BODY=512*1024
CONTENT_TYPES={'text/html','application/xhtml+xml','text/plain','application/json','application/ld+json','application/geo+json'}

def public_ips(values):
    if not isinstance(values,list) or not values:raise PlaceProviderError('unsafe_address')
    try:
        if any(not ipaddress.ip_address(value).is_global for value in values):raise ValueError()
    except (ValueError,TypeError):raise PlaceProviderError('unsafe_address') from None
    return list(dict.fromkeys(values))

async def resolve_public_addresses(host: str) -> list[str]:
    records=await asyncio.get_running_loop().getaddrinfo(host,443,type=socket.SOCK_STREAM)
    return public_ips([record[4][0] for record in records])

def page_url(value):
    try:safe_source_url(value)
    except ValidationError:raise PlaceProviderError('unsafe_url') from None
    url=urlsplit(value);host=url.hostname.lower().rstrip('.');path=url.path.casefold()
    if host in {'api.mapbox.com','api.geoapify.com','maps.googleapis.com','maps-api.apple.com','api.openai.com'} or any(part in path for part in ('/geocode','/geocoding','/maps/rpc','/maps/api','/maps/preview/rpc','/maps/preview/place','/maps/preview/search','/batchexecute')):
        raise PlaceProviderError('unsupported_endpoint')
    return str(httpx.URL(value).copy_with(fragment=None))

class PinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self,resolver,backend):self.resolver,self.backend=resolver,backend
    async def connect_tcp(self,host,port,**kwargs):
        ips=public_ips(await self.resolver(host))
        return await self.backend.connect_tcp(ips[0],port,**kwargs)
    async def connect_unix_socket(self,*args,**kwargs):raise PlaceProviderError('unsafe_address')
    async def sleep(self,seconds):await self.backend.sleep(seconds)

class PublicPageClient:
    def __init__(self,*,resolver=None,network_backend=None):
        pinned=PinnedBackend(resolver or resolve_public_addresses,network_backend or httpcore.AnyIOBackend())
        self.pool=httpcore.AsyncConnectionPool(network_backend=pinned,max_connections=3,max_keepalive_connections=0,retries=0)
    async def __aenter__(self):return self
    async def __aexit__(self,*args):await self.pool.aclose()

    async def _get(self,url,timeout):
        try:
            async with asyncio.timeout(timeout):
                async with self.pool.stream('GET',url,headers=[(b'User-Agent',b'Kakei-PlaceResearch/1.0'),(b'Accept',b'text/html,application/json,text/plain')],extensions={'timeout':dict.fromkeys(('connect','read','write','pool'),timeout)}) as response:
                    headers={k.decode('ascii').casefold():v.decode('latin1') for k,v in response.headers}
                    # Redirect bodies are not evidence; do not download them.
                    if response.status in (301,302,303,307,308):return {'status':response.status,'headers':headers,'body':b''}
                    if response.status!=200:raise PlaceProviderError('network')
                    content_type=headers.get('content-type','').split(';')[0].strip().lower()
                    if content_type not in CONTENT_TYPES:raise PlaceProviderError('unsupported_content')
                    if headers.get('content-encoding','identity').lower() not in ('','identity'):raise PlaceProviderError('unsupported_content')
                    if headers.get('content-length','').isdigit() and int(headers['content-length'])>MAX_BODY:raise PlaceProviderError('page_too_large')
                    body=bytearray()
                    async for chunk in response.aiter_stream():
                        body.extend(chunk)
                        if len(body)>MAX_BODY:raise PlaceProviderError('page_too_large')
                    return {'status':200,'headers':headers,'body':bytes(body)}
        except (TimeoutError,httpcore.TimeoutException):raise PlaceProviderError('timeout') from None
        except (httpcore.NetworkError,httpcore.ProtocolError,OSError):raise PlaceProviderError('network') from None

    async def fetch(self,url: str,*,allowed_urls: set[str],budget,timeout: float) -> dict:
        current=page_url(url)
        allowed=set()
        for source in allowed_urls:
            try:allowed.add(page_url(source))
            except PlaceProviderError:pass
        if current not in allowed:raise PlaceProviderError('unsafe_url')
        redirects=[];requests=[]
        try:
            for hop in range(4):
                entry={'url':current,'startedAt':time.time(),'result':'running'};requests.append(entry)
                result=await budget.run('page',current,lambda t:self._get(current,min(timeout,t)))
                entry.update(httpStatus=result['status'],finishedAt=time.time())
                if result['status']==200:
                    entry['result']='read'
                    return {'url':url,'final_url':current,'redirects':redirects,'requests':requests,'content_type':result['headers']['content-type'].split(';')[0].strip().lower(),'body':result['body'],'retrieved_at':time.time()}
                entry['result']='redirect'
                if hop==3:raise PlaceProviderError('redirect_limit')
                location=result['headers'].get('location')
                if not location:raise PlaceProviderError('network')
                current=page_url(urljoin(current,location));entry['redirectTo']=current;redirects.append(current)
        except (PlaceProviderError,SearchLimit) as error:
            requests[-1].update(result=error.code if isinstance(error,PlaceProviderError) else str(error),finishedAt=time.time())
            error.page_requests=requests
            raise
        raise PlaceProviderError('redirect_limit')
