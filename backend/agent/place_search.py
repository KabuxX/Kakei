"""Bounded Web discovery, coordinate verification and grounded estimation."""
import asyncio,copy,json,time,uuid
from agent.limits import SEARCH_SECONDS,FINAL_REPLY_RESERVE,STAGE_LIMITS,PIPELINE_VERSION,SearchLimit
from agent.place_matching import compact,merchant_key,coordinates_valid,locality_matches,distance
from agent.place_http import PlaceProviderError
from db.store import TrajectoryConflict
from services.validation import ValidationError
from services.merchant_address import addresses_match
from services.coordinate_evidence import rebind_candidate_sources,validate_coordinate_evidence
from agent.coordinate_estimation import estimate_coordinates
from agent.geolonia_addresses import eligible_address
from agent.geolonia_candidates import candidate_from_match

class SearchBudget:
    def __init__(self,turn_deadline,*,clock=time.monotonic):
        self.turn_deadline,self.clock=turn_deadline,clock;self.deadline=None
        self.counts=dict.fromkeys(STAGE_LIMITS,0);self.stopped={};self.tasks={};self.lock=asyncio.Lock();self.page_slots=asyncio.Semaphore(3)
    def geolonia_time_remaining(self):
        now=self.clock()
        if self.deadline is None:self.deadline=min(now+SEARCH_SECONDS,self.turn_deadline-FINAL_REPLY_RESERVE)
        return max(0,self.deadline-now-35)
    async def run(self,stage,key,call):
        provider='pages' if stage=='page' else 'openai'
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
                            if stage=='page':await self.page_slots.acquire();acquired=True
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
                        if acquired:self.page_slots.release()
                self.tasks[identity]=asyncio.create_task(invoke())
            task=self.tasks[identity]
        return copy.deepcopy(await asyncio.shield(task))
    async def verify(self,key,call):
        identity=('verify',key)
        async with self.lock:
            if identity not in self.tasks:
                async def invoke():
                    remaining=(self.deadline or min(self.clock()+SEARCH_SECONDS,self.turn_deadline-FINAL_REPLY_RESERVE))-self.clock()
                    if remaining<=0:raise SearchLimit('time_limit')
                    # Each external page hop has its own deadline in run(). An
                    # enclosing timeout would discard already verified evidence.
                    return await call(5)
                self.tasks[identity]=asyncio.create_task(invoke())
            task=self.tasks[identity]
        return copy.deepcopy(await asyncio.shield(task))
    async def close(self):
        tasks=list(self.tasks.values())
        for task in tasks:
            if not task.done():task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)

def conditions(request):
    return {k:v for k,v in request.items() if k not in ('place_id','reuse_search_id','evidence','refresh','address_format')}

def abbreviated_branch(place,request):
    branch=merchant_key(request.get('branch'));actual=merchant_key(place.get('branch'))
    stem=branch.removesuffix('店')
    return bool(branch and branch.endswith('店') and len(stem)>=2 and actual.startswith(stem) and actual.endswith('店') and actual in merchant_key(place.get('name')) and branch!=actual and request.get('address') and addresses_match(request['address'],place.get('address')))

def coordinate_warnings(place,request):
    # Only these non-identity warnings can accompany independently verified pins.
    warnings=[w['note'] for w in place.get('warnings',[]) if w['kind'] in ('historical_location_unconfirmed','building_relation_unconfirmed') or (w['kind']=='branch_label_difference' and abbreviated_branch(place,request))]
    if abbreviated_branch(place,request):warnings.append('入力の支店名は掲載名と異なります。住所が一致する店舗の候補として確認してください。')
    return warnings

def annotate_candidate(candidate,place,request):
    evidence=candidate.get('coordinateEvidence')
    warnings=coordinate_warnings(place,request)
    if evidence and warnings:
        evidence['note']=(evidence['note']+' '+' '.join(warnings))[:500]
        evidence['verification']='needs_confirmation'
    if abbreviated_branch(place,request):candidate['matchReasons']=list(dict.fromkeys(candidate.get('matchReasons',[])+['branch_unconfirmed']))
    return candidate

def store_reasons(place,request,region):
    reasons=[];name=merchant_key(place.get('name'));brand=merchant_key(request.get('brand') or request['query'])
    if brand not in name:reasons.append('name_mismatch')
    branch=merchant_key(request.get('branch'))
    if branch and branch not in name and not abbreviated_branch(place,request):reasons.append('branch_unconfirmed')
    if request.get('address') and not addresses_match(request['address'],place.get('address')):reasons.append('address_mismatch')
    if not locality_matches(request.get('locality'),place):reasons.append('locality_unconfirmed')
    if request.get('country_code') and place.get('country_code')!=request['country_code']:reasons.append('country_unconfirmed')
    if region and region.get('coordinates') and coordinates_valid(place.get('coordinates')) and place.get('coordinateEvidence',{}).get('precision')!='area' and distance(place['coordinates'],region['coordinates'])>1000:reasons.append('outside_region')
    return reasons

def unique_stores(rows):
    merged={}
    for row in rows:
        key=(compact(row['name']),compact(row['address']))
        if key not in merged:merged[key]=copy.deepcopy(row);continue
        current=merged[key];urls={s['url']:s['id'] for s in current.get('sources',[])};mapping={}
        for s in row.get('sources',[]):
            if s['url'] not in urls and len(current['sources'])<6:current['sources'].append(copy.deepcopy(s));urls[s['url']]=s['id']
            if s['url'] in urls:mapping[s['id']]=urls[s['url']]
        for field in ('hints','verifiedHints'):
            hints=current.setdefault(field,[])
            for original in row.get(field,[]):
                hint=copy.deepcopy(original)
                if not all(i in mapping for i in hint['relationSourceIds']):continue
                hint['relationSourceIds']=list(dict.fromkeys(mapping[i] for i in hint['relationSourceIds']))
                if hint not in hints:hints.append(hint)
        for field in ('urls','discoveredUrls'):current[field]=list(dict.fromkeys(current.get(field,[])+row.get(field,[])))[:50]
        current['unresolved']=list(dict.fromkeys(current.get('unresolved',[])+row.get('unresolved',[])))
    return list(merged.values())

class PlaceSearchService:
    def __init__(self,web,verifier,searches,resolver,context,budget,*,geolonia=None):
        self.web,self.verifier,self.searches,self.resolver,self.context,self.budget=web,verifier,searches,resolver,context,budget
        self.geolonia=geolonia
    async def search(self,request):
        resolved=self.resolver.resolve(request);request=resolved['request']
        refresh=request.get('refresh',False);reuse=request.get('reuse_search_id')
        if type(refresh)!=bool or (refresh and reuse):raise ValidationError('refresh','再検索と履歴再利用を同時に指定できません。')
        sid=self.searches.start(self.context,request)
        out={'pipelineVersion':PIPELINE_VERSION,'searchId':sid,'placeId':request['place_id'],'query':request['query'],'candidates':[],'unlocatedCandidates':[],'sources':[],'status':'empty','error':None,'unresolved':[],'truncated':False,'grounding':copy.deepcopy(resolved['region'])}
        source_ids={};attempts=[]
        def sources_for(rows):
            result=[]
            for original in rows:
                mapping={source['id']:source_ids.setdefault(source['url'],sid+':'+str(len(source_ids)+1)) for source in original.get('sources',[])}
                row=rebind_candidate_sources(original,mapping);row['id']=str(uuid.uuid4())
                for hint in row.get('hints',[])+row.get('verifiedHints',[]):hint['relationSourceIds']=list(dict.fromkeys(mapping.get(i,i) for i in hint['relationSourceIds']))
                if 'coordinateEvidence' in row:validate_coordinate_evidence(row)
                result.append(row)
            return result
        def finish(status):
            out['status']=status
            all_sources={}
            for c in out['candidates']+out['unlocatedCandidates']:
                c['searchId']=sid
                if request.get('visit_date') and c.get('coordinateEvidence'):
                    evidence=c['coordinateEvidence'];warning=' 訪問日'+request['visit_date']+'当時の所在地は未確認。現在の掲載位置と異なる可能性があるため、移転履歴も確認してください。'
                    if warning not in evidence['note']:evidence['note']=evidence['note'][:500-len(warning)]+warning
                    evidence['verification']='needs_confirmation'
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
            out['candidates']=sources_for(out['candidates']);out['unlocatedCandidates']=sources_for(out.get('unlocatedCandidates',[]));return finish(prior['status'])
        if not refresh:
            for p in resolved['saved_places']:
                if coordinates_valid(p.get('coordinates')) and not store_reasons(p,request,resolved['region']):out['candidates'].append(p)
            if out['candidates']:
                out['candidates']=sources_for(out['candidates'][:5]);return finish('found')
        def start(stage,params):
            a={'id':str(uuid.uuid4()),'stage':stage,'params':params,'startedAt':time.time(),'status':'running'};attempts.append(a);self.searches.record_attempt(self.context,sid,a);return a
        def record(a,**values):a.update(values);self.searches.record_attempt(self.context,sid,a)
        key=json.dumps(conditions(request),ensure_ascii=False,sort_keys=True)
        children=[];stores=[];anchors=[];failures=[];tried=[];a=None;geo_session=None;geo_attempt=None;geo_trials=[]
        def preserve_unlocated():
            located={(merchant_key(c['name']),compact(c['address'])) for c in out['candidates']}
            out['unlocatedCandidates']=sources_for([{k:p[k] for k in ('id','name','address','sources')}|{'unresolved':p.get('unresolved') or list(dict.fromkeys(failures)) or ['position_unverified']} for p in unique_stores(stores)[:5] if (merchant_key(p['name']),compact(p['address'])) not in located])
        async def geolonia_locate(store):
            nonlocal geo_session,geo_attempt
            if self.geolonia is None:return None
            address=store.get('address') if store else request.get('address')
            reason='geolonia_address_unavailable' if not address else 'geolonia_not_japanese' if not eligible_address(address,request.get('country_code')) else 'geolonia_store_unconfirmed' if not store else None
            if geo_attempt is None:geo_attempt=start('geolonia',{'address':address})
            summary=out.setdefault('geolonia',{'status':'skipped','unresolved':[],'supplementalMatches':[]})
            if reason:
                summary['unresolved']=list(dict.fromkeys(summary['unresolved']+[reason]))
                record(geo_attempt,status='complete',trials=geo_trials,unresolved=summary['unresolved'],finishedAt=time.time());return None
            if geo_session is None:geo_session=self.geolonia.session(key,self.budget)
            # Administrative prefixes must themselves be quoted in validated evidence.
            prefixes=[e['value'] for e in request.get('evidence',[]) if e['field']=='locality']
            result=await geo_session.lookup(address,grounded_prefixes=prefixes)
            geo_trials.extend(result.get('attempts',[]))
            summary['status']=result['status'];summary['unresolved']=list(dict.fromkeys(summary['unresolved']+result.get('unresolved',[])))
            candidate=candidate_from_match(store,result)
            if result.get('match') and not candidate and len(summary['supplementalMatches'])<6:
                match=result['match'];point=match.get('point') or {}
                summary['supplementalMatches'].append({'originalAddress':address,'matchedAddress':''.join(match.get(k) or '' for k in ('pref','city','town','addr')),'level':match.get('level'),'pointLevel':point.get('level'),'fetches':result.get('proof',{}).get('fetches',[]),'reasons':result.get('unresolved') or ['geolonia_invalid_response']})
            record(geo_attempt,status='complete',trials=geo_trials,unresolved=summary['unresolved'],finishedAt=time.time())
            return candidate
        try:
            if request.get('address'):
                candidate=await geolonia_locate(resolved.get('address_store'))
                if candidate and not store_reasons(candidate,request,resolved['region']):
                    out['candidates']=sources_for([candidate]);return finish('found')
            elif self.geolonia is not None:
                await geolonia_locate(None)
            for index in range(4):
                strategy='store' if index==0 or not stores else ('maps','address','anchor')[index-1]
                prior={'stores':[{k:p[k] for k in ('name','address')} for p in stores],'hints':[h for p in stores for h in p.get('verifiedHints',[])],'tried':tried,'unresolved':failures}
                stage_key=key+':'+strategy+':'+str(index)
                tried.append(strategy);a=start('web',{'strategy':strategy,**conditions(request)})
                try:
                    report=await self.budget.run('web',stage_key,lambda t:self.web.research(request,strategy=strategy,prior=prior,timeout=t))
                    record(a,status='complete',result=report,finishedAt=time.time())
                    a=start('extract',{'webAttemptId':a['id']})
                    rows=await self.budget.run('extract',stage_key,lambda t:self.web.extract(report,timeout=t))
                    rows=unique_stores(rows)[:5];record(a,status='complete',candidates=rows,finishedAt=time.time())
                    a=start('verify',{'strategy':strategy,'stores':[p['name'] for p in rows]})
                    page_records=[]
                    async def locate(p):
                        if p.get('role')=='anchor':
                            hints=[h for store in stores for h in store.get('verifiedHints',[])]
                            if not any(compact(h['anchorName'])==compact(p['name']) and addresses_match(h['anchorAddress'],p['address']) for h in hints):return
                        else:
                            reasons=store_reasons(p,request,None)+p.get('unresolved',[])
                            if any(w['kind']=='branch_label_difference' for w in p.get('warnings',[])) and not abbreviated_branch(p,request):reasons.append('branch_unconfirmed')
                            if reasons:
                                stores.append({**p,'unresolved':reasons});return
                            candidate=await geolonia_locate(p)
                            if candidate and not store_reasons({**p,**candidate},request,resolved['region']):
                                out['candidates'].append(annotate_candidate(candidate,p,request));stores.append(p);return
                        verify_key=json.dumps({'name':p['name'],'address':p['address'],'sources':p['sources'],'hints':p.get('hints',[])},sort_keys=True,ensure_ascii=False)
                        try:
                            result=await self.budget.verify(verify_key,lambda t:self.verifier.verify(p,timeout=t))
                        except (PlaceProviderError,SearchLimit) as e:
                            failures.append(e.code if isinstance(e,PlaceProviderError) else str(e))
                            if p.get('role')!='anchor':stores.append({**p,'unresolved':[failures[-1]]})
                            return
                        failures.extend(result.get('unresolved',[]))
                        page_records.extend(result.get('pages',[]))
                        if p.get('role')=='anchor':anchors.extend(result['anchors']);return
                        stores.append({**p,'verifiedHints':result.get('verifiedHints',[])})
                        for c in result['candidates']:
                            if not store_reasons({**p,**c},request,resolved['region']):out['candidates'].append(annotate_candidate(c,p,request))
                    children=[asyncio.create_task(locate(p)) for p in rows]
                    await asyncio.gather(*children)
                    stores=unique_stores(stores)[:5]
                    record(a,status='complete',candidates=out['candidates'],pages=page_records[:80],unresolved=list(dict.fromkeys(failures)),finishedAt=time.time())
                    if anchors:
                        a=start('estimate',{'anchors':[p['name'] for p in anchors]})
                        for store in stores:
                            for c in estimate_coordinates(store,anchors):
                                if not store_reasons({**store,**c},request,resolved['region']):out['candidates'].append(annotate_candidate(c,store,request))
                        record(a,status='complete',candidates=out['candidates'],finishedAt=time.time())
                    if out['candidates']:break
                except PlaceProviderError as e:
                    failures.append(e.code);record(a,status='failed',errorCode=e.code,finishedAt=time.time())
                    if e.stop_turn:break
            a=start('compare',{});out['candidates']=sources_for(compare_candidates(out['candidates']))
            record(a,status='complete',candidates=out['candidates'],finishedAt=time.time())
            preserve_unlocated()
            out['unresolved']=list(dict.fromkeys(failures))
            if failures or out['unlocatedCandidates']:
                out['error']='一部の店舗の位置確認・探索が完了していません。';return finish('partial' if stores or out['candidates'] else 'error')
            if not stores and not out['candidates']:out['unresolved']=['住所と位置の根拠を確認できません。地域・住所を補足してください。']
            return finish('found' if out['candidates'] else 'empty')
        except (PlaceProviderError,SearchLimit) as e:
            code=e.code if isinstance(e,PlaceProviderError) else str(e)
            if a:record(a,status='failed',errorCode=code,finishedAt=time.time())
            out['candidates']=sources_for(compare_candidates(out['candidates']));out['unresolved'].append(code);out['error']='地点検索は途中で終了しました（'+code+'）。'
            failures.append(code);preserve_unlocated()
            return finish('partial')
        except asyncio.CancelledError:
            for task in children:task.cancel()
            await asyncio.gather(*children,return_exceptions=True);await self.budget.close()
            try:
                for a in attempts:
                    if a['status']=='running':record(a,status='cancelled',finishedAt=time.time())
                finish('cancelled')
            except TrajectoryConflict:pass
            raise
        finally:
            if geo_session is not None:await geo_session.close()

def compare_candidates(candidates):
    groups={}
    for candidate in candidates:
        key=(merchant_key(candidate['name']),compact(candidate['address']))
        group=groups.setdefault(key,[])
        if any(c['coordinates']==candidate['coordinates'] and c.get('coordinateEvidence',{}).get('status')==candidate.get('coordinateEvidence',{}).get('status') for c in group):continue
        group.append(copy.deepcopy(candidate))
    result=[]
    for group in list(groups.values())[:5]:
        published=[c for c in group if c.get('coordinateEvidence',{}).get('status') in ('published','address_matched')]
        if any(distance(a['coordinates'],b['coordinates'])>100 for a in published for b in published):
            for c in published:c['matchReasons']=list(dict.fromkeys(c.get('matchReasons',[])+['coordinate_conflict']))
        result.extend(group[:3])
    return result
