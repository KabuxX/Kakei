"""Read-only web discovery followed by permanent, verified address geocoding."""
import asyncio,copy,json,time,uuid
from agent.limits import SEARCH_SECONDS,FINAL_REPLY_RESERVE,STAGE_LIMITS,PIPELINE_VERSION
from agent.place_matching import compact,coordinates_valid,locality_matches,distance
from agent.place_http import PlaceProviderError
from db.store import TrajectoryConflict
from services.validation import ValidationError
from services.merchant_address import addresses_match

class SearchLimit(Exception):pass

class SearchBudget:
    def __init__(self,turn_deadline,*,clock=time.monotonic):
        self.turn_deadline,self.clock=turn_deadline,clock;self.deadline=None
        self.counts=dict.fromkeys(STAGE_LIMITS,0);self.stopped={};self.tasks={};self.lock=asyncio.Lock();self.geo_slots=asyncio.Semaphore(2)
    async def run(self,stage,key,call):
        provider='mapbox' if stage=='geocode' else 'openai'
        async with self.lock:
            now=self.clock()
            if self.deadline is None:self.deadline=min(now+SEARCH_SECONDS,self.turn_deadline-FINAL_REPLY_RESERVE)
            if provider in self.stopped:raise PlaceProviderError(self.stopped[provider],stop_turn=True)
            if now>=self.deadline:raise SearchLimit('time_limit')
            identity=(stage,key);limit,seconds=STAGE_LIMITS[stage]
            if identity not in self.tasks:
                if self.counts[stage]>=limit:raise SearchLimit('request_limit')
                self.counts[stage]+=1
                async def invoke():
                    acquired=False
                    try:
                        async with asyncio.timeout(max(.001,self.deadline-self.clock())):
                            if stage=='geocode':await self.geo_slots.acquire();acquired=True
                            if provider in self.stopped:raise PlaceProviderError(self.stopped[provider],stop_turn=True)
                            remaining=self.deadline-self.clock()
                            if remaining<=0:raise SearchLimit('time_limit')
                            timeout=min(seconds,remaining)
                            async with asyncio.timeout(timeout):return await call(timeout)
                    except TimeoutError:raise PlaceProviderError('timeout') from None
                    except PlaceProviderError as e:
                        if e.stop_turn:self.stopped[provider]=e.code
                        raise
                    finally:
                        if acquired:self.geo_slots.release()
                self.tasks[identity]=asyncio.create_task(invoke())
            task=self.tasks[identity]
        return copy.deepcopy(await asyncio.shield(task))
    async def close(self):
        tasks=list(self.tasks.values())
        for task in tasks:
            if not task.done():task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)

def conditions(request):
    return {'address_format':'original',**{k:v for k,v in request.items() if k not in ('place_id','reuse_search_id','evidence','refresh')}}

def store_reasons(place,request,region):
    reasons=[];name=compact(place.get('name'));brand=compact(request.get('brand') or request['query'])
    if brand not in name:reasons.append('name_mismatch')
    branch=compact(request.get('branch'))
    if branch and branch not in name:reasons.append('branch_unconfirmed')
    if request.get('address') and not addresses_match(request['address'],place.get('address')):reasons.append('address_mismatch')
    if not locality_matches(request.get('locality'),place):reasons.append('locality_unconfirmed')
    if request.get('country_code') and place.get('country_code')!=request['country_code']:reasons.append('country_unconfirmed')
    if region and region.get('coordinates') and coordinates_valid(place.get('coordinates')) and distance(place['coordinates'],region['coordinates'])>1000:reasons.append('outside_region')
    return reasons

def unique_stores(rows):
    merged={}
    for row in rows:
        key=(compact(row['name']),compact(row['address']))
        if key not in merged:merged[key]=copy.deepcopy(row);continue
        current=merged[key];urls={s['url'] for s in current.get('sources',[])}
        for s in row.get('sources',[]):
            if s['url'] not in urls and len(current['sources'])<3:current['sources'].append(s);urls.add(s['url'])
        current['unresolved']=list(dict.fromkeys(current.get('unresolved',[])+row.get('unresolved',[])))
    return list(merged.values())

class PlaceSearchService:
    def __init__(self,web,geocoder,searches,resolver,context,budget):
        self.web,self.geocoder,self.searches,self.resolver,self.context,self.budget=web,geocoder,searches,resolver,context,budget
    async def search(self,request):
        resolved=self.resolver.resolve(request);request=resolved['request']
        refresh=request.get('refresh',False);reuse=request.get('reuse_search_id')
        if type(refresh)!=bool or (refresh and reuse):raise ValidationError('refresh','再検索と履歴再利用を同時に指定できません。')
        sid=self.searches.start(self.context,request)
        out={'pipelineVersion':PIPELINE_VERSION,'searchId':sid,'placeId':request['place_id'],'query':request['query'],'candidates':[],'unlocatedCandidates':[],'sources':[],'status':'empty','error':None,'unresolved':[],'truncated':False,'grounding':copy.deepcopy(resolved['region'])}
        source_ids={};attempts=[]
        def sources_for(rows):
            for row in rows:
                row['id']=str(uuid.uuid4())
                refs={}
                for source in row.get('sources',[]):
                    source['id']=source_ids.setdefault(source['url'],sid+':'+str(len(source_ids)+1))
                    refs.setdefault(source['url'],source)
                if 'sources' in row:row['sources']=list(refs.values())
            return rows
        def finish(status):
            out['status']=status
            all_sources={}
            for c in out['candidates']+out['unlocatedCandidates']:
                c['searchId']=sid
                for s in c.get('sources',[]):all_sources[s['id']]=s
            out['sources']=list(all_sources.values())
            self.searches.finish(self.context,sid,out)
            return self.searches.get(self.context['thread_id'],sid)['result']
        if resolved['clarification']:
            out['unresolved']=[resolved['clarification']['message']];return finish('needs_clarification')
        if reuse:
            old=self.searches.get(self.context['thread_id'],reuse)
            if old['status'] in ('running','cancelled') or not old['result'] or conditions(old['input'])!=conditions(request):raise ValidationError('reuse_search_id','同じ店舗・地域の終了した検索だけ再利用できます。')
            if old['result'].get('pipelineVersion')!=PIPELINE_VERSION or old['result'].get('grounding')!=resolved['region']:
                out['unresolved']=['検索方式または地域の根拠が変わりました。再検索してください。'];return finish('needs_clarification')
            prior=copy.deepcopy(old['result']);out.update(prior);out.update(searchId=sid,placeId=request['place_id'],reusedFrom={'searchId':reuse,'createdAt':old['createdAt']})
            sources_for(out['candidates']);sources_for(out.get('unlocatedCandidates',[]));return finish(prior['status'])
        if not refresh:
            for p in resolved['saved_places']:
                if coordinates_valid(p.get('coordinates')) and not store_reasons(p,request,resolved['region']):out['candidates'].append(p)
            if out['candidates']:
                out['candidates']=sources_for(out['candidates'][:5]);return finish('found')
        def start(stage,params):
            a={'id':str(uuid.uuid4()),'stage':stage,'params':params,'startedAt':time.time(),'status':'running'};attempts.append(a);self.searches.record_attempt(self.context,sid,a);return a
        def record(a,**values):a.update(values);self.searches.record_attempt(self.context,sid,a)
        key=json.dumps({k:v for k,v in conditions(request).items() if k!='address_format'},ensure_ascii=False,sort_keys=True)
        children=[]
        try:
            a=start('web',conditions(request))
            report=await self.budget.run('web',key,lambda t:self.web.research(request,timeout=t))
            record(a,status='complete',result=report,finishedAt=time.time())
            a=start('extract',{'webAttemptId':a['id']})
            rows=await self.budget.run('extract',key,lambda t:self.web.extract(report,timeout=t))
            rows=sources_for(unique_stores(rows))[:5]
            record(a,status='complete',candidates=rows,finishedAt=time.time())
            if not rows:
                out['unresolved']=['住所と引用元を確認できません。店舗の地域や住所を補足してください。'];return finish('needs_region' if not request.get('locality') and not request.get('landmark') else 'empty')
            a=start('geocode',{'addresses':[p['address'] for p in rows]});a['items']=[]
            async def locate(p):
                item={'id':p['id'],'address':p['address'],'status':'running'};a['items'].append(item);record(a)
                reasons=list(p.get('unresolved',[]))+store_reasons(p,request,None)
                try:
                    if reasons:result={'candidates':[],'unresolved':reasons}
                    else:
                        p={**p,'address_format':request.get('address_format','original')}
                        geo_key=json.dumps({k:p[k] for k in ('address','country_code','locality','address_format')},ensure_ascii=False,sort_keys=True)
                        result=await self.budget.run('geocode',geo_key,lambda t:self.geocoder.geocode(p,timeout=t))
                    if result['candidates']:
                        c=result['candidates'][0];reasons=store_reasons({**p,**c},request,resolved['region'])
                        if not reasons:
                            out['candidates'].append({'id':p['id'],'name':p['name'],'address':p['address'],**c,'sources':p['sources'],'sourceUrl':p['sources'][0]['url'],'attribution':'© Mapbox','matchReasons':(['user_confirmation_required'] if c['geocoding'].get('verification')=='needs_confirmation' else ['address_verified'])+(['interpolated'] if c['geocoding']['accuracy']=='interpolated' else [])})
                    else:reasons=result['unresolved']
                    item.update(status='complete',result=result)
                except (PlaceProviderError,SearchLimit) as e:
                    reasons=[e.code if isinstance(e,PlaceProviderError) else str(e)];item.update(status='failed',errorCode=reasons[0])
                except asyncio.CancelledError:
                    item.update(status='cancelled',finishedAt=time.time());record(a);raise
                if reasons:out['unlocatedCandidates'].append({k:p[k] for k in ('id','name','address','sources')}|{'unresolved':reasons})
                item['finishedAt']=time.time();record(a)
            children=[asyncio.create_task(locate(p)) for p in rows]
            await asyncio.gather(*children)
            order={p['id']:i for i,p in enumerate(rows)}
            for k in ('candidates','unlocatedCandidates'):out[k].sort(key=lambda p:order[p['id']])
            record(a,status='complete',finishedAt=time.time())
            if out['unlocatedCandidates']:
                out['error']='一部の店舗の位置を確認できませんでした。';return finish('partial')
            return finish('found' if out['candidates'] else 'empty')
        except (PlaceProviderError,SearchLimit) as e:
            code=e.code if isinstance(e,PlaceProviderError) else str(e)
            record(a,status='failed',errorCode=code,finishedAt=time.time());out['error']='地点検索を完了できませんでした（'+code+'）。'
            return finish('partial' if isinstance(e,SearchLimit) else 'error')
        except asyncio.CancelledError:
            for task in children:task.cancel()
            await asyncio.gather(*children,return_exceptions=True);await self.budget.close()
            try:
                for a in attempts:
                    if a['status']=='running':record(a,status='cancelled',finishedAt=time.time())
                finish('cancelled')
            except TrajectoryConflict:pass
            raise
