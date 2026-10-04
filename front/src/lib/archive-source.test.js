import { describe, it, expect } from 'vitest';
import { createArchiveSource } from '../../demo/maps/archive-source.js';
const url = 'http://localhost:3000/Kakei/maps/tokyo.pmtiles';
const bytes = new Uint8Array([0,1,2,3,4,5,6,7]);
const source = (fetchImpl, maxBytes=8) => createArchiveSource(url,{fetchImpl,maxBytes});
const response = (status=200, body=bytes, headers={}) => new Response(body,{status,headers});
describe('bounded same-origin archive source',()=>{
 it('returns exactly requested bytes from valid 206',async()=>{ const s=source(async(_,o)=>{expect(o.headers.Range).toBe('bytes=2-4');return response(206,bytes.slice(2,5),{'Content-Range':'bytes 2-4/8'});});expect(new Uint8Array((await s.getBytes(2,3)).data)).toEqual(new Uint8Array([2,3,4]));});
 it.each(['bytes 1-3/8','bytes 2-4/*','bytes 2-4/99'])('rejects malformed or oversized range %s',async range=>{await expect(source(async()=>response(206,bytes.slice(2,5),{'Content-Range':range})).getBytes(2,3)).rejects.toThrow();});
 it('rejects short 206 bytes',async()=>{await expect(source(async()=>response(206,bytes.slice(2,4),{'Content-Range':'bytes 2-4/8'})).getBytes(2,3)).rejects.toThrow();});
 it('shares and retains a full 200 response across concurrent calls',async()=>{let calls=0;const s=source(async()=>{calls++;await new Promise(r=>setTimeout(r,5));return response();});const result=await Promise.all([s.getBytes(2,3),s.getBytes(5,2)]);expect(result.map(r=>Array.from(new Uint8Array(r.data)))).toEqual([[2,3,4],[5,6]]);await s.getBytes(0,1);expect(calls).toBe(1);});
 it('enforces actual bytes even without Content-Length',async()=>{await expect(source(async()=>response(),7).getBytes(0,1)).rejects.toThrow();});
 it('retries after 404 instead of caching rejection',async()=>{let calls=0;const s=source(async()=>response(++calls===1?404:200));await expect(s.getBytes(0,1)).rejects.toThrow();expect(new Uint8Array((await s.getBytes(0,1)).data)).toEqual(new Uint8Array([0]));});
 it('aborts one waiter without breaking concurrent readers',async()=>{const s=source(async()=>{await new Promise(r=>setTimeout(r,10));return response();});const c=new AbortController();const first=s.getBytes(0,1,c.signal);const second=s.getBytes(2,1);c.abort();await expect(first).rejects.toMatchObject({name:'AbortError'});expect(new Uint8Array((await second).data)).toEqual(new Uint8Array([2]));});
 it('rejects external URLs before fetch',()=>{expect(()=>createArchiveSource('https://example.com/a',{maxBytes:8})).toThrow();});
 it('rejects invalid requests',async()=>{const s=source(async()=>response());await expect(s.getBytes(-1,3)).rejects.toThrow();await expect(s.getBytes(7,2)).rejects.toThrow();});
});
