const KakeiTransactionData = (() => {
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
    return { merchant, paymentMethod, items };
  }

  function parseAmount(value, field) {
    const raw = String(value).trim();
    const amount = Number(raw);
    if (!/^\d+$/.test(raw) || !Number.isInteger(amount) || amount < 1 || amount > maxAmount) {
      throw new ValidationError(field, '1円から999,999,999円までの整数を入力してください。');
    }
    return amount;
  }

  function parseExpenseDraft({ merchant, paymentMethod, itemRows, manualAmount }) {
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
    return { merchant: cleanMerchant, paymentMethod, items, amount };
  }

  function persistAddedTransaction(items, newRecord, storage, key, isValid = () => true) {
    const raw = storage.getItem(key);
    const current = raw === null ? items : JSON.parse(raw);
    if (!Array.isArray(current)) throw new Error('保存された取引データが不正です。');
    const next = [...current.filter(isValid), newRecord];
    storage.setItem(key, JSON.stringify(next));
    return next;
  }

  return { PAYMENT_METHOD_LABELS, ValidationError, readExpenseDetails, parseExpenseDraft, persistAddedTransaction };
})();

globalThis.KakeiTransactionData = KakeiTransactionData;
if (typeof module !== 'undefined') module.exports = KakeiTransactionData;
