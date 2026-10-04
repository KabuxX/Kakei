import React from 'react';
const yen=value=>`${Number(value).toLocaleString('ja-JP')}円`;
const basis={exclusive:'税抜',inclusive:'税込',exempt:'非課税',unknown:'不明'};
export default function ReceiptCalculation({review,current}){
 const calc=review.calculation;
 if(!calc)return null;
 const prepared=review.preparedDraft;
 const changed=prepared&&current&&(Number(current.amount)!==prepared.amount||JSON.stringify((current.items||[]).map(({name,amount})=>({name,amount:Number(amount)})))!==JSON.stringify(prepared.items));
 return <section className="receipt-calculation" aria-label="税込金額の計算根拠">
  <h3>税込金額の計算根拠</h3>
  {calc.issues.length>0?<div className="agent-notice"><p>自動計算を保留しました。原本と照合して、保存する金額・品目を修正してください。</p><ul>{calc.issues.map((issue,i)=><li key={i}>{issue}</li>)}</ul></div>:<>
   <p className="receipt-totals">税込合計 <strong>{yen(calc.grossTotal)}</strong><span>還元・値引 −{yen(calc.discountTotal)}</span><span>実支払額 <strong>{yen(calc.paidTotal)}</strong></span></p>
   <p>印字された外税を同じ税区分の品目へ配分し、還元・値引を税込額に比例して配分しました。1円未満の端数は余りが大きい順、同じ場合は印字順に配分します。税込・非課税の品目には税を追加しません。</p>
   {changed&&<p className="agent-notice">金額・品目は自動計算後に変更されています。以下は読み取り時の計算根拠です。保存する内容は取引欄で確認してください。</p>}
   <details open><summary>品目ごとの計算</summary><ol className="receipt-calculation-items">{calc.rows.map((row,i)=><li key={i}>
    <div className="receipt-calculation-title"><strong>{row.name}</strong><span>{basis[row.basis]}{row.rate?` ${row.rate}%`:''}</span></div>
    <dl><div><dt>印字金額</dt><dd>{yen(row.printed)}</dd></div><div><dt>追加する税</dt><dd>+{yen(row.addedTax)}</dd></div><div><dt>税込金額</dt><dd>{yen(row.gross)}</dd></div><div><dt>還元・値引</dt><dd>−{yen(row.discount)}</dd></div><div><dt>記録額</dt><dd><strong>{yen(row.net)}</strong></dd></div></dl>
   </li>)}</ol></details>
  </>}
  <details><summary>読み取った小計・税額</summary><ul>{(review.candidate.tax_groups||[]).map((group,i)=><li key={i}>{basis[group.basis]} {group.rate!=null?`${group.rate}%`:''}：小計 {group.subtotal!=null?yen(group.subtotal):'不明'} ／ {group.basis==='inclusive'?'内税':'税額'} {group.tax!=null?yen(group.tax):'個別の印字なし・不明'}</li>)}</ul></details>
 </section>;
}
