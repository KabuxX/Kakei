import {it,expect} from 'vitest';
import {createDemoFetch} from '../../demo/api.js';
import snapshot from '../../demo/data/snapshot.json';
import {validateDemoSnapshot} from '../../demo/validate.js';
it('serves independent clones and rejects every write without HTTP fallback',async()=>{
 const api=createDemoFetch(snapshot);const a=await(await api('/api/transactions')).json();expect(a.transactions).toHaveLength(41);a.transactions.length=0;expect((await(await api('/api/transactions')).json()).transactions).toHaveLength(41);
 expect((await(await api('/api/budget')).json()).categories['食費']).toBe(80000);
 expect((await(await api('/api/trajectory')).json()).dates).toHaveLength(13);
 for(const method of ['POST','PUT','PATCH','DELETE'])expect((await api('/api/transactions',{method})).status).toBe(403);
 for(const path of ['/api/unknown','/api/agent/threads/missing','/api/trajectory/missing','/api/transactions/%ZZ'])expect((await api(path)).status).toBe(404);
 const signal=AbortSignal.abort();await expect(api('/api/status',{signal})).rejects.toMatchObject({name:'AbortError'});
});
it('keeps history and original metadata readable',async()=>{
 const api=createDemoFetch(snapshot);const t=snapshot.threads[0];expect((await(await api(`/api/agent/threads/${t.id}`)).json()).thread.messages.length).toBe(t.messages.length);
 for(const r of Object.values(snapshot.receipts))expect((await(await api(`/api/transactions/${r.transactionId}/receipts`)).json()).receipts.some(v=>v.id===r.id)).toBe(true);
});
it('rejects invalid budgets and event references at the data boundary',()=>{
 const s=structuredClone(snapshot);s.categories['食費']=-1;expect(()=>validateDemoSnapshot(s)).toThrow();s.categories['食費']=80000;s.timeline.days[0].events[0].placeId='missing';expect(()=>validateDemoSnapshot(s)).toThrow();
});
