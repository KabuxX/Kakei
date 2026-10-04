import { transactionCalendarDate, transactionMonthKey } from './transaction-datetime.js';
import {sumBudget} from './budget.js';

export const categories = [
  { name: '食費', color: '#415eee' },
  { name: '住まい', color: '#92addf' },
  { name: '日用品', color: '#b9a6ff' },
  { name: '交通', color: '#ffab94' },
  { name: '娯楽', color: '#e8b76b' },
  { name: 'その他', color: '#86b6a9' },
];

export const yen = (value) => `¥${Math.abs(value).toLocaleString('ja-JP')}`;
export const monthKey = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;

export function dashboardForMonth(records, month, budgets = null) {
  const items = records.filter((item) => transactionMonthKey(item.date) === monthKey(month))
    .sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id));
  const { income, expense } = items.reduce((sum, item) => {
    sum[item.type] += item.amount;
    return sum;
  }, { income: 0, expense: 0 });
  const categoryTotals = categories.map((category) => ({
    ...category,
    budget: budgets ? budgets[category.name] : null,
    amount: items.filter((item) => item.type === 'expense' && item.category === category.name)
      .reduce((total, item) => total + item.amount, 0),
  }));
  const weekly = [0, 0, 0, 0, 0];
  items.filter((item) => item.type === 'expense').forEach((item) => {
    const day = Number(transactionCalendarDate(item.date).slice(8, 10));
    const week = Math.min(4, Math.floor((day - 1) / 7));
    weekly[week] += item.amount;
  });
  const totalBudget = budgets ? sumBudget(budgets) : null;
  return { items, income, expense, balance: income - expense, totalBudget, remaining: totalBudget === null ? null : totalBudget - expense, categoryTotals, weekly };
}
