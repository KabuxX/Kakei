import React,{useEffect,useState} from 'react';
import {listTransactionReceipts} from '../../lib/agent-api.js';
export default function TransactionReceipts({transactionId}){
 const [receipts,setReceipts]=useState([]),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
 useEffect(()=>{let active=true;setReceipts([]);setError('');listTransactionReceipts(transactionId).then(values=>{if(active)setReceipts(values);}).catch(()=>{if(active)setError('レシートを読み込めませんでした。');});return()=>{active=false;};},[transactionId,attempt]);
 return <section className="detail-items-section" aria-label="保存したレシート"><h3>レシート</h3>{error?<p role="alert">{error}<button className="secondary-button" type="button" onClick={()=>setAttempt(v=>v+1)}>再試行</button></p>:receipts.length?<ul>{receipts.map((r,i)=><li key={r.id}><a href={`/api/receipts/${encodeURIComponent(r.id)}`} target="_blank" rel="noreferrer">レシート {i+1} を開く</a></li>)}</ul>:<p>添付はありません。</p>}</section>;
}
