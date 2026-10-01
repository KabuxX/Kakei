const test = require('node:test');
const assert = require('node:assert/strict');
const { createSampleTransactions, persistEnrichedSamples } = require('../front/sample-data.js');

test('every sample expense has concrete details whose items add to its amount', () => {
  const samples = createSampleTransactions(new Date(2026, 8, 1));
  const expenses = samples.filter((record) => record.type === 'expense');
  const incomes = samples.filter((record) => record.type === 'income');
  assert.equal(samples.length, 16);
  assert.equal(expenses.length, 14);
  assert.equal(incomes.length, 2);
  for (const record of expenses) {
    assert.ok(record.merchant.trim(), `${record.id}: merchant`);
    assert.ok(['cash', 'credit_card', 'e_money', 'bank_account'].includes(record.paymentMethod), `${record.id}: payment`);
    assert.ok(record.items.length > 0, `${record.id}: items`);
    assert.ok(record.items.every((item) => item.name.trim() && Number.isInteger(item.amount) && item.amount > 0), `${record.id}: valid items`);
    assert.equal(record.items.reduce((sum, item) => sum + item.amount, 0), record.amount, `${record.id}: total`);
  }
  for (const record of incomes) {
    assert.equal(Object.hasOwn(record, 'merchant'), false);
    assert.equal(Object.hasOwn(record, 'paymentMethod'), false);
    assert.equal(Object.hasOwn(record, 'items'), false);
  }
});

test('saved old samples gain details while newer user records remain intact', () => {
  const oldSample = Object.freeze({ id: 'sample-3', date: '2026-08-24', title: '電車・バス', category: '交通', amount: 4200, type: 'expense' });
  const source = Object.freeze([oldSample]);
  const userRecord = { id: 'custom-1', date: '2026-08-24', title: '電車・バス', category: '交通', amount: 4200, type: 'expense' };
  let saved = JSON.stringify([oldSample, userRecord]);
  const storage = { getItem() { return saved; }, setItem(_key, value) { saved = value; } };

  const result = persistEnrichedSamples(source, storage, 'kakei-transactions-v1');

  assert.deepEqual(result[1], userRecord);
  assert.equal(result[0].merchant, '東都交通');
  assert.equal(result[0].paymentMethod, 'e_money');
  assert.equal(result[0].items.reduce((sum, item) => sum + item.amount, 0), 4200);
  assert.deepEqual(JSON.parse(saved), result);
  assert.deepEqual(source, [oldSample]);
});

test('existing sample details are not overwritten', () => {
  const custom = { id: 'sample-1', date: '2026-08-27', title: '週末の買い物', category: '食費', amount: 6840, type: 'expense', merchant: '既存の店', paymentMethod: 'cash', items: [{ name: '既存品目', amount: 6840 }] };
  let writes = 0;
  const storage = { getItem() { return JSON.stringify([custom]); }, setItem() { writes += 1; } };

  assert.deepEqual(persistEnrichedSamples([custom], storage, 'kakei-transactions-v1'), [custom]);
  assert.equal(writes, 0);
});

test('failed sample enrichment leaves old data available without overwriting storage', () => {
  const oldSample = Object.freeze({ id: 'sample-3', date: '2026-08-24', title: '電車・バス', category: '交通', amount: 4200, type: 'expense' });
  const source = Object.freeze([oldSample]);
  const storage = { getItem() { return JSON.stringify(source); }, setItem() { throw new Error('quota exceeded'); } };

  assert.throws(() => persistEnrichedSamples(source, storage, 'kakei-transactions-v1'), /quota exceeded/);
  assert.deepEqual(source, [oldSample]);
});
