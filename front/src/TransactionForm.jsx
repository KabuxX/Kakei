import React, { useRef, useState } from 'react';
import MerchantAddressField from './MerchantAddressField.jsx';
import { Icon } from './AppShell.jsx';
import { categories } from './lib/dashboard.js';
import { ApiError } from './lib/api.js';
import { parseExpenseDraft, readExpenseDetails, ValidationError } from './lib/transaction-data.js';
import { dateTimeLocalValue, isValidTransactionDateTime } from './lib/transaction-datetime.js';

const maxAmount = 999999999;
const baseFieldIds = { title: 'title-input', amount: 'amount-input', date: 'date-input', merchant: 'merchant-input', merchantAddress: 'merchant-address-input', paymentMethod: 'payment-method-input', itemRows: 'item-rows' };

export default function TransactionForm({ record = null, busy = false, onCancel, onSubmit, onSaved, prefix = '' }) {
  const form = useRef(null);
  const initial = readExpenseDetails(record);
  const fieldIds = Object.fromEntries(Object.entries(baseFieldIds).map(([key,value])=>[key,prefix+value]));
  const sequence = useRef(initial.items.length);
  const pending = useRef(false);
  const [type, setType] = useState(record?.type || 'expense');
  const [title, setTitle] = useState(record?.title || '');
  const [manualAmount, setManualAmount] = useState(record ? String(record.amount) : '');
  const [date, setDate] = useState(record?.date || dateTimeLocalValue());
  const [category, setCategory] = useState(record?.category || categories[0].name);
  const [merchantAddress, setMerchantAddress] = useState(initial.merchantAddress || '');
  const [merchant, setMerchant] = useState(initial.merchant || '');
  const [paymentMethod, setPaymentMethod] = useState(initial.paymentMethod || '');
  const [itemRows, setItemRows] = useState(()=>initial.items.map((item,index)=>({key:index+1,name:item.name,amount:String(item.amount)})));
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const blocked = busy || submitting;
  const itemized = type === 'expense' && itemRows.length > 0;
  const validItems = itemRows.every((row) => row.name.trim() && /^\d+$/.test(row.amount.trim()) && Number(row.amount) > 0);
  const itemTotal = itemRows.reduce((sum, row) => sum + Number(row.amount), 0);
  const amount = itemized ? validItems && itemTotal <= maxAmount ? String(itemTotal) : '' : manualAmount;

  const showError = (field, message) => {
    setErrors((current) => ({ ...current, [field]: message }));
    let selector = `#${fieldIds[field]}`;
    if (field === 'itemRows') {
      const row = itemRows.find((item) => !item.name.trim() || !/^\d+$/.test(item.amount.trim()) || Number(item.amount) < 1 || Number(item.amount) > maxAmount) || itemRows.at(-1);
      selector = row ? `[data-item-key="${row.key}"] ${row.name.trim() ? '[data-item-amount]' : '[data-item-name]'}` : `#${prefix}add-item`;
    }
    form.current?.querySelector(selector)?.focus();
    requestAnimationFrame(()=>form.current?.querySelector(selector)?.focus());
  };
  const changeType = (next) => { setType(next); setCategory(next === 'income' ? '収入' : categories[0].name); setErrors({}); };
  const addItem = () => {
    sequence.current += 1;
    const key = sequence.current;
    setItemRows((current) => [...current, { key, name: '', amount: '' }]);
    requestAnimationFrame(() => form.current?.querySelector(`[data-item-key="${key}"] [data-item-name]`)?.focus());
  };
  const updateItem = (key, field, value) => {
    setItemRows((current) => current.map((row) => row.key === key ? { ...row, [field]: value } : row));
    setErrors((current) => ({ ...current, itemRows: '' }));
  };
  const removeItem = (key) => {
    setItemRows((current) => current.filter((row) => row.key !== key));
    form.current?.querySelector(`#${prefix}add-item`)?.focus();
  };

  const submit = async (event) => {
    event.preventDefault();
    if (blocked || pending.current) return;
    setErrors({}); setFormError('');
    const cleanTitle = title.trim();
    if (!cleanTitle) { showError('title', '内容を入力してください。'); return; }
    if (!isValidTransactionDateTime(date)) { showError('date', '正しい日時を入力してください。'); return; }
    let parsedAmount;
    let details = {};
    if (type === 'expense') {
      try {
        details = parseExpenseDraft({ merchant, merchantAddress, paymentMethod, itemRows, manualAmount });
        parsedAmount = details.amount;
      } catch (cause) {
        if (cause instanceof ValidationError) { showError(cause.field, cause.message); return; }
        throw cause;
      }
    } else {
      parsedAmount = Number(manualAmount.trim());
      if (!/^\d+$/.test(manualAmount.trim()) || !Number.isInteger(parsedAmount) || parsedAmount < 1 || parsedAmount > maxAmount) { showError('amount', '1円から999,999,999円までの整数を入力してください。'); return; }
    }
    pending.current = true;
    setSubmitting(true);
    try {
      await onSubmit({ title: cleanTitle, amount: parsedAmount, date, type, category, ...details });
      onSaved?.();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 400 && ['title', 'date', 'amount', 'merchant', 'merchantAddress', 'paymentMethod', 'items'].includes(cause.field)) {
        showError(cause.field === 'items' ? 'itemRows' : cause.field, cause.message);
      } else {
        setFormError(cause instanceof ApiError && cause.status === 404 ? cause.message : '保存できませんでした。サーバーへの接続を確認して再試行してください。');
      }
    } finally {
      pending.current = false;
      setSubmitting(false);
    }
  };

  return <form ref={form} id={`${prefix}transaction-form`} noValidate onSubmit={submit}>
      <fieldset disabled={blocked} className="transaction-form-fields">
      <div className="type-tabs" role="group" aria-label="取引の種類"><label><input type="radio" name="type" value="expense" checked={type === 'expense'} onChange={() => changeType('expense')} /><span>支出</span></label><label><input type="radio" name="type" value="income" checked={type === 'income'} onChange={() => changeType('income')} /><span>収入</span></label></div>
      <div className="form-grid">
        <label className="field full"><span>内容 <em>必須</em></span><input id={`${prefix}title-input`} name="title" type="text" maxLength="60" placeholder="例：スーパーで買い物" aria-describedby={`${prefix}title-error`} aria-invalid={!!errors.title || undefined} required disabled={blocked} value={title} onChange={(event) => setTitle(event.target.value)} /><small id={`${prefix}title-error`} role="alert" className="field-error" hidden={!errors.title}>{errors.title}</small></label>
        <label className="field"><span>金額 <em>必須</em></span><span className="yen-input"><b>¥</b><input id={`${prefix}amount-input`} name="amount" type="number" inputMode="numeric" min="1" max="999999999" placeholder="0" aria-describedby={`${prefix}amount-error`} aria-invalid={!!errors.amount || undefined} disabled={blocked} required={!itemized} readOnly={itemized} value={amount} onChange={(event) => setManualAmount(event.target.value)} /></span><small id={`${prefix}amount-error`} role="alert" className="field-error" hidden={!errors.amount}>{errors.amount}</small></label>
        <label className="field"><span>日付と時刻 <em>必須</em></span><input id={`${prefix}date-input`} name="date" type="datetime-local" step="60" aria-describedby={`${prefix}date-error`} aria-invalid={!!errors.date || undefined} required disabled={blocked} value={date} onChange={(event) => setDate(event.target.value)} /><small id={`${prefix}date-error`} role="alert" className="field-error" hidden={!errors.date}>{errors.date}</small></label>
        <label className="field full"><span>カテゴリ</span><select id={`${prefix}category-input`} name="category" disabled={blocked} value={category} onChange={(event) => setCategory(event.target.value)}>{(type === 'income' ? ['収入'] : categories.map((item) => item.name)).map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
      </div>
      <div id={`${prefix}expense-fields`} className="expense-fields" hidden={type !== 'expense'}>
        <div className="form-grid"><label className="field full"><span>店名・取引先 <em>必須</em></span><input id={`${prefix}merchant-input`} name="merchant" type="text" maxLength="60" placeholder="例：スーパー○○" aria-describedby={`${prefix}merchant-error`} aria-invalid={!!errors.merchant || undefined} required={type === 'expense'} disabled={type !== 'expense' || blocked} value={merchant} onChange={(event) => setMerchant(event.target.value)} /><small id={`${prefix}merchant-error`} role="alert" className="field-error" hidden={!errors.merchant}>{errors.merchant}</small></label><label className="field full"><span>支払方法 <em>必須</em></span><select id={`${prefix}payment-method-input`} name="paymentMethod" aria-describedby={`${prefix}payment-method-error`} aria-invalid={!!errors.paymentMethod || undefined} required={type === 'expense'} disabled={type !== 'expense' || blocked} value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}><option value="">選択してください</option><option value="cash">現金</option><option value="credit_card">クレジットカード</option><option value="e_money">電子マネー</option><option value="bank_account">銀行口座</option></select><small id={`${prefix}payment-method-error`} role="alert" className="field-error" hidden={!errors.paymentMethod}>{errors.paymentMethod}</small></label></div>
        <MerchantAddressField id={`${prefix}merchant-address-input`} value={merchantAddress} onChange={setMerchantAddress} error={errors.merchantAddress} disabled={type !== 'expense' || blocked}/>
        <div className="item-section" aria-labelledby={`${prefix}item-section-title`}><div className="item-section-head"><strong id={`${prefix}item-section-title`}>品目 <span>任意</span></strong><button id={`${prefix}add-item`} type="button" className="item-add" onClick={addItem} disabled={type !== 'expense' || blocked}>＋ 品目を追加</button></div><div id={`${prefix}item-rows`} className="item-rows">{itemRows.map((row) => <div className="item-row" key={row.key} data-item-key={row.key}><label><span>品目名</span><input data-item-name type="text" maxLength="60" aria-label={`品目${row.key}の名前`} aria-describedby={`${prefix}items-error`} placeholder="例：パン" value={row.name} onChange={(event) => updateItem(row.key, 'name', event.target.value)} disabled={type !== 'expense' || blocked} /></label><label><span>金額</span><input data-item-amount type="number" inputMode="numeric" min="1" max="999999999" aria-label={`品目${row.key}の金額（円）`} aria-describedby={`${prefix}items-error`} placeholder="0" value={row.amount} onChange={(event) => updateItem(row.key, 'amount', event.target.value)} disabled={type !== 'expense' || blocked} /></label><button className="remove-item" type="button" aria-label={`品目${row.key}を削除`} onClick={() => removeItem(row.key)} disabled={type !== 'expense' || blocked}>×</button></div>)}</div><small id={`${prefix}items-error`} className="field-error" role="status" hidden={!errors.itemRows}>{errors.itemRows}</small></div>
      </div>
      </fieldset>
      <p id={`${prefix}form-error`} className="field-error form-error" role="alert" hidden={!formError}>{formError}</p>
      {record?.timeEstimated && date === record.date && <p className="form-note">元の時刻は仮設定です。日時を変更すると入力時刻として保存します。</p>}
      <p className="form-note" id={`${prefix}form-note`}>入力した取引はこの端末のサーバーに保存されます。</p>
      <div className="dialog-actions"><button type="button" className="secondary-button close-dialog" onClick={onCancel} disabled={blocked}>キャンセル</button><button type="submit" className="primary-button" disabled={blocked}>{!record && <Icon name="plus" />}{submitting ? '保存中…' : record ? '保存する' : '追加する'}</button></div>
  </form>;
}
