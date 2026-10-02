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

it('uses the new 30-day September JSON in mock mode and preserves mock operations', async () => {
  let base = await startVite('mock');
  expect(await (await fetch(`${base}/api/status`)).json()).toEqual({ initialized: true });
  const initial = (await (await fetch(`${base}/api/transactions`)).json()).transactions;
  expect(initial).toEqual(septemberTransactions);
  expect(new Set(initial.map((record) => record.date)).size).toBe(30);

  const created = await fetch(`${base}/api/transactions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date: '2026-09-29', title: '追加', type: 'income', category: '収入', amount: 100 }),
  });
  expect(created.status).toBe(201);
  const id = (await created.json()).transaction.id;
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
