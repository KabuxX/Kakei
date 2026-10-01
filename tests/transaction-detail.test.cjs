const test = require('node:test');
const assert = require('node:assert/strict');
const {
  detailHref,
  detailIdFromHash,
  removePersistedTransaction,
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
  const storage = { setItem(key, value) { saved = { key, value }; } };

  const remaining = removePersistedTransaction(items, 'one', storage, 'kakei-transactions-v1');

  assert.deepEqual(remaining, [{ id: 'two', title: '交通' }]);
  assert.deepEqual(saved, { key: 'kakei-transactions-v1', value: '[{"id":"two","title":"交通"}]' });
  assert.equal(items.length, 2);
});

test('a failed storage write leaves the source transactions unchanged', () => {
  const items = Object.freeze([{ id: 'one' }, { id: 'two' }]);
  const storage = { setItem() { throw new Error('quota exceeded'); } };

  assert.throws(() => removePersistedTransaction(items, 'one', storage, 'kakei-transactions-v1'), /quota exceeded/);
  assert.deepEqual(items, [{ id: 'one' }, { id: 'two' }]);
});
