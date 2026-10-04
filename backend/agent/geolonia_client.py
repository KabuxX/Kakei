"""Lazy, bounded Node workers; resources belong to the current Agent turn."""
import asyncio
import copy
import json
import re
import shutil
import time
import uuid
from pathlib import Path
from agent.geolonia_addresses import address_variants, match_reasons
from agent.place_matching import coordinates_valid
from services.geolonia_evidence import dataset_url
from services.place_evidence import text, timestamp
from services.validation import ValidationError

MAX_BYTES=32*1024*1024


def validate_worker_result(response):
    """Check nested JSON before matches can reach candidate or history code."""
    if set(response)!={'id','status','bytesRead','libraryVersion','match','proof'}:raise ValueError()
    match=response['match'];proof=response['proof']
    if not isinstance(match,dict) or set(match)!={'pref','city','town','addr','other','level','point','record'}:raise ValueError()
    for key in ('pref','city','town','addr','other'):
        if not isinstance(match[key],str) or len(match[key])>500:raise ValueError()
    if type(match['level']) is not int or match['level'] not in (0,1,2,3,8):raise ValueError()
    point=match['point']
    if point is not None and (not isinstance(point,dict) or set(point)!={'lng','lat','level'} or type(point['level']) is not int or point['level'] not in (1,2,3,8) or not coordinates_valid([point['lng'],point['lat']])):raise ValueError()
    record=match['record']
    if record is not None:
        if not isinstance(record,dict) or set(record)!={'kind','fields'} or record['kind'] not in ('rsdt','chiban') or not isinstance(record['fields'],dict):raise ValueError()
        fields=record['fields'];numbers=('blk_num','rsdt_num','rsdt_num2') if record['kind']=='rsdt' else ('prc_num1','prc_num2','prc_num3')
        mandatory='rsdt_num' if record['kind']=='rsdt' else 'prc_num1'
        if mandatory not in fields or set(fields)-set(numbers)-{'point'}:raise ValueError()
        for key in numbers:
            if key in fields:text(fields[key],40,key)
        if 'point' in fields and not coordinates_valid(fields['point']):raise ValueError()
    if not isinstance(proof,dict) or set(proof)!={'fetches','observation'}:raise ValueError()
    fetches=proof['fetches']
    if not isinstance(fetches,list) or not 1<=len(fetches)<=4:raise ValueError()
    ids=set()
    for fetch in fetches:
        if not isinstance(fetch,dict) or set(fetch)!={'sourceId','url','retrievedAt','range','sha256','updatedAt'}:raise ValueError()
        text(fetch['sourceId'],100,'sourceId')
        if fetch['sourceId'] in ids or not dataset_url(fetch['url']):raise ValueError()
        ids.add(fetch['sourceId']);timestamp(fetch['retrievedAt'])
        if fetch['updatedAt'] is not None:timestamp(fetch['updatedAt'])
        if not isinstance(fetch['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',fetch['sha256']):raise ValueError()
        span=fetch['range']
        if span is not None and (not isinstance(span,dict) or set(span)!={'offset','length'} or type(span['offset']) is not int or span['offset']<0 or type(span['length']) is not int or not 1<=span['length']<=8*1024*1024):raise ValueError()
    observation=proof['observation']
    if point is not None and point['level']==8:
        coords=[point['lng'],point['lat']]
        if not record or record['fields'].get('point')!=coords:raise ValueError()
        if not isinstance(observation,dict) or set(observation)!={'sourceId','kind','excerpt','coordinates'} or not isinstance(observation['sourceId'],str) or observation['sourceId'] not in ids or observation['kind']!='geolonia_address' or observation['coordinates']!=coords:raise ValueError()
        text(observation['excerpt'],2048,'excerpt')
        if json.loads(observation['excerpt'])!={'components':{k:match[k] for k in ('pref','city','town','addr')},'record':record}:raise ValueError()
    elif observation is not None:raise ValueError()


class WorkerError(Exception):
    def __init__(self,code):self.code=code


class GeoloniaClient:
    def __init__(self,*,executable=None,worker_path=None,clock=time.monotonic):
        self.executable=executable or shutil.which('node')
        self.worker_path=Path(worker_path) if worker_path else Path(__file__).resolve().parents[1]/'geolonia'/'worker.mjs'
        self.clock=clock;self.slots=asyncio.Semaphore(2);self.sessions={}

    def session(self,key,budget):
        if key not in self.sessions:self.sessions[key]=GeoloniaSession(self,budget)
        session=self.sessions[key];session.owners+=1
        return session

    async def close(self):
        await asyncio.gather(*(s.shutdown() for s in self.sessions.values()))


class GeoloniaSession:
    def __init__(self,client,budget):
        self.client,self.budget=client,budget
        self.tasks={};self.lock=asyncio.Lock();self.seen=set();self.spent=0;self.bytes=0
        self.process=None;self.stderr_task=None;self.acquired=False;self.owners=0;self.failure_code=None

    async def lookup(self,address,*,grounded_prefixes):
        key=json.dumps([address,grounded_prefixes],ensure_ascii=False)
        if key not in self.tasks:self.tasks[key]=asyncio.create_task(self._lookup(address,grounded_prefixes))
        try:return copy.deepcopy(await asyncio.shield(self.tasks[key]))
        except asyncio.CancelledError:
            if self.owners<=1:await self.shutdown()
            raise

    async def close(self):
        self.owners=max(0,self.owners-1)
        if not self.owners:await self.shutdown()

    async def shutdown(self):
        tasks=[t for t in self.tasks.values() if not t.done() and t is not asyncio.current_task()]
        for task in tasks:task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)
        await self._stop()

    async def _stderr(self):
        body=bytearray()
        while chunk:=await self.process.stderr.read(1024):
            body.extend(chunk)
            if len(body)>4096:
                if self.process.returncode is None:self.process.kill()
                break
        return bytes(body[:4096])

    async def _start(self):
        if self.process:return
        if not self.client.executable:raise WorkerError('geolonia_unavailable')
        await self.client.slots.acquire();self.acquired=True
        try:
            self.process=await asyncio.create_subprocess_exec(self.client.executable,str(self.client.worker_path),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,limit=65536)
            self.stderr_task=asyncio.create_task(self._stderr())
        except OSError:raise WorkerError('geolonia_unavailable') from None

    async def _stop(self):
        if self.process:
            if self.process.returncode is None:
                try:self.process.terminate()
                except ProcessLookupError:pass
            try:await asyncio.wait_for(self.process.wait(),1)
            except TimeoutError:
                try:self.process.kill()
                except ProcessLookupError:pass
                await self.process.wait()
            if self.stderr_task:await self.stderr_task
            self.process=None;self.stderr_task=None
        if self.acquired:self.client.slots.release();self.acquired=False

    async def _exchange(self,variant,timeout):
        await self._start()
        rid=str(uuid.uuid4())
        payload={'id':rid,'address':variant['address'],'timeoutMs':max(1,min(30000,int(timeout*1000))),'bytesRemaining':MAX_BYTES-self.bytes}
        try:
            self.process.stdin.write((json.dumps(payload,ensure_ascii=False)+'\n').encode())
            await self.process.stdin.drain();line=await self.process.stdout.readline()
            if not line:
                await self.process.wait()
                stderr=await self.stderr_task
                code='geolonia_unavailable' if b'ERR_MODULE_NOT_FOUND' in stderr or b'MODULE_NOT_FOUND' in stderr else 'geolonia_invalid_response'
                raise WorkerError(code)
            response=json.loads(line)
            if not isinstance(response,dict) or response.get('id')!=rid or response.get('status') not in ('ok','error'):
                raise ValueError()
            size=response.get('bytesRead')
            if type(size) is not int or not 0<=size<=MAX_BYTES-self.bytes:raise ValueError()
            self.bytes+=size
            if response['status']=='error':
                code=response.get('errorCode')
                allowed={'geolonia_network','geolonia_network_permanent','geolonia_timeout','geolonia_invalid_range','geolonia_size_limit','geolonia_unsafe_url','geolonia_unsafe_address','geolonia_unsupported_content','geolonia_missing_proof'}
                raise WorkerError(code if code in allowed else 'geolonia_invalid_response')
            if response.get('libraryVersion')!='3.1.3' or not isinstance(response.get('match'),dict) or not isinstance(response.get('proof'),dict):raise ValueError()
            validate_worker_result(response)
            return response
        except (ValueError,TypeError,KeyError,ValidationError,BrokenPipeError,ConnectionError):raise WorkerError('geolonia_invalid_response') from None

    async def _lookup(self,address,prefixes):
        out={'status':'empty','originalAddress':address,'matchedVariant':None,'match':None,'proof':None,'attempts':[],'unresolved':[],'libraryVersion':'3.1.3'}
        start=self.client.clock()
        allowed=min(30-self.spent,self.budget.geolonia_time_remaining())
        if allowed<=0:out.update(status='skipped',unresolved=['geolonia_time_limit']);return out
        try:
            async with asyncio.timeout(allowed):
                async with self.lock:
                    if self.failure_code:raise WorkerError(self.failure_code)
                    for variant in address_variants(address,grounded_prefixes=prefixes):
                        if variant['address'] in self.seen:continue
                        if len(self.seen)>=6:out['unresolved'].append('geolonia_variant_limit');break
                        elapsed=self.client.clock()-start
                        remaining=min(30-self.spent-elapsed,allowed-elapsed,self.budget.geolonia_time_remaining())
                        if remaining<=0:raise WorkerError('geolonia_time_limit')
                        self.seen.add(variant['address'])
                        attempt={'inputAddress':address,'queryAddress':variant['address'],'strategies':variant['strategies'],'startedAt':time.time(),'status':'running'}
                        out['attempts'].append(attempt)
                        try:result=await self._exchange(variant,remaining)
                        except WorkerError as error:
                            attempt.update(status='failed',errorCode=error.code,finishedAt=time.time());raise
                        reasons=match_reasons(address,variant,result['match'])
                        attempt.update(status='complete',match=result['match'],proof=result['proof'],reasons=reasons,finishedAt=time.time())
                        out.update(match=result['match'],proof=result['proof'],matchedVariant=variant)
                        if not reasons:out['status']='matched';break
                        if 'address_precision_unconfirmed' in reasons:out['status']='coarse'
                        out['unresolved']=list(dict.fromkeys(out['unresolved']+reasons))
        except TimeoutError:
            out.update(status='failed',unresolved=['geolonia_time_limit']);await self._stop()
        except WorkerError as error:
            self.failure_code=error.code
            out.update(status='unavailable' if error.code=='geolonia_unavailable' else 'failed',unresolved=[error.code]);await self._stop()
        except asyncio.CancelledError:
            await self._stop();raise
        finally:
            self.spent+=max(0,self.client.clock()-start)
            for attempt in out['attempts']:
                if attempt['status']=='running':attempt.update(status='failed',errorCode='geolonia_time_limit',finishedAt=time.time())
        return out
