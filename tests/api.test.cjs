const test = require('node:test');
const assert = require('node:assert/strict');
const KakeiApi = require('../front/api.js');

const response = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

const income = { id: 'old-1', title: '給与', date: '2026-09-01', type: 'income', category: '収入', amount: 100 };

test('loads an initialized server without reading browser storage', async () => {
  const urls = [];
  const fetchImpl = async (url) => {
    urls.push(url);
    return url === '/api/status' ? response(200, { initialized: true }) : response(200, { transactions: [income] });
  };
  const storage = { getItem() { throw new Error('should not read storage'); } };
  const actual = await KakeiApi.loadInitialTransactions({ fetchImpl, storage, sampleFactory: () => [] });
  assert.deepEqual(actual, [income]);
  assert.deepEqual(urls, ['/api/status', '/api/transactions']);
});

test('imports an existing saved array, including an empty array', async () => {
  for (const records of [[income], []]) {
    const calls = [];
    const fetchImpl = async (url, options = {}) => {
      calls.push({ url, options });
      if (url === '/api/status') return response(200, { initialized: false });
      if (url === '/api/initialize') return response(201, { count: records.length });
      return response(200, { transactions: records });
    };
    const storage = { getItem: () => JSON.stringify(records) };
    assert.deepEqual(await KakeiApi.loadInitialTransactions({ fetchImpl, storage, sampleFactory: () => [income] }), records);
    assert.deepEqual(calls.map(({ url }) => url), ['/api/status', '/api/initialize', '/api/transactions']);
    assert.deepEqual(JSON.parse(calls[1].options.body), { transactions: records });
  }
});

test('seeds samples only when the saved key is absent', async () => {
  const calls = [];
  let sampleCalls = 0;
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, options });
    if (url === '/api/status') return response(200, { initialized: false });
    if (url === '/api/initialize') return response(201, { count: 1 });
    return response(200, { transactions: [income] });
  };
  const records = await KakeiApi.loadInitialTransactions({
    fetchImpl,
    storage: { getItem: () => null },
    sampleFactory: () => { sampleCalls++; return [income]; },
  });
  assert.deepEqual(records, [income]);
  assert.equal(sampleCalls, 1);
  assert.deepEqual(JSON.parse(calls[1].options.body), { transactions: [income] });
});

test('corrupt saved JSON or inaccessible storage stops before import', async () => {
  for (const getItem of [() => '{bad', () => '{}', () => { throw new Error('blocked'); }]) {
    const urls = [];
    const fetchImpl = async (url) => { urls.push(url); return response(200, { initialized: false }); };
    await assert.rejects(() => KakeiApi.loadInitialTransactions({ fetchImpl, storage: { getItem }, sampleFactory: () => [income] }));
    assert.deepEqual(urls, ['/api/status']);
  }
});

test('an initialization conflict loads the winning server data', async () => {
  const urls = [];
  const winner = { ...income, id: 'other' };
  const fetchImpl = async (url) => {
    urls.push(url);
    if (url === '/api/status') return response(200, { initialized: false });
    if (url === '/api/initialize') return response(409, { error: { code: 'already_initialized', message: 'already' } });
    return response(200, { transactions: [winner] });
  };
  const records = await KakeiApi.loadInitialTransactions({ fetchImpl, storage: { getItem: () => '[]' }, sampleFactory: () => [] });
  assert.deepEqual(records, [winner]);
  assert.deepEqual(urls, ['/api/status', '/api/initialize', '/api/transactions']);
});

test('create, delete, and clear samples use the expected API requests', async () => {
  const calls = [];
  const draft = { title: '給与', date: '2026-09-01', type: 'income', category: '収入', amount: 100 };
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    if (url === '/api/transactions') return response(201, { transaction: income });
    if (url === '/api/samples') return response(200, { deletedCount: 2 });
    return response(204);
  };
  assert.deepEqual(await KakeiApi.addTransaction(draft, fetchImpl), income);
  assert.equal(await KakeiApi.removeTransaction('a/b ?', fetchImpl), undefined);
  assert.equal(await KakeiApi.removeSamples(fetchImpl), 2);
  assert.deepEqual(calls.map(({ url, options }) => [options.method, url]), [
    ['POST', '/api/transactions'],
    ['DELETE', '/api/transactions/a%2Fb%20%3F'],
    ['DELETE', '/api/samples'],
  ]);
  assert.deepEqual(JSON.parse(calls[0].options.body), draft);
  assert.equal(calls[1].options.body, undefined);
});

test('failed writes reject without changing the draft', async () => {
  const draft = { title: '給与', date: '2026-09-01', type: 'income', category: '収入', amount: 100 };
  const original = structuredClone(draft);
  const fetchImpl = async () => response(400, { error: { code: 'invalid_transaction', field: 'title', message: '内容を確認してください。' } });
  await assert.rejects(() => KakeiApi.addTransaction(draft, fetchImpl), (error) => {
    assert.equal(error.status, 400);
    assert.equal(error.field, 'title');
    return true;
  });
  await assert.rejects(() => KakeiApi.removeTransaction('old-1', fetchImpl), KakeiApi.ApiError);
  await assert.rejects(() => KakeiApi.removeSamples(fetchImpl), KakeiApi.ApiError);
  assert.deepEqual(draft, original);
});
