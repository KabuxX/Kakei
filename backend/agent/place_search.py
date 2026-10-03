"""Bounded search stages with durable evidence and shared request budgets."""
import asyncio
import copy
import json
import time
import uuid
from agent.place_matching import match_candidates, resolve_region, short_query
from agent.places import PlaceProviderError
from db.store import TrajectoryConflict
from services.validation import ValidationError


class SearchLimit(Exception): pass


class SearchBudget:
    def __init__(self,turn_deadline,*,clock=time.monotonic):
        self.turn_deadline=turn_deadline;self.clock=clock;self.deadline=None
        self.count=0;self.stopped=None;self.tasks={};self.lock=asyncio.Lock()

    async def run(self,key,call):
        async with self.lock:
            now=self.clock()
            if self.deadline is None: self.deadline=min(now+25,self.turn_deadline-5)
            if self.stopped: raise PlaceProviderError(self.stopped,stop_turn=True)
            if now>=self.deadline: raise SearchLimit('time_limit')
            if key not in self.tasks:
                if self.count>=8: raise SearchLimit('request_limit')
                self.count+=1
                timeout=min(5,self.deadline-now)
                async def invoke():
                    try:
                        async with asyncio.timeout(timeout): return await call(timeout)
                    except TimeoutError: raise PlaceProviderError('timeout') from None
                    except PlaceProviderError as e:
                        if e.stop_turn: self.stopped=e.code
                        raise
                self.tasks[key]=asyncio.create_task(invoke())
            task=self.tasks[key]
        return copy.deepcopy(await asyncio.shield(task))

    async def close(self):
        tasks=list(self.tasks.values())
        for task in tasks:
            if not task.done(): task.cancel()
        if tasks: await asyncio.gather(*tasks,return_exceptions=True)


class PlaceSearchService:
    def __init__(self,provider,searches,resolver,context,budget):
        self.provider,self.searches,self.resolver,self.context,self.budget=provider,searches,resolver,context,budget

    async def search(self,request):
        resolved=self.resolver.resolve(request);request=resolved['request']
        reuse=request.get('reuse_search_id')
        if reuse:
            old=self.searches.get(self.context['thread_id'],reuse)
            def conditions(r): return {k:v for k,v in r.items() if k not in ('place_id','reuse_search_id','evidence')}
            if old['status'] in ('running','cancelled') or not old['result'] or conditions(old['input'])!=conditions(request):
                raise ValidationError('reuse_search_id','同じ店舗・地域の終了した検索だけを再利用できます。')
        sid=self.searches.start(self.context,request)
        out={'searchId':sid,'placeId':request['place_id'],'query':request['query'],'candidates':[], 'status':'empty','error':None,'unresolved':[],'truncated':False}
        def finish(status=None):
            if status: out['status']=status
            for c in out['candidates']: c['searchId']=sid
            self.searches.finish(self.context,sid,out)
            # Use the persisted bounded version for tools and approval snapshots.
            return self.searches.get(self.context['thread_id'],sid)['result']
        if reuse:
            out.update(copy.deepcopy(old['result']));out.update(searchId=sid,placeId=request['place_id'],reusedFrom={'searchId':reuse,'createdAt':old['createdAt']})
            for c in out['candidates']: c['id']=str(uuid.uuid4())
            return finish()
        if resolved['clarification']:
            out['unresolved']=[resolved['clarification']['message']]
            return finish(resolved['clarification']['status'])
        region=resolved['region']; pool=resolved['saved_places'];attempts=[]; failures=[]; successes=0
        active=None
        async def run(stage,params):
            nonlocal active,successes
            if len(attempts)>=4: raise SearchLimit('search_limit')
            active={'id':str(uuid.uuid4()),'stage':stage,'params':params,'startedAt':time.time(),'status':'running','candidates':[],'excluded':[],'truncated':False}
            attempts.append(active);self.searches.record_attempt(self.context,sid,active)
            async def invoke(timeout):
                if stage=='nearby': return await self.provider.nearby(params['query'],category=params['category'],region=params['region'],timeout=timeout)
                return await self.provider.geocode(params['query'],country_code=params.get('country_code'),region=params.get('region'),timeout=timeout)
            key=json.dumps({'operation':'nearby' if stage=='nearby' else 'geocode',**params},ensure_ascii=False,sort_keys=True)
            try:
                rows=await self.budget.run(key,invoke)
                for row in rows: row['id']=str(uuid.uuid4())
                successes+=1;active.update(status='complete',candidates=rows,finishedAt=time.time())
                if stage!='region': active['excluded']=match_candidates(rows,request,region)['excluded']
                self.searches.record_attempt(self.context,sid,active)
                return rows
            except (PlaceProviderError,SearchLimit) as e:
                code=e.code if isinstance(e,PlaceProviderError) else str(e)
                failures.append(code);active.update(status='failed',errorCode=code,finishedAt=time.time())
                self.searches.record_attempt(self.context,sid,active)
                if isinstance(e,SearchLimit) or getattr(e,'stop_turn',False): raise
                return []
        def match():
            found=match_candidates(pool,request,region)
            out['candidates']=found['candidates'];out['truncated']=found.get('truncated',False)
            return found['exact_match']
        try:
            exact=match()
            if not exact:
                pool+=await run('formal',{'query':request['query'],'country_code':request.get('country_code'),'region':region})
                exact=match()
            if not exact and not region:
                anchor=request.get('landmark') or request.get('locality')
                if not anchor:
                    out['candidates']=[];out['unresolved']=['店舗のある市区町村や駅名を教えてください。']
                    return finish('needs_region' if not failures else 'error')
                rows=await run('region',{'query':anchor,'country_code':request.get('country_code')})
                resolved_region=resolve_region(rows,request);region=resolved_region['region']
                if not region:
                    out['candidates']=[];out['unresolved']=[resolved_region['clarification']['message']]
                    if failures:
                        out['error']='地点検索の一部に失敗しました。';return finish('partial' if successes else 'error')
                    return finish(resolved_region['clarification']['status'])
                exact=match()
            if not exact:
                pool+=await run('short',{'query':short_query(request,region),'country_code':request.get('country_code'),'region':region})
                exact=match()
            if not exact:
                if resolved['category']:
                    pool+=await run('nearby',{'query':request.get('brand') or request['query'],'category':resolved['category'],'region':region})
                    match()
                else:
                    failures.append('category_unknown');out['unresolved'].append('業種が不明なため周辺施設検索を省略しました。')
        except (PlaceProviderError,SearchLimit) as e:
            if not failures: failures.append(e.code if isinstance(e,PlaceProviderError) else str(e))
            match()
        except asyncio.CancelledError:
            await self.budget.close()
            try:
                if active and active['status']=='running':
                    active.update(status='cancelled',finishedAt=time.time());self.searches.record_attempt(self.context,sid,active)
                finish('cancelled')
            except TrajectoryConflict: pass
            raise
        if failures:
            out['error']='検索の一部を完了できませんでした（'+', '.join(dict.fromkeys(failures))+'）。'
            return finish('partial' if successes or out['candidates'] or any('limit' in f for f in failures) else 'error')
        return finish('found' if out['candidates'] else 'empty')
