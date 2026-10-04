import React from 'react';
import { yen } from '../lib/dashboard.js';
import { detailHref } from '../lib/transaction-detail.js';

export default function TransactionDelete({ record, busy = false, error, onConfirm }) {
  return <section id="delete-view" className="detail-view delete-view" aria-labelledby="delete-heading">
    <h1 id="delete-heading" tabIndex="-1">{record ? 'この取引を削除しますか？' : '取引が見つかりません'}</h1>
    {record ? <>
      <p id="delete-warning" className="delete-warning">削除後は元に戻せません。内容を確認してください。</p>
      <p>紐づくレシート原本も削除されます。軌跡の訪問記録は残りますが、この取引の購入・交通費の参照と、それを根拠にした移動手段は外れます。</p>
      <article className="delete-summary" aria-label="削除する取引">
        <span className="delete-summary-label">削除する取引</span>
        <h2>{record.title}</h2>
        <strong className="delete-summary-amount">{record.type === 'income' ? '+' : '−'}{yen(record.amount)}</strong>
        <p>{record.type === 'income' ? '収入' : '支出'} · {record.date.slice(0, 4)}年{Number(record.date.slice(5, 7))}月{Number(record.date.slice(8, 10))}日</p>
      </article>
      {error && <p className="delete-error" role="alert">{error}</p>}
      <div className="delete-actions">
        <a className="secondary-button" href={detailHref(record.id)} aria-disabled={busy || undefined} onClick={(event) => { if (busy) event.preventDefault(); }}>取引詳細へ戻る</a>
        <button className="delete-confirm" type="button" onClick={() => onConfirm(record)} disabled={busy} aria-describedby="delete-warning">{busy ? '削除中…' : '削除する'}</button>
      </div>
    </> : <div className="detail-missing"><p>削除されたか、URLが正しくない可能性があります。</p><a className="detail-back" href="#transactions">取引履歴へ戻る</a></div>}
  </section>;
}
