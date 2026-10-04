import React, {useEffect, useRef, useState} from 'react';
import {Icon} from '../layout/AppShell.jsx';
import {CATEGORY_NAMES, parseBudgetFields, sumBudget} from '../../lib/budget.js';
import {yen} from '../../lib/dashboard.js';

export default function BudgetDialog({open, categories, busy = false, onClose, onSubmit}) {
  const dialog = useRef(null);
  const lock = useRef(false);
  const [fields, setFields] = useState({});
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const disabled = busy || submitting;
  const parsed = parseBudgetFields(fields);

  useEffect(() => {
    const element = dialog.current;
    if (open) {
      setFields(Object.fromEntries(CATEGORY_NAMES.map(name => [name, String(categories[name])])));
      setErrors({});
      setMessage('');
      if (!element.open) {
        if (element.showModal) element.showModal(); else element.setAttribute('open', '');
      }
      element.querySelector('input')?.focus();
    } else if (element.open) {
      if (element.close) element.close(); else element.removeAttribute('open');
    }
  }, [open, categories]);

  const close = () => {if (!busy && !lock.current) onClose();};
  const submit = async event => {
    event.preventDefault();
    if (disabled || lock.current) return;
    const result = parseBudgetFields(fields);
    setErrors(result.errors);
    setMessage('');
    if (!result.categories) {
      setMessage('入力を確認してください。');
      dialog.current.querySelector(`[name="${Object.keys(result.errors)[0]}"]`)?.focus();
      return;
    }
    lock.current = true;
    setSubmitting(true);
    try {
      await onSubmit(result.categories);
      onClose();
    } catch (cause) {
      const name = cause.field?.replace(/^categories\./, '');
      if (CATEGORY_NAMES.includes(name)) setErrors({[name]: cause.message});
      setMessage(`保存できませんでした。${cause.message || '接続を確認してください。'} 内容を確認して、もう一度保存してください。`);
    } finally {
      lock.current = false;
      setSubmitting(false);
    }
  };

  return <dialog ref={dialog} className="transaction-dialog budget-dialog" aria-labelledby="budget-dialog-title" aria-describedby="budget-dialog-description"
    onCancel={event => {event.preventDefault(); close();}}
    onClick={event => {if (event.target === event.currentTarget) close();}}>
    <div className="dialog-head"><h2 id="budget-dialog-title">予算を設定</h2><button type="button" className="icon-button" aria-label="閉じる" onClick={close} disabled={disabled}><Icon name="close"/></button></div>
    {open && <form onSubmit={submit} noValidate aria-busy={disabled}>
      <p id="budget-dialog-description" className="budget-description">毎月共通の予算です。変更はすべての月に適用されます。</p>
      {message && <p className="budget-error" role="alert">{message}</p>}
      <div className="form-grid budget-fields">{CATEGORY_NAMES.map((name, index) => {
        const id = `budget-input-${index}`, errorId = `${id}-error`;
        return <div className="field" key={name}>
          <label htmlFor={id}>{name}（円）</label>
          <div className="yen-input"><b aria-hidden="true">¥</b><input id={id} name={name} inputMode="numeric" autoComplete="off" required disabled={disabled}
            value={fields[name] ?? ''} aria-invalid={errors[name] ? true : undefined} aria-describedby={errors[name] ? errorId : undefined}
            onChange={event => setFields(previous => ({...previous, [name]: event.target.value}))}
            onBlur={() => setErrors(previous => ({...previous, [name]: parseBudgetFields(fields).errors[name]}))}/></div>
          {errors[name] && <small id={errorId} className="budget-field-error">{errors[name]}</small>}
        </div>;
      })}</div>
      <div className="budget-total"><span>月の予算</span><output aria-live="polite">{parsed.categories ? yen(sumBudget(parsed.categories)) : '—'}</output></div>
      <div className="dialog-actions"><button type="button" className="secondary-button" disabled={disabled} onClick={close}>キャンセル</button><button type="submit" className="primary-button" disabled={disabled}>{disabled ? '保存中…' : '保存'}</button></div>
    </form>}
  </dialog>;
}
