// @vitest-environment node
import { afterEach, expect, it } from 'vitest';
import { createServer as createHttpServer } from 'node:http';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createServer as createViteServer } from 'vite';

const root = fileURLToPath(new URL('..', import.meta.url));
const septemberTransactions = JSON.parse(readFileSync(new URL('./data/september-transactions.json', import.meta.url), 'utf8'));
const running = [];

async function startVite(mode) {
  const server = await createViteServer({ root, mode, server: { host: '127.0.0.1', port: 0 }, optimizeDeps: { noDiscovery: true } });
  running.push(() => server.close());
  await server.listen();
  return `http://127.0.0.1:${server.httpServer.address().port}`;
}

afterEach(async () => {
  await Promise.all(running.splice(0).map((close) => close()));
  delete process.env.KAKEI_API_TARGET;
});

it('edits shared category budgets in mock mode without persisting across server restarts',async()=>{
  let base=await startVite('mock');
  const initial=await (await fetch(base+'/api/budget')).json();
  expect(initial.categories).toEqual({'食費':60000,'住まい':90000,'日用品':25000,'交通':25000,'娯楽':30000,'その他':20000});
  const changed={categories:{...initial.categories,'食費':70000}};
  const save=await fetch(base+'/api/budget',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(changed)});
  expect(save.status).toBe(200);
  expect(await save.json()).toEqual(changed);
  expect(await (await fetch(base+'/api/budget')).json()).toEqual(changed);
  expect((await fetch(base+'/api/budget',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({categories:{...changed.categories,'食費':-1}})})).status).toBe(400);
  expect(await (await fetch(base+'/api/budget')).json()).toEqual(changed);
  await running.pop()();base=await startVite('mock');
  expect((await (await fetch(base+'/api/budget')).json()).categories['食費']).toBe(60000);
});

it('uses the 37-record September JSON in mock mode and preserves mock operations', async () => {
  let base = await startVite('mock');
  expect(await (await fetch(`${base}/api/status`)).json()).toEqual({ initialized: true });
  const initial = (await (await fetch(`${base}/api/transactions`)).json()).transactions;
  expect(initial).toHaveLength(37);
  expect(initial.map(({ id }) => id)).toEqual(septemberTransactions.map(({ id }) => id));
  expect(initial.every((record) => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(record.date)
    && record.timeEstimated === true)).toBe(true);
  expect(initial.find((record) => record.id === 'sample-0')).toMatchObject({
    date: '2026-09-28T10:48', timeEstimated: true,
  });
  expect(initial.filter((record) => record.date.slice(0, 10) === '2026-09-30').map(({ id, date }) => [id, date])).toEqual([
    ['sample-20260930-a', '2026-09-30T11:30'],
    ['sample-20260930-b', '2026-09-30T15:00'],
    ['sample-20260930-metro', '2026-09-30T18:30'],
  ]);

  const dateOnly = await fetch(`${base}/api/transactions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date: '2026-09-29', title: '日付のみ', type: 'income', category: '収入', amount: 100 }),
  });
  expect(dateOnly.status).toBe(400);

  const created = await fetch(`${base}/api/transactions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date: '2026-09-29T10:12', timeEstimated: true, title: '追加', type: 'income', category: '収入', amount: 100 }),
  });
  expect(created.status).toBe(201);
  const createdRecord = (await created.json()).transaction;
  expect(createdRecord).toMatchObject({ date: '2026-09-29T10:12', timeEstimated: false });
  const id = createdRecord.id;
  expect((await (await fetch(`${base}/api/transactions`)).json()).transactions).toHaveLength(initial.length + 1);
  expect((await fetch(`${base}/api/transactions/${id}`, { method: 'DELETE' })).status).toBe(204);
  expect((await (await fetch(`${base}/api/transactions`)).json()).transactions).toHaveLength(initial.length);

  await running.pop()();
  base = await startVite('mock');
  expect((await (await fetch(`${base}/api/transactions`)).json()).transactions).toEqual(initial);
});

it('forwards API requests to the configured backend in api mode', async () => {
  const upstream = createHttpServer((request, response) => {
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify({ path: request.url, method: request.method, origin: request.headers.origin, host: request.headers.host }));
  });
  await new Promise((resolve) => upstream.listen(0, '127.0.0.1', resolve));
  running.push(() => new Promise((resolve) => upstream.close(resolve)));
  process.env.KAKEI_API_TARGET = `http://127.0.0.1:${upstream.address().port}`;
  const base = await startVite('api');
  expect(await (await fetch(`${base}/api/transactions`, { method: 'POST', headers: { Origin: base } })).json()).toEqual({
    path: '/api/transactions', method: 'POST', origin: process.env.KAKEI_API_TARGET,
    host: new URL(process.env.KAKEI_API_TARGET).host,
  });
});

it('updates a mock transaction and preserves estimated time until the datetime changes',async()=>{
 const base=await startVite('mock');
 const initial=(await (await fetch(base+'/api/transactions')).json()).transactions[0];
 const {id,timeEstimated,...draft}=initial;
 const update=await fetch(base+'/api/transactions/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...draft,title:'編集した取引'})});
 expect(update.status).toBe(200);
 expect((await update.json()).transaction).toMatchObject({id,title:'編集した取引',timeEstimated:true});
 expect((await (await fetch(base+'/api/transactions')).json()).transactions[0].title).toBe('編集した取引');
 const moved=await fetch(base+'/api/transactions/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...draft,date:'2026-10-04T10:00'})});
 expect((await moved.json()).transaction.timeEstimated).toBe(false);
});
