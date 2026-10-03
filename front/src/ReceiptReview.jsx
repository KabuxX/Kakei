import React,{useState} from 'react';
import {TransactionFields} from './AgentProposal.jsx';
import * as api from './lib/agent-api.js';
export default function ReceiptReview({review,threadId,busy,setBusy,onProposed}){
 const candidate=review.candidate;
 const [target,setTarget]=useState(''),[error,setError]=useState(''),[currency,setCurrency]=useState(candidate.currency||'');
 const [command,setCommand]=useState({kind:'transaction.create',identity:{},data:{title:candidate.merchant||'',merchant:candidate.merchant||'',date:candidate.date&&candidate.time?`${candidate.date}T${candidate.time}`:'',amount:candidate.total??'',type:'expense',category:'その他',paymentMethod:candidate.payment_method||'',items:candidate.items||[]}});
 const mismatch=command.data.items?.length && (command.data.items.reduce((s,i)=>s+Number(i.amount),0)!==Number(command.data.amount)||command.data.items.some(i=>i.amount<=0));
 const url=`/api/agent/threads/${encodeURIComponent(threadId)}/receipts/${encodeURIComponent(review.receiptId)}`;
 const submit=async(e)=>{e.preventDefault();if(busy)return;setBusy(true);setError('');try{onProposed(await api.proposeReceipt(threadId,{receiptId:review.receiptId,target,currency,draft:command.data}));}catch(e){setError(e.message);}finally{setBusy(false);}};
 return <article className="agent-proposal receipt-review" aria-label="レシートの確認"><h2>レシートを確認</h2>
 {review.mimeType?.startsWith('image/')&&<img className="receipt-preview" alt="レシートのプレビュー" src={url}/>}
 <p><a href={url} target="_blank" rel="noreferrer">レシート原本を開く</a></p>
 {review.missingFields.length>0&&<p className="agent-notice">読み取れない項目があります。原本を確認し、空欄を補ってください。</p>}
 {mismatch&&<p className="agent-notice">品目合計と合計金額が一致しません。品目を修正するか、品目を保存せずに進めてください。税・値引を自動で補いません。</p>}
 {review.matches.length>0&&<p>同じ取引の可能性がある記録が見つかりました。保存先を選んでください。</p>}
 <form onSubmit={submit}><label>保存先<select aria-label="保存先" required value={target} onChange={e=>setTarget(e.target.value)} disabled={busy}><option value="">選択してください</option><option value="new">新しい取引として追加</option>{review.matches.map(m=><option key={m.transaction.id} value={m.transaction.id}>{m.reason==='hash'?'同じレシート':'近い取引'}: {m.transaction.date} {m.transaction.title} {m.transaction.amount}円 を編集</option>)}</select></label>
 <label>通貨<select value={currency} onChange={e=>setCurrency(e.target.value)} required><option value="">確認してください</option>{currency&&currency!=='JPY'&&<option>{currency}</option>}<option value="JPY">日本円（JPY）</option></select></label>
 <TransactionFields command={command} index={0} onChange={setCommand}/>
 {command.data.items.length>0&&<button type="button" className="secondary-button" onClick={()=>setCommand({...command,data:{...command.data,items:[]}})}>品目を保存しない</button>}
 {error&&<p role="alert" className="agent-error">{error}</p>}
 <button className="primary-button" disabled={busy||!target||!!mismatch||currency!=='JPY'}>変更案を確認</button>
 </form></article>;
}
