import { expect, it } from 'vitest';
import { dashboardForMonth } from './dashboard.js';

it('uses saved category totals and leaves missing budgets unknown',()=>{
  const records=[{id:'food',date:'2026-09-01T12:00',type:'expense',category:'食費',amount:1200}];
  const month=new Date(2026,8,1);
  const budgets={'食費':110000,'住まい':90000,'日用品':25000,'交通':25000,'娯楽':30000,'その他':20000};
  expect(dashboardForMonth(records,month,budgets)).toMatchObject({totalBudget:300000,remaining:298800,expense:1200});
  expect(dashboardForMonth(records,month)).toMatchObject({totalBudget:null,remaining:null,expense:1200,balance:-1200});
});

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
