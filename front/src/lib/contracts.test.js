import { describe, expect, it, vi } from 'vitest';
import { loadInitialTransactions, removeTransaction } from './api.js';
import { detailHref, detailIdFromHash } from './transaction-detail.js';
import { readExpenseDetails, serializeTransactionsCsv } from './transaction-data.js';
import { createSampleTransactions } from './sample-data.js';
import { dashboardForMonth } from './dashboard.js';

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

it('keeps sample values and monthly dashboard totals', () => {
  const samples = createSampleTransactions(new Date(2026, 8, 1));
  expect(samples).toHaveLength(16);
  expect(samples[0]).toMatchObject({ id: 'sample-0', title: '給与', amount: 320000 });
  const model = dashboardForMonth(samples, new Date(2026, 8, 1));
  expect(model.income).toBe(332000);
  expect(model.expense).toBe(173900);
  expect(model.balance).toBe(158100);
  expect(model.items[0].date).toBe('2026-09-28');
  expect(model.weekly).toHaveLength(5);
});
