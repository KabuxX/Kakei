import {receiptUrl,receiptPreviewUrl} from '@kakei/runtime';
import {RecordView} from '../agent/AgentProposal.jsx';
import React,{useEffect,useRef,useState} from 'react';
import {TransactionFields} from '../agent/AgentProposal.jsx';
import * as api from '../../lib/agent-api.js';
import {normalizeMerchantAddress} from '../../lib/transaction-data.js';
import ReceiptLocation from './ReceiptLocation.jsx';
import useReceiptLocation from './useReceiptLocation.js';
import ReceiptCalculation from './ReceiptCalculation.jsx';
export default function ReceiptReview({review,threadId,busy,setBusy,onProposed,readOnly=false,proposal}){
 const candidate=review.candidate;
 const sourceInput=proposal?proposal.metadata?.receiptLocation?.input:review.locationResolution?.input;
 const proposalAddress=proposal?.commands?.[0]?.data?.merchantAddress;
 const googleBinding=['google_unique','google_selected','existing_google'].includes(proposal?.metadata?.receiptLocation?.method);
 const candidateAddress=normalizeMerchantAddress(proposal?(googleBinding&&proposalAddress===null?sourceInput?.merchantAddress:proposalAddress):sourceInput?sourceInput.merchantAddress:candidate.merchant_address);
 const prepared=review.preparedDraft;
 const [details,setDetails]=useState({branch:sourceInput?.branch??review.locationResolution?.input?.branch??null,locality:sourceInput?.locality??review.locationResolution?.input?.locality??null});
 const [verified,setVerified]=useState(false);
 const needsVerification=!!review.calculation?.issues?.length;
 const errorSummary=useRef(null);
 const [target,setTarget]=useState(proposal?.metadata?.targetChoice||''),[error,setError]=useState(''),[currency,setCurrency]=useState(candidate.currency||'');
 const [command,setCommand]=useState(proposal?.commands?.[0]||{kind:'transaction.create',identity:{},data:{title:candidate.merchant||'',merchant:sourceInput?.merchant??candidate.merchant??'',date:candidate.date&&candidate.time?`${candidate.date}T${candidate.time}`:'',amount:prepared?.amount??candidate.paid_total??candidate.total??'',type:'expense',category:'その他',paymentMethod:candidate.payment_method||'',items:prepared?.items||(candidate.items||[]).map(({name,amount})=>({name,amount}))}});
 const addressEdits=useRef({});
 const targetAddress=review.matches.find(m=>m.transaction.id===target)?.transaction.merchantAddress;
 const displayAddress=Object.hasOwn(addressEdits.current,target)?addressEdits.current[target]:candidateAddress??(proposal?null:targetAddress)??'';
 const locationInput={merchant:command.data.merchant,...details,merchantAddress:displayAddress||null};
 const location=useReceiptLocation({threadId,receiptId:review.receiptId,initialResolution:proposal?null:review.locationResolution,input:locationInput,target:review.matches.find(m=>m.transaction.id===target)?.transaction||target,readOnly});
 const displayCommand={...command,data:{...command.data,merchantAddress:displayAddress}};
 const changeCommand=next=>{
   if(next.data.merchantAddress!==displayAddress)addressEdits.current[target]=next.data.merchantAddress;
   const {merchantAddress,...data}=next.data;setCommand({...next,data});setVerified(false);
 };
 useEffect(()=>{if(error)errorSummary.current?.focus();},[error]);
 const mismatch=command.data.items?.length && (command.data.items.reduce((s,i)=>s+Number(i.amount),0)!==Number(command.data.amount)||command.data.items.some(i=>i.amount<=0));
 const invalidAmounts=[command.data.amount,...(command.data.items||[]).map(item=>item.amount)].some(amount=>!Number.isInteger(amount)||amount<=0);
 const url=receiptUrl(review.receiptId,threadId);
 const submit=async(e)=>{e.preventDefault();if(busy||invalidAmounts||mismatch||!location.resolved||(needsVerification&&!verified))return;setBusy(true);setError('');try{const draft={...command.data,merchantAddress:locationInput.merchantAddress};const binding={resolutionId:location.resolution.id,revision:location.resolution.revision,input:location.resolution.input};onProposed(proposal?await api.reconfirmReceiptProposal(proposal.id,{revision:proposal.revision,draft,location:binding}):await api.proposeReceipt(threadId,{receiptId:review.receiptId,target,currency,draft,location:binding}));}catch(e){setError(e.message);}finally{setBusy(false);}};
 if(readOnly)return <article className="agent-proposal receipt-review" aria-label="レシートの読み取り結果"><h2>レシートの読み取り結果</h2>{review.mimeType?.startsWith('image/')&&<img className="receipt-preview" alt="レシートのプレビュー" src={receiptPreviewUrl(review.receiptId,threadId)}/>}<p><a href={url} target="_blank" rel="noreferrer">レシート原本を開く</a></p><ReceiptCalculation review={review} current={command.data}/><RecordView value={candidate}/></article>;
 return <article className="agent-proposal receipt-review" aria-label="レシートの確認"><h2>レシートを確認</h2>
 {review.mimeType?.startsWith('image/')&&<img className="receipt-preview" alt="レシートのプレビュー" src={receiptPreviewUrl(review.receiptId,threadId)}/>}
 <p><a href={url} target="_blank" rel="noreferrer">レシート原本を開く</a></p>
 <ReceiptCalculation review={review} current={command.data}/>
 {review.missingFields.length>0&&<p className="agent-notice">読み取れない項目があります。原本を確認し、空欄を補ってください。</p>}
 {mismatch&&<p className="agent-notice">品目合計と合計金額が一致しません。品目を修正するか、品目を保存せずに進めてください。不明な税・値引は自動で補いません。</p>}
 {review.matches.length>0&&<p>同じ取引の可能性がある記録が見つかりました。保存先を選んでください。</p>}
 <form onSubmit={submit}><label>保存先<select aria-label="保存先" required value={target} onChange={e=>setTarget(e.target.value)} disabled={busy||!!proposal}><option value="">選択してください</option><option value="new">新しい取引として追加</option>{review.matches.map(m=><option key={m.transaction.id} value={m.transaction.id}>{m.reason==='hash'?'同じレシート':'近い取引'}: {m.transaction.date} {m.transaction.title} {m.transaction.amount}円 を編集</option>)}</select></label>
 <label>通貨<select value={currency} onChange={e=>setCurrency(e.target.value)} required><option value="">確認してください</option>{currency&&currency!=='JPY'&&<option>{currency}</option>}<option value="JPY">日本円（JPY）</option></select></label>
 <ReceiptLocation onSourceAddressChange={address=>{addressEdits.current[target]=address;setCommand(current=>({...current}));}} inheritedPlace={review.matches.find(m=>m.transaction.id===target)?.transaction.merchantPlace} location={location} input={locationInput} onInputChange={next=>{setDetails({branch:next.branch,locality:next.locality});addressEdits.current[target]=next.merchantAddress;setCommand(current=>({...current,data:{...current.data,merchant:next.merchant}}));}}/>
 <TransactionFields hideLocation command={displayCommand} index={0} onChange={changeCommand}/>
 {command.data.items.length>0&&<button type="button" className="secondary-button" onClick={()=>setCommand({...command,data:{...command.data,items:[]}})}>品目を保存しない</button>}
 {error&&<p ref={errorSummary} tabIndex="-1" role="alert" className="agent-error">{error}</p>}
 {needsVerification&&<label className="agent-checkbox"><input type="checkbox" checked={verified} onChange={e=>setVerified(e.target.checked)}/>原本と照合し、金額・品目を確認しました</label>}
 <button className="primary-button" disabled={busy||invalidAmounts||!location.resolved||!target||!!mismatch||currency!=='JPY'||(needsVerification&&!verified)}>変更案を確認</button>
 </form></article>;
}
