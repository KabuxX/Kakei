export const CATEGORY_NAMES = ['食費', '住まい', '日用品', '交通', '娯楽', 'その他'];
const MAX_AMOUNT = 999999999;

export function isValidBudget(categories) {
  return categories !== null && typeof categories === 'object' && !Array.isArray(categories)
    && Object.keys(categories).length === CATEGORY_NAMES.length
    && CATEGORY_NAMES.every(name => Object.hasOwn(categories, name)
      && Number.isInteger(categories[name]) && categories[name] >= 0 && categories[name] <= MAX_AMOUNT);
}

export function parseBudgetFields(fields) {
  const categories = {}, errors = {};
  for (const name of CATEGORY_NAMES) {
    const raw = String(fields[name] ?? '').trim();
    const amount = Number(raw);
    if (!/^\d+$/.test(raw) || !Number.isInteger(amount) || amount > MAX_AMOUNT) {
      errors[name] = '0円から999,999,999円までの整数を入力してください。';
    } else categories[name] = amount;
  }
  return {categories: Object.keys(errors).length ? null : categories, errors};
}

export const sumBudget = categories => CATEGORY_NAMES.reduce((sum, name) => sum + categories[name], 0);

export function budgetUsage(spent, limit) {
  return {percent: limit === 0 ? (spent > 0 ? 100 : 0) : Math.max(0, Math.min(100, spent / limit * 100)),
    over: spent > limit, excess: Math.max(0, spent - limit)};
}
