"""Google-only search tools. The model sees references, never Google content."""
import asyncio
from agent.google_places import GooglePlacesError
from agent.place_matching import EvidenceResolver
from db.agent_search_store import AgentSearchStore

class GooglePlaceTools:
    legacy=False
    def __init__(self,*,store,thread_id,messages,turn_context,deadline):
        from agent.google_places import GooglePlacesClient
        self.client=GooglePlacesClient()
        self.resolver=EvidenceResolver(store,AgentSearchStore(store.db_path),thread_id,messages)
        self.deadline=deadline
        self.latest=None
    async def search(self,request):
        import time
        self.resolver.resolve(request)
        query=request['query']
        address=request.get('address')
        if address:
            query+=' '+address
        try:
            candidates=await asyncio.wait_for(self.client.search_text(query),max(0.001,min(8,self.deadline-time.monotonic())))
            refs=list(dict.fromkeys(c.place_id for c in candidates))
            reason=None if refs else 'not_found'
        except GooglePlacesError as error:
            refs=[]
            reason='provider_configuration' if error.code=='configuration' else 'provider_unavailable'
        except TimeoutError:
            refs=[];reason='budget_exceeded'
        self.latest={'query':request['query'],'placeIds':refs,'reason':reason}
        return {'placeSearch':self.latest,'saved':False}
    async def close(self):
        await self.client.__aexit__(None,None,None)

def google_place_tools_factory(**kwargs):
    return GooglePlaceTools(**kwargs)
