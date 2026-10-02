import { expect, it } from 'vitest';
import { dashboardForMonth } from './dashboard.js';

it('groups minute transactions by calendar day', () => {
  const records = [
    { id: 'late', date: '2026-09-02T21:05', type: 'expense', category: '食費', amount: 200 },
    { id: 'early', date: '2026-09-02T09:17', type: 'expense', category: '食費', amount: 300 },
    { id: 'income', date: '2026-09-02T08:00', type: 'income', category: '収入', amount: 1000 },
    { id: 'next-week', date: '2026-09-08T12:00', type: 'expense', category: '交通', amount: 400 },
    { id: 'next-month', date: '2026-10-02T09:00', type: 'expense', category: '食費', amount: 900 },
  ];

  const model = dashboardForMonth(records, new Date(2026, 8, 1));

  expect(model.items.map(({ id }) => id)).toEqual(['next-week', 'late', 'early', 'income']);
  expect(model.income).toBe(1000);
  expect(model.expense).toBe(900);
  expect(model.weekly).toEqual([500, 400, 0, 0, 0]);
});
