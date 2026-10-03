import React, { useEffect, useRef, useState } from 'react';
import MerchantAddressField from './MerchantAddressField.jsx';
import { Icon } from './AppShell.jsx';
import { categories } from './lib/dashboard.js';
import { ApiError } from './lib/api.js';
import { parseExpenseDraft, ValidationError } from './lib/transaction-data.js';
import { dateTimeLocalValue, isValidTransactionDateTime } from './lib/transaction-datetime.js';

const maxAmount = 999999999;
const fieldIds = { title: 'title-input', amount: 'amount-input', date: 'date-input', merchant: 'merchant-input', merchantAddress: 'merchant-address-input', paymentMethod: 'payment-method-input', itemRows: 'item-rows' };

export default function TransactionDialog({ open, selectedMonth, busy, onClose, onSubmit }) {
  const dialog = useRef(null);
  const sequence = useRef(0);
  const [type, setType] = useState('expense');
  const [title, setTitle] = useState('');
  const [manualAmount, setManualAmount] = useState('');
  const [date, setDate] = useState(dateTimeLocalValue);
  const [category, setCategory] = useState(categories[0].name);
  const [merchantAddress, setMerchantAddress] = useState('');
  const [merchant, setMerchant] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('');
  const [itemRows, setItemRows] = useState([]);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const blocked = busy || submitting;
  const itemized = type === 'expense' && itemRows.length > 0;
  const validItems = itemRows.every((row) => row.name.trim() && /^\d+$/.test(row.amount.trim()) && Number(row.amount) > 0);
  const itemTotal = itemRows.reduce((sum, row) => sum + Number(row.amount), 0);
  const amount = itemized ? validItems && itemTotal <= maxAmount ? String(itemTotal) : '' : manualAmount;

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) {
      setType('expense'); setTitle(''); setManualAmount(''); setDate(dateTimeLocalValue());
      setCategory(categories[0].name); setMerchant(''); setMerchantAddress(''); setPaymentMethod(''); setItemRows([]);
      setErrors({}); setFormError(''); sequence.current = 0;
      if (element.showModal) element.showModal();
      else element.setAttribute('open', '');
      element.querySelector('[name="title"]')?.focus();
    } else if (!open && element.open) {
      if (element.close) element.close();
      else element.removeAttribute('open');
    }
  }, [open, selectedMonth]);

  const showError = (field, message) => {
    setErrors((current) => ({ ...current, [field]: message }));
    let selector = `#${fieldIds[field]}`;
    if (field === 'itemRows') {
      const row = itemRows.find((item) => !item.name.trim() || !/^\d+$/.test(item.amount.trim()) || Number(item.amount) < 1 || Number(item.amount) > maxAmount) || itemRows.at(-1);
      selector = row ? `[data-item-key="${row.key}"] ${row.name.trim() ? '[data-item-amount]' : '[data-item-name]'}` : '#add-item';
    }
    dialog.current?.querySelector(selector)?.focus();
  };
  const changeType = (next) => { setType(next); setCategory(next === 'income' ? '収入' : categories[0].name); setErrors({}); };
  const addItem = () => {
    sequence.current += 1;
    const key = sequence.current;
    setItemRows((current) => [...current, { key, name: '', amount: '' }]);
    requestAnimationFrame(() => dialog.current?.querySelector(`[data-item-key="${key}"] [data-item-name]`)?.focus());
  };
  const updateItem = (key, field, value) => {
    setItemRows((current) => current.map((row) => row.key === key ? { ...row, [field]: value } : row));
    setErrors((current) => ({ ...current, itemRows: '' }));
  };
  const removeItem = (key) => {
    setItemRows((current) => current.filter((row) => row.key !== key));
    dialog.current?.querySelector('#add-item')?.focus();
  };

  const submit = async (event) => {
    event.preventDefault();
    if (blocked) return;
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
    setSubmitting(true);
    try {
      await onSubmit({ title: cleanTitle, amount: parsedAmount, date, type, category, ...details });
      onClose();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 400 && ['title', 'date', 'amount', 'merchant', 'merchantAddress', 'paymentMethod', 'items'].includes(cause.field)) {
        showError(cause.field === 'items' ? 'itemRows' : cause.field, cause.message);
      } else {
        setFormError('保存できませんでした。サーバーへの接続を確認して再試行してください。');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return <dialog ref={dialog} id="transaction-dialog" className="transaction-dialog" aria-labelledby="dialog-title" onClick={(event) => { if (!blocked && event.target === event.currentTarget) onClose(); }} onCancel={(event) => { event.preventDefault(); if (!blocked) onClose(); }}>
    <form id="transaction-form" noValidate onSubmit={submit}>
      <div className="dialog-head"><h2 id="dialog-title">取引を追加</h2><button type="button" className="icon-button close-dialog" aria-label="閉じる" onClick={onClose} disabled={blocked}><Icon name="close" /></button></div>
      <div className="type-tabs" role="group" aria-label="取引の種類"><label><input type="radio" name="type" value="expense" checked={type === 'expense'} onChange={() => changeType('expense')} /><span>支出</span></label><label><input type="radio" name="type" value="income" checked={type === 'income'} onChange={() => changeType('income')} /><span>収入</span></label></div>
      <div className="form-grid">
        <label className="field full"><span>内容 <em>必須</em></span><input id="title-input" name="title" type="text" maxLength="60" placeholder="例：スーパーで買い物" aria-describedby="title-error" aria-invalid={!!errors.title || undefined} required value={title} onChange={(event) => setTitle(event.target.value)} /><small id="title-error" className="field-error" hidden={!errors.title}>{errors.title}</small></label>
        <label className="field"><span>金額 <em>必須</em></span><span className="yen-input"><b>¥</b><input id="amount-input" name="amount" type="number" inputMode="numeric" min="1" max="999999999" placeholder="0" aria-describedby="amount-error" aria-invalid={!!errors.amount || undefined} required={!itemized} readOnly={itemized} value={amount} onChange={(event) => setManualAmount(event.target.value)} /></span><small id="amount-error" className="field-error" hidden={!errors.amount}>{errors.amount}</small></label>
        <label className="field"><span>日付と時刻 <em>必須</em></span><input id="date-input" name="date" type="datetime-local" step="60" aria-describedby="date-error" aria-invalid={!!errors.date || undefined} required value={date} onChange={(event) => setDate(event.target.value)} /><small id="date-error" className="field-error" hidden={!errors.date}>{errors.date}</small></label>
        <label className="field full"><span>カテゴリ</span><select id="category-input" name="category" value={category} onChange={(event) => setCategory(event.target.value)}>{(type === 'income' ? ['収入'] : categories.map((item) => item.name)).map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
      </div>
      <div id="expense-fields" className="expense-fields" hidden={type !== 'expense'}>
        <div className="form-grid"><label className="field full"><span>店名・取引先 <em>必須</em></span><input id="merchant-input" name="merchant" type="text" maxLength="60" placeholder="例：スーパー○○" aria-describedby="merchant-error" aria-invalid={!!errors.merchant || undefined} required={type === 'expense'} disabled={type !== 'expense'} value={merchant} onChange={(event) => setMerchant(event.target.value)} /><small id="merchant-error" className="field-error" hidden={!errors.merchant}>{errors.merchant}</small></label><label className="field full"><span>支払方法 <em>必須</em></span><select id="payment-method-input" name="paymentMethod" aria-describedby="payment-method-error" aria-invalid={!!errors.paymentMethod || undefined} required={type === 'expense'} disabled={type !== 'expense'} value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}><option value="">選択してください</option><option value="cash">現金</option><option value="credit_card">クレジットカード</option><option value="e_money">電子マネー</option><option value="bank_account">銀行口座</option></select><small id="payment-method-error" className="field-error" hidden={!errors.paymentMethod}>{errors.paymentMethod}</small></label></div>
        <MerchantAddressField id="merchant-address-input" value={merchantAddress} onChange={setMerchantAddress} error={errors.merchantAddress} disabled={type !== 'expense' || blocked}/>
        <div className="item-section" aria-labelledby="item-section-title"><div className="item-section-head"><strong id="item-section-title">品目 <span>任意</span></strong><button id="add-item" type="button" className="item-add" onClick={addItem} disabled={type !== 'expense'}>＋ 品目を追加</button></div><div id="item-rows" className="item-rows">{itemRows.map((row) => <div className="item-row" key={row.key} data-item-key={row.key}><label><span>品目名</span><input data-item-name type="text" maxLength="60" aria-label={`品目${row.key}の名前`} aria-describedby="items-error" placeholder="例：パン" value={row.name} onChange={(event) => updateItem(row.key, 'name', event.target.value)} disabled={type !== 'expense'} /></label><label><span>金額</span><input data-item-amount type="number" inputMode="numeric" min="1" max="999999999" aria-label={`品目${row.key}の金額（円）`} aria-describedby="items-error" placeholder="0" value={row.amount} onChange={(event) => updateItem(row.key, 'amount', event.target.value)} disabled={type !== 'expense'} /></label><button className="remove-item" type="button" aria-label={`品目${row.key}を削除`} onClick={() => removeItem(row.key)} disabled={type !== 'expense'}>×</button></div>)}</div><small id="items-error" className="field-error" role="status" hidden={!errors.itemRows}>{errors.itemRows}</small></div>
      </div>
      <p id="form-error" className="field-error form-error" role="alert" hidden={!formError}>{formError}</p>
      <p className="form-note" id="form-note">入力した取引はこの端末のサーバーに保存されます。</p>
      <div className="dialog-actions"><button type="button" className="secondary-button close-dialog" onClick={onClose} disabled={blocked}>キャンセル</button><button type="submit" className="primary-button" disabled={blocked}><Icon name="plus" />追加する</button></div>
    </form>
  </dialog>;
}
