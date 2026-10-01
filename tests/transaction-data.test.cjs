const test = require('node:test');
const assert = require('node:assert/strict');
const {
  PAYMENT_METHOD_LABELS,
  readExpenseDetails,
  parseExpenseDraft,
  persistAddedTransaction,
} = require('../front/transaction-data.js');

const draft = (changes = {}) => ({
  merchant: '店', paymentMethod: 'cash', itemRows: [], manualAmount: '500', ...changes,
});

test('old expenses remain readable without invented details', () => {
  assert.deepEqual(readExpenseDetails({ type: 'expense', amount: 300 }), {
    merchant: null, paymentMethod: null, items: [],
  });
});

test('malformed extra fields do not remove the valid ones', () => {
  assert.deepEqual(readExpenseDetails({
    type: 'expense', amount: 300, merchant: ' 店 ', paymentMethod: 'unknown', items: 'bad',
  }), { merchant: '店', paymentMethod: null, items: [] });
  assert.deepEqual(readExpenseDetails({
    type: 'expense', amount: 300, merchant: 12, paymentMethod: 'cash', items: [{ name: 'パン', amount: 200 }],
  }), { merchant: null, paymentMethod: 'cash', items: [] });
});

test('valid item details preserve names and amounts', () => {
  assert.deepEqual(readExpenseDetails({
    type: 'expense', amount: 300, merchant: '店', paymentMethod: 'e_money',
    items: [{ name: 'パン', amount: 200 }, { name: '牛乳', amount: 100 }],
  }).items, [{ name: 'パン', amount: 200 }, { name: '牛乳', amount: 100 }]);
  assert.equal(PAYMENT_METHOD_LABELS.e_money, '電子マネー');
});

test('itemized expenses derive the total and trim names', () => {
  assert.deepEqual(parseExpenseDraft(draft({
    merchant: ' 店 ', itemRows: [{ name: ' パン ', amount: '200' }, { name: '牛乳', amount: '100' }], manualAmount: '',
  })), {
    merchant: '店', paymentMethod: 'cash', amount: 300,
    items: [{ name: 'パン', amount: 200 }, { name: '牛乳', amount: 100 }],
  });
});

test('unitemized expenses keep the manually entered amount', () => {
  assert.deepEqual(parseExpenseDraft(draft()), {
    merchant: '店', paymentMethod: 'cash', items: [], amount: 500,
  });
});

test('expense draft rejects missing merchant and payment method', () => {
  assert.throws(() => parseExpenseDraft(draft({ merchant: '   ' })), { field: 'merchant' });
  assert.throws(() => parseExpenseDraft(draft({ paymentMethod: '' })), { field: 'paymentMethod' });
  assert.throws(() => parseExpenseDraft(draft({ paymentMethod: 'crypto' })), { field: 'paymentMethod' });
});

test('expense draft rejects incomplete or noninteger item rows', () => {
  for (const row of [
    { name: ' ', amount: '100' }, { name: 'パン', amount: '' },
    { name: 'パン', amount: '0' }, { name: 'パン', amount: '1.5' },
  ]) {
    assert.throws(() => parseExpenseDraft(draft({ itemRows: [row] })), { field: 'itemRows' });
  }
});

test('expense draft rejects amounts outside the supported range', () => {
  for (const amount of ['0', '1.5', '1000000000', '']) {
    assert.throws(() => parseExpenseDraft(draft({ manualAmount: amount })), { field: 'amount' });
  }
  assert.throws(() => parseExpenseDraft(draft({ itemRows: [
    { name: 'A', amount: '999999999' }, { name: 'B', amount: '1' },
  ] })), { field: 'itemRows' });
});

test('adding a transaction preserves a newer record from another tab', () => {
  const source = Object.freeze([{ id: 'old' }]);
  let saved = JSON.stringify([{ id: 'old' }, { id: 'other-tab' }]);
  const storage = { getItem() { return saved; }, setItem(_key, value) { saved = value; } };
  const result = persistAddedTransaction(source, { id: 'new' }, storage, 'key', (item) => typeof item?.id === 'string');
  assert.deepEqual(result, [{ id: 'old' }, { id: 'other-tab' }, { id: 'new' }]);
  assert.deepEqual(JSON.parse(saved), result);
  assert.deepEqual(source, [{ id: 'old' }]);
});

test('storage read and write failures leave the source untouched', () => {
  const source = Object.freeze([{ id: 'old' }]);
  const brokenRead = { getItem() { throw new Error('read blocked'); }, setItem() { throw new Error('unexpected write'); } };
  const brokenWrite = { getItem() { return null; }, setItem() { throw new Error('quota'); } };
  assert.throws(() => persistAddedTransaction(source, { id: 'new' }, brokenRead, 'key'), /read blocked/);
  assert.throws(() => persistAddedTransaction(source, { id: 'new' }, brokenWrite, 'key'), /quota/);
  assert.deepEqual(source, [{ id: 'old' }]);
});

test('malformed saved data is not overwritten', () => {
  let writes = 0;
  const storage = { getItem() { return '{broken'; }, setItem() { writes += 1; } };
  assert.throws(() => persistAddedTransaction([], { id: 'new' }, storage, 'key'), SyntaxError);
  assert.equal(writes, 0);
});
