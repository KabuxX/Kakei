import { isValidTransactionDateTime } from './transaction-datetime.js';

  const maxAmount = 999999999;
  const PAYMENT_METHOD_LABELS = Object.freeze({
    cash: '現金',
    credit_card: 'クレジットカード',
    e_money: '電子マネー',
    bank_account: '銀行口座',
  });

  class ValidationError extends Error {
    constructor(field, message) {
      super(message);
      this.name = 'ValidationError';
      this.field = field;
    }
  }

  export function normalizeMerchantAddress(value) {
    if (value == null) return null;
    if (typeof value !== 'string') throw new ValidationError('merchantAddress', '住所は文字列で入力してください。');
    const result = value.replace(/\r\n?/g, '\n').trim();
    if ([...result].length > 500) throw new ValidationError('merchantAddress', '住所は500文字以内で入力してください。');
    return result || null;
  }

  function paymentMethodIsValid(value) {
    return typeof value === 'string' && Object.hasOwn(PAYMENT_METHOD_LABELS, value);
  }

  function readExpenseDetails(record) {
    if (record?.type !== 'expense') return { merchant: null, paymentMethod: null, items: [] };
    const merchant = typeof record.merchant === 'string' && record.merchant.trim() ? record.merchant.trim() : null;
    const paymentMethod = paymentMethodIsValid(record.paymentMethod) ? record.paymentMethod : null;
    let items = [];
    if (Array.isArray(record.items) && record.items.length > 0) {
      const valid = record.items.every((item) => item && typeof item.name === 'string' && item.name.trim() && Number.isInteger(item.amount) && item.amount > 0 && item.amount <= maxAmount);
      if (valid && record.items.reduce((sum, item) => sum + item.amount, 0) === record.amount) {
        items = record.items.map((item) => ({ name: item.name, amount: item.amount }));
      }
    }
    return { merchant, paymentMethod, items, ...(record.merchantAddress !== undefined ? {merchantAddress: normalizeMerchantAddress(record.merchantAddress)} : {}) };
  }

  function parseAmount(value, field) {
    const raw = String(value).trim();
    const amount = Number(raw);
    if (!/^\d+$/.test(raw) || !Number.isInteger(amount) || amount < 1 || amount > maxAmount) {
      throw new ValidationError(field, '1円から999,999,999円までの整数を入力してください。');
    }
    return amount;
  }

  function parseExpenseDraft({ merchant, merchantAddress, paymentMethod, itemRows, manualAmount }) {
    const cleanMerchant = typeof merchant === 'string' ? merchant.trim() : '';
    if (!cleanMerchant) throw new ValidationError('merchant', '店名・取引先を入力してください。');
    if (!paymentMethodIsValid(paymentMethod)) throw new ValidationError('paymentMethod', '支払方法を選んでください。');
    const items = [];
    for (const row of itemRows) {
      const name = typeof row.name === 'string' ? row.name.trim() : '';
      if (!name) throw new ValidationError('itemRows', '品目名と金額を入力してください。');
      const amount = parseAmount(row.amount, 'itemRows');
      items.push({ name, amount });
    }
    const amount = items.length ? items.reduce((sum, item) => sum + item.amount, 0) : parseAmount(manualAmount, 'amount');
    if (amount > maxAmount) throw new ValidationError('itemRows', '品目の合計は999,999,999円以下にしてください。');
    return { merchant: cleanMerchant, paymentMethod, items, amount, ...(merchantAddress !== undefined ? {merchantAddress: normalizeMerchantAddress(merchantAddress)} : {}) };
  }

  function serializeTransactionsCsv(records, addressContexts = []) {
    const quote = (value) => {
      const text = String(value);
      const safe = /^[=+\-@\t\r]/.test(text) && typeof value !== 'number' ? `'${text}` : text;
      return `"${safe.replace(/"/g, '""')}"`;
    };
    const rows = [['日付', '時刻の精度', '種類', '内容', 'カテゴリ', '金額', '店名・取引先', '支払方法', '品目', '取引先住所', '関連軌跡住所']];
    for (const record of records) {
      const details = readExpenseDetails(record);
      rows.push([
        record.date,
        record.timeEstimated === true || !isValidTransactionDateTime(record.date) ? '仮設定' : '入力時刻',
        record.type === 'income' ? '収入' : '支出',
        record.title,
        record.category,
        record.amount,
        details.merchant || '',
        PAYMENT_METHOD_LABELS[details.paymentMethod] || '',
        details.items.length ? JSON.stringify(details.items) : '',
        record.type === 'expense' ? record.merchantAddress || '' : '',
        record.type === 'expense' ? [...new Set((addressContexts.find(c=>c.transactionId===record.id)?.places || []).map(p=>p.address).filter(Boolean))].join('\n') : '',
      ]);
    }
    return `\uFEFF${rows.map((row) => row.map(quote).join(',')).join('\r\n')}`;
  }

export { PAYMENT_METHOD_LABELS, ValidationError, readExpenseDetails, parseExpenseDraft, serializeTransactionsCsv };
