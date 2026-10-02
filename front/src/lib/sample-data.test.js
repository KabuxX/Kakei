import { describe, expect, it } from 'vitest';
import oldSamples from '../data/old-samples.json';
import { createSampleTransactions } from './sample-data.js';

describe('September sample transactions', () => {
  it('keeps unique September contents with unique valid transaction IDs', () => {
    const records = createSampleTransactions();
    expect(records).toHaveLength(37);
    const keys = records.map(({ type, title, category, amount, merchant, paymentMethod, items }) => JSON.stringify([type, title, category, amount, merchant, paymentMethod, items?.map(({ name, amount }) => [name, amount])]));
    expect(new Set(keys).size).toBe(37);
    expect(records.find((record) => record.id === 'sample-0')).toEqual(oldSamples.find((record) => record.id === 'sample-0'));
    expect(new Set(records.map((record) => record.id)).size).toBe(records.length);
    expect(records.find((record) => record.id === 'sample-0')).toMatchObject({ date: '2026-09-28', title: '給与', amount: 320000 });
  });

  it('keeps expense items consistent with transaction amounts', () => {
    const expenses = createSampleTransactions().filter((record) => record.type === 'expense');
    expect(expenses.length).toBeGreaterThan(0);
    for (const record of expenses) {
      expect(record.merchant).toBeTruthy();
      expect(record.items.reduce((total, item) => total + item.amount, 0)).toBe(record.amount);
    }
  });

  it('returns a fresh copy so callers cannot mutate later initializations', () => {
    const first = createSampleTransactions();
    first[0].title = '書き換え';
    first.find((record) => record.type === 'expense').items[0].name = '書き換え';
    const second = createSampleTransactions();
    expect(second[0].title).not.toBe('書き換え');
    expect(second.find((record) => record.type === 'expense').items[0].name).not.toBe('書き換え');
  });
});
