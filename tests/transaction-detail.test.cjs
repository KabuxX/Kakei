const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const {
  detailHref,
  detailIdFromHash,
  removePersistedTransaction,
  removePersistedSamples,
} = require('../front/transaction-detail.js');

test('special characters in a transaction ID survive a detail URL round trip', () => {
  const id = '食費 /# 1';
  const href = detailHref(id);
  assert.equal(href, '#transaction/%E9%A3%9F%E8%B2%BB%20%2F%23%201');
  assert.equal(detailIdFromHash(href), id);
});

test('non-detail and malformed hashes have no transaction ID', () => {
  assert.equal(detailIdFromHash('#transactions'), null);
  assert.equal(detailIdFromHash('#transaction/%ZZ'), null);
  assert.equal(detailIdFromHash('#transaction/'), null);
});

test('deletion persists the remaining transactions without mutating the input', () => {
  const items = Object.freeze([
    Object.freeze({ id: 'one', title: '食費' }),
    Object.freeze({ id: 'two', title: '交通' }),
  ]);
  let saved;
  const storage = { getItem() { return null; }, setItem(key, value) { saved = { key, value }; } };

  const remaining = removePersistedTransaction(items, 'one', storage, 'kakei-transactions-v1');

  assert.deepEqual(remaining, [{ id: 'two', title: '交通' }]);
  assert.deepEqual(saved, { key: 'kakei-transactions-v1', value: '[{"id":"two","title":"交通"}]' });
  assert.equal(items.length, 2);
});

test('a failed storage write leaves the source transactions unchanged', () => {
  const items = Object.freeze([{ id: 'one' }, { id: 'two' }]);
  const storage = { getItem() { return null; }, setItem() { throw new Error('quota exceeded'); } };

  assert.throws(() => removePersistedTransaction(items, 'one', storage, 'kakei-transactions-v1'), /quota exceeded/);
  assert.deepEqual(items, [{ id: 'one' }, { id: 'two' }]);
});

test('deletion preserves a transaction another tab saved during confirmation', () => {
  const beforeConfirmation = Object.freeze([{ id: 'one' }, { id: 'two' }]);
  let persisted = JSON.stringify([...beforeConfirmation, { id: 'new-in-other-tab' }]);
  const storage = {
    getItem() { return persisted; },
    setItem(_key, value) { persisted = value; },
  };

  const remaining = removePersistedTransaction(beforeConfirmation, 'one', storage, 'kakei-transactions-v1');

  assert.deepEqual(remaining, [{ id: 'two' }, { id: 'new-in-other-tab' }]);
  assert.deepEqual(JSON.parse(persisted), remaining);
});

test('clearing samples preserves a real transaction saved during confirmation', () => {
  const source = Object.freeze([{ id: 'sample-1' }, { id: 'mine' }]);
  let persisted = JSON.stringify([...source, { id: 'new-in-other-tab' }]);
  const storage = { getItem() { return persisted; }, setItem(_key, value) { persisted = value; } };

  const remaining = removePersistedSamples(source, storage, 'kakei-transactions-v1');

  assert.deepEqual(remaining, [{ id: 'mine' }, { id: 'new-in-other-tab' }]);
  assert.deepEqual(JSON.parse(persisted), remaining);
  assert.deepEqual(source, [{ id: 'sample-1' }, { id: 'mine' }]);
});

test('failed sample clearing leaves the source and saved data untouched', () => {
  const source = Object.freeze([{ id: 'sample-1' }, { id: 'mine' }]);
  const storage = { getItem() { return JSON.stringify(source); }, setItem() { throw new Error('quota exceeded'); } };

  assert.throws(() => removePersistedSamples(source, storage, 'kakei-transactions-v1'), /quota exceeded/);
  assert.deepEqual(source, [{ id: 'sample-1' }, { id: 'mine' }]);
});

test('tablet navigation links retain accessible names', () => {
  const html = readFileSync(require.resolve('../front/index.html'), 'utf8');
  const navigation = html.match(/<nav class="side-nav"[^>]*>([\s\S]*?)<\/nav>/)?.[1];
  assert.ok(navigation);
  const links = [...navigation.matchAll(/<a\b[^>]*class="nav-link[^>]*>/g)].map(([tag]) => tag);
  assert.equal(links.length, 4);
  for (const link of links) assert.match(link, /\baria-label="[^"]+"/);
});
