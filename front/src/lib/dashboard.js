export const categories = [
  { name: '食費', color: '#415eee', budget: 60000 },
  { name: '住まい', color: '#92addf', budget: 90000 },
  { name: '日用品', color: '#b9a6ff', budget: 25000 },
  { name: '交通', color: '#ffab94', budget: 25000 },
  { name: '娯楽', color: '#e8b76b', budget: 30000 },
  { name: 'その他', color: '#86b6a9', budget: 20000 },
];

export const totalBudget = categories.reduce((total, category) => total + category.budget, 0);
export const yen = (value) => `¥${Math.abs(value).toLocaleString('ja-JP')}`;
export const monthKey = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;

export function dashboardForMonth(records, month) {
  const items = records.filter((item) => item.date.startsWith(monthKey(month)))
    .sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id));
  const { income, expense } = items.reduce((sum, item) => {
    sum[item.type] += item.amount;
    return sum;
  }, { income: 0, expense: 0 });
  const categoryTotals = categories.map((category) => ({
    ...category,
    amount: items.filter((item) => item.type === 'expense' && item.category === category.name)
      .reduce((total, item) => total + item.amount, 0),
  }));
  const weekly = [0, 0, 0, 0, 0];
  items.filter((item) => item.type === 'expense').forEach((item) => {
    const week = Math.min(4, Math.floor((Number(item.date.slice(-2)) - 1) / 7));
    weekly[week] += item.amount;
  });
  return { items, income, expense, balance: income - expense, remaining: totalBudget - expense, categoryTotals, weekly };
}
