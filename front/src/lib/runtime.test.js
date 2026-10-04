import {expect,it,vi} from 'vitest';
import * as runtime from './runtime.js';
import * as demo from '../../demo/runtime.js';
it('uses previous month and real fetch only for the normal runtime',async()=>{
 expect(runtime.getInitialMonth(new Date(2029,1,15)).getMonth()).toBe(0);expect(runtime.receiptUrl('a b','t')).toBe('/api/agent/threads/t/receipts/a%20b');
 const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response('{}'));await runtime.apiFetch('/api/status');expect(fetch).toHaveBeenCalledWith('/api/status',undefined);fetch.mockRestore();
});
it('starts with the snapshot month even years later and uses base-aware originals',()=>{
 const date=demo.getInitialMonth(new Date(2029,0,1));expect(date.getFullYear()).toBe(2026);expect(date.getMonth()).toBe(9);expect(demo.snapshotTime).toBeGreaterThan(0);expect(demo.readOnly).toBe(true);
 expect(demo.receiptUrl('3832da1f-f349-4ab2-8b7b-2b7463e8ebbf')).toMatch(/demo-data\/receipts\/.*\.png$/);
});
