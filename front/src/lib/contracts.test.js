import { describe, expect, it, vi } from 'vitest';
import { ApiError, addTransaction, loadInitialTransactions, removeSamples, removeTransaction } from './api.js';
import { detailHref, detailIdFromHash } from './transaction-detail.js';
import { parseExpenseDraft, readExpenseDetails, serializeTransactionsCsv } from './transaction-data.js';
import { createSampleTransactions } from './sample-data.js';
import { dashboardForMonth } from './dashboard.js';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const json = (status, value) => ({ status, ok: status < 400, json: async () => value });

describe('initial server import', () => {
  it.each([
    [null, [{ id: 'sample-0' }]],
    ['[]', []],
  ])('imports %s once', async (raw, expected) => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(json(200, { initialized: false }))
      .mockResolvedValueOnce(json(201, { count: expected.length }))
      .mockResolvedValueOnce(json(200, { transactions: expected }));
    const result = await loadInitialTransactions({
      fetchImpl, storage: { getItem: () => raw }, sampleFactory: () => [{ id: 'sample-0' }],
    });
    expect(result).toEqual(expected);
    expect(JSON.parse(fetchImpl.mock.calls[1][1].body).transactions).toEqual(expected);
  });

  it('does not import malformed storage', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(json(200, { initialized: false }));
    await expect(loadInitialTransactions({ fetchImpl, storage: { getItem: () => '{' }, sampleFactory: () => [] })).rejects.toThrow();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('accepts a competing initializer', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(json(200, { initialized: false }))
      .mockResolvedValueOnce(json(409, { error: { code: 'already_initialized' } }))
      .mockResolvedValueOnce(json(200, { transactions: [] }));
    await expect(loadInitialTransactions({ fetchImpl, storage: { getItem: () => '[]' }, sampleFactory: () => [] })).resolves.toEqual([]);
  });
});

it('encodes unusual IDs consistently for links and writes', async () => {
  const id = 'a/b %日本語';
  expect(detailIdFromHash(detailHref(id))).toBe(id);
  const fetchImpl = vi.fn().mockResolvedValue({ status: 204, ok: true });
  await removeTransaction(id, fetchImpl);
  expect(fetchImpl.mock.calls[0][0]).toBe(`/api/transactions/${encodeURIComponent(id)}`);
});

it('preserves old expense fields and safe CSV escaping', () => {
  const record = { id: 'old', date: '2026-09-01', type: 'expense', title: '=SUM(1,1)', category: '食費', amount: 100 };
  expect(readExpenseDetails(record)).toEqual({ merchant: null, paymentMethod: null, items: [] });
  expect(serializeTransactionsCsv([record])).toContain("\"'=SUM(1,1)\"");
  expect(serializeTransactionsCsv([record])).toContain('"100","","",""');
});

it('uses September transaction JSON for fresh dashboard totals', () => {
  const samples = createSampleTransactions();
  expect(samples).toHaveLength(37);
  expect(samples.find((record) => record.id === 'sample-0')).toMatchObject({ title: '給与', amount: 320000 });
  const model = dashboardForMonth(samples, new Date(2026, 8, 1));
  expect(model.income).toBe(320000);
  expect(model.expense).toBe(130390);
  expect(model.balance).toBe(189610);
  expect(model.items[0].date).toBe('2026-09-30');
  expect(model.weekly).toHaveLength(5);
});

it('preserves the old sixteen transaction fixture as a separate JSON file', () => {
  const path = resolve(process.cwd(), 'src/data/old-samples.json');
  expect(existsSync(path)).toBe(true);
  const archived = JSON.parse(readFileSync(path, 'utf8'));
  expect(archived).toHaveLength(16);
  expect(archived[0]).toMatchObject({ id: 'sample-0', date: '2026-09-28', title: '給与', amount: 320000 });
});

it('loads an initialized server without touching browser storage', async () => {
  const fetchImpl = vi.fn()
    .mockResolvedValueOnce(json(200, { initialized: true }))
    .mockResolvedValueOnce(json(200, { transactions: [] }));
  await expect(loadInitialTransactions({ fetchImpl, storage: { getItem: () => { throw new Error('unexpected storage read'); } }, sampleFactory: () => [] })).resolves.toEqual([]);
  expect(fetchImpl.mock.calls.map(([path]) => path)).toEqual(['/api/status', '/api/transactions']);
});

it('preserves write methods, payloads, and server field errors', async () => {
  const draft = { title: '給与', date: '2026-09-01T09:17', type: 'income', category: '収入', amount: 100 };
  const fetchImpl = vi.fn()
    .mockResolvedValueOnce(json(201, { transaction: { id: 'new', ...draft, timeEstimated: false } }))
    .mockResolvedValueOnce({ status: 204, ok: true })
    .mockResolvedValueOnce(json(200, { deletedCount: 2 }))
    .mockResolvedValueOnce(json(400, { error: { code: 'validation_error', field: 'title', message: '内容を確認してください。' } }));
  expect(await addTransaction(draft, fetchImpl)).toMatchObject({ id: 'new' });
  await removeTransaction('a/b ?', fetchImpl);
  expect(await removeSamples(fetchImpl)).toBe(2);
  await expect(addTransaction(draft, fetchImpl)).rejects.toMatchObject({ status: 400, field: 'title' });
  expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual(draft);
  expect(fetchImpl.mock.calls.map(([path]) => path)).toEqual([
    '/api/transactions', '/api/transactions/a%2Fb%20%3F', '/api/samples', '/api/transactions',
  ]);
  expect(draft).toEqual({ title: '給与', date: '2026-09-01T09:17', type: 'income', category: '収入', amount: 100 });
});

it('rejects malformed server responses', async () => {
  const fetchImpl = vi.fn().mockResolvedValue(json(200, { initialized: true }));
  fetchImpl.mockResolvedValueOnce(json(200, { initialized: 'yes' }));
  await expect(loadInitialTransactions({ fetchImpl, storage: { getItem: () => null }, sampleFactory: () => [] })).rejects.toBeInstanceOf(ApiError);
});

it('keeps sample expense details consistent and income fields absent', () => {
  for (const record of createSampleTransactions()) {
    if (record.type === 'income') {
      expect(Object.hasOwn(record, 'merchant')).toBe(false);
      continue;
    }
    expect(record.merchant.trim().length).toBeGreaterThan(0);
    expect(['cash', 'credit_card', 'e_money', 'bank_account']).toContain(record.paymentMethod);
    expect(record.items.reduce((sum, item) => sum + item.amount, 0)).toBe(record.amount);
  }
});

it('preserves valid legacy fields and rejects inconsistent items', () => {
  expect(readExpenseDetails({ type: 'expense', amount: 300, merchant: ' 店 ', paymentMethod: 'cash', items: [{ name: 'パン', amount: 200 }] })).toEqual({ merchant: '店', paymentMethod: 'cash', items: [] });
  expect(readExpenseDetails({ type: 'expense', amount: 300, merchant: '店', paymentMethod: 'e_money', items: [{ name: 'パン', amount: 200 }, { name: '牛乳', amount: 100 }] }).items).toEqual([{ name: 'パン', amount: 200 }, { name: '牛乳', amount: 100 }]);
});

it('parses item totals and validates amounts and required expense fields', () => {
  expect(parseExpenseDraft({ merchant: ' 店 ', paymentMethod: 'cash', itemRows: [{ name: ' パン ', amount: '200' }], manualAmount: '' })).toEqual({ merchant: '店', paymentMethod: 'cash', items: [{ name: 'パン', amount: 200 }], amount: 200 });
  expect(parseExpenseDraft({ merchant: '店', paymentMethod: 'cash', itemRows: [], manualAmount: '500' }).amount).toBe(500);
  expect(() => parseExpenseDraft({ merchant: '', paymentMethod: 'cash', itemRows: [], manualAmount: '500' })).toThrow();
  expect(() => parseExpenseDraft({ merchant: '店', paymentMethod: '', itemRows: [], manualAmount: '500' })).toThrow();
  expect(() => parseExpenseDraft({ merchant: '店', paymentMethod: 'cash', itemRows: [{ name: 'パン', amount: '1.5' }], manualAmount: '' })).toThrow();
});

it('exports quoted items and leaves legacy columns empty', () => {
  const record = { id: 'a', date: '2026-10-01', type: 'expense', title: '買い物', category: '食費', amount: 300, merchant: '=店名', paymentMethod: 'cash', items: [{ name: 'パン, "大"', amount: 300 }] };
  const csv = serializeTransactionsCsv([record, { ...record, id: 'old', merchant: undefined, paymentMethod: undefined, items: undefined }]);
  expect(csv.startsWith('\uFEFF')).toBe(true);
  expect(csv).toContain("'=店名");
  expect(csv).toContain('パン,');
  expect(csv).toContain('"300","","","","",""');
});

it('exports minute date and precision', () => {
  const csv = serializeTransactionsCsv([
    { id: 'entered', date: '2026-10-03T09:17', timeEstimated: false, type: 'income', title: '給与', category: '収入', amount: 1000 },
    { id: 'estimated', date: '2026-10-03T08:00', timeEstimated: true, type: 'income', title: '旧給与', category: '収入', amount: 900 },
    { id: 'legacy', date: '2026-10-03', type: 'income', title: '旧日付', category: '収入', amount: 800 },
  ]);
  const rows = csv.slice(1).split('\r\n');
  expect(rows[0]).toBe('"日付","時刻の精度","種類","内容","カテゴリ","金額","店名・取引先","支払方法","品目","取引先住所","関連軌跡住所"');
  expect(rows[1]).toBe('"2026-10-03T09:17","入力時刻","収入","給与","収入","1000","","","","",""');
  expect(rows[2]).toBe('"2026-10-03T08:00","仮設定","収入","旧給与","収入","900","","","","",""');
  expect(rows[3]).toBe('"2026-10-03","仮設定","収入","旧日付","収入","800","","","","",""');
});

it('ignores non-detail and malformed hash values', () => {
  expect(detailIdFromHash('#transactions')).toBeNull();
  expect(detailIdFromHash('#transaction/%ZZ')).toBeNull();
  expect(detailIdFromHash('#transaction/')).toBeNull();
});
