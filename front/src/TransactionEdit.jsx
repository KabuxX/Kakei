import React from 'react';
import {Icon} from './AppShell.jsx';
import TransactionForm from './TransactionForm.jsx';
import {detailHref} from './lib/transaction-detail.js';
export default function TransactionEdit({record,busy,saveDisabled,onSubmit,onCancel}) {
 return <section className="detail-view edit-view" aria-labelledby="edit-heading">
  <a className="detail-back" href={record ? detailHref(record.id) : '#transactions'} aria-disabled={busy||undefined} onClick={e=>{e.preventDefault();if(!busy)onCancel();}}><Icon name="chevron"/>{record?'取引詳細へ戻る':'取引履歴へ戻る'}</a>
  <h1 id="edit-heading" tabIndex="-1">{record?'取引を編集':'取引が見つかりません'}</h1>
  {record ? <div className="edit-form-card"><TransactionForm key={record.id} record={record} prefix="edit-" busy={busy} saveDisabled={saveDisabled} onCancel={onCancel} onSubmit={onSubmit} onSaved={onCancel}/></div> : <p>削除されたか、URLが正しくない可能性があります。</p>}
 </section>;
}
