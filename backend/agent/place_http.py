"""Bounded JSON requests to the OpenAI provider only."""
import asyncio,json,os
import httpx

class PlaceProviderError(Exception):
    def __init__(self,code,*,stop_turn=False):
        self.code,self.stop_turn=code,stop_turn
        super().__init__(code)

async def request_json(client,provider,path,*,params=None,body=None,timeout):
    endpoints={'openai':('https://api.openai.com','/v1/responses','OPENAI_API_KEY')}
    if provider not in endpoints or path!=endpoints[provider][1]:raise PlaceProviderError('invalid_endpoint')
    host,_,env=endpoints[provider];key=os.environ.get(env,'').strip()
    if not key:raise PlaceProviderError('unavailable',stop_turn=True)
    headers={'Authorization':'Bearer '+key}
    params=params or {}
    try:
        async with asyncio.timeout(timeout):
            async with client.stream('POST' if body is not None else 'GET',host+path,params=params,json=body,headers=headers,timeout=timeout,follow_redirects=False) as response:
                if response.status_code in (401,403):raise PlaceProviderError('auth',stop_turn=True)
                if response.status_code==429:raise PlaceProviderError('rate_limited',stop_turn=True)
                response.raise_for_status();data=bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data)>512*1024:raise PlaceProviderError('invalid_response')
        value=json.loads(data,parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite')))
        if not isinstance(value,dict):raise ValueError()
        return value
    except (TimeoutError,httpx.TimeoutException):raise PlaceProviderError('timeout') from None
    except httpx.HTTPError:raise PlaceProviderError('network') from None
    except (ValueError,TypeError):raise PlaceProviderError('invalid_response') from None
