import React from 'react';
import { Icon } from './AppShell.jsx';
import { PAYMENT_METHOD_LABELS, readExpenseDetails } from './lib/transaction-data.js';
import { yen } from './lib/dashboard.js';

export default function TransactionDetail({ record, onDelete, busy = false, onBack }) {
  const expense = record?.type === 'expense';
  const details = readExpenseDetails(record);
  return <section id="detail-view" className="detail-view" aria-labelledby="detail-heading">
    <a id="detail-back" className="detail-back" href="#transactions" onClick={onBack}><Icon name="chevron" />取引履歴へ戻る</a>
    <h1 id="detail-heading" tabIndex="-1">取引詳細</h1>
    {record ? <div id="detail-present">
      <article className="detail-hero" aria-labelledby="detail-title"><div className="detail-hero-top"><span id="detail-type" className={`detail-type${record.type === 'income' ? ' income' : ''}`}>{record.type === 'income' ? '収入' : '支出'}</span><span id="detail-sample" className="detail-sample" hidden={!record.id.startsWith('sample-')}>サンプルデータ</span></div><strong id="detail-amount" className="detail-amount">{record.type === 'income' ? '+' : '−'}{yen(record.amount)}</strong><h2 id="detail-title">{record.title}</h2></article>
      <dl className="detail-fields"><div><dt>日付</dt><dd id="detail-date">{record.date.slice(0, 4)}年{Number(record.date.slice(5, 7))}月{Number(record.date.slice(8, 10))}日</dd></div><div><dt>カテゴリ</dt><dd id="detail-category">{record.category}</dd></div></dl>
      {expense && <div id="detail-expense-fields"><dl className="detail-fields"><div><dt>店名・取引先</dt><dd id="detail-merchant">{details.merchant || '未登録'}</dd></div><div><dt>支払方法</dt><dd id="detail-payment-method">{PAYMENT_METHOD_LABELS[details.paymentMethod] || '未登録'}</dd></div></dl><section className="detail-items-section" aria-labelledby="detail-items-heading"><h3 id="detail-items-heading">品目</h3><div id="detail-items">{details.items.length ? <ul className="detail-item-list">{details.items.map((item, index) => <li key={index}><span>{item.name}</span><strong>{yen(item.amount)}</strong></li>)}</ul> : <p className="detail-item-empty">品目は登録されていません</p>}</div></section></div>}
      <div className="detail-danger"><button id="detail-delete" type="button" onClick={() => onDelete(record)} disabled={busy}><Icon name="trash" />取引を削除</button></div>
    </div> : <div id="detail-missing" className="detail-missing"><h2>取引が見つかりません</h2><p>削除されたか、URLが正しくない可能性があります。</p></div>}
  </section>;
}
