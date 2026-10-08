import {receiptUrl as originalUrl,receiptPreviewUrl,snapshotTime} from '@kakei/runtime';
import PlaceSources from '../places/PlaceSources.jsx';
import MerchantAddressField from '../transactions/MerchantAddressField.jsx';
import React, { useState } from 'react';
import * as api from '../../lib/agent-api.js';
import AgentPlaces from './AgentPlaces.jsx';
import TrajectoryFields from '../trajectory/TrajectoryFields.jsx';
import TrajectoryDeletion from '../trajectory/TrajectoryDeletion.jsx';
import ReceiptReview from '../receipts/ReceiptReview.jsx';
import ReceiptCalculation from '../receipts/ReceiptCalculation.jsx';
const labels={title:'内容',date:'日時',type:'区分',category:'カテゴリ',amount:'金額',merchant:'店舗',merchantAddress:'取引先住所',paymentMethod:'支払方法',items:'品目',name:'名前',timeEstimated:'時刻は推定',events:'訪問',legs:'移動',placeId:'地点',time:'時刻',id:'識別子',transactionId:'関連取引',modeHint:'移動手段',from:'出発',to:'到着',coordinates:'座標',address:'住所',transportTransactionId:'交通費',viaPlaceIds:'経由地',timeEvidence:'時刻の根拠',timeEvidenceNote:'時刻の補足',modeEvidence:'移動手段の根拠',modeEvidenceNote:'移動の補足',placeEvidence:'地点の根拠',attribution:'出典',sourceUrl:'出典',receiptIds:'添付レシート',fromEventId:'出発する訪問',toEventId:'到着する訪問'};
const values={income:'収入',expense:'支出',cash:'現金',credit_card:'クレジットカード',e_money:'電子マネー',bank_account:'銀行口座',exact:'確定',estimated:'推定',unknown:'不明',legacy:'既存記録',inferred:'推定',fare:'交通費',user:'ユーザー指定',provider:'地点検索'};
export function RecordView({value,referenceLabels={}}) {
  if(value===null || value===undefined) return <span>なし</span>;
  if(Array.isArray(value)) return value.length ? <ol>{value.map((v,i)=><li key={i}><RecordView value={v} referenceLabels={referenceLabels}/></li>)}</ol> : <span>なし</span>;
  if(typeof value==='object'&&value.coordinateEvidence)return <><RecordView value={Object.fromEntries(Object.entries(value).filter(([k])=>!['coordinateEvidence','sources'].includes(k)))} referenceLabels={referenceLabels}/><PlaceSources {...value}/></>;
  if(typeof value==='object') return <dl className="agent-record">{Object.entries(value).filter(([key])=>key!=='id').map(([key,v])=><div key={key}><dt>{labels[key]||key}</dt><dd><RecordView value={v} referenceLabels={referenceLabels}/></dd></div>)}</dl>;
  return <span>{typeof value==='boolean'?(value?'はい':'いいえ'):referenceLabels[value]||values[value]||String(value)}</span>;
}
export function TransactionFields({command,index,onChange,hideLocation=false}) {
  const data=command.data;
  const set=(key,value)=>onChange({...command,data:{...data,[key]:value}});
  const input=(key,type='text')=><label>{labels[key]}<input aria-label={`${labels[key]} ${index+1}`} type={type} min={type==='number'?1:undefined} value={data[key]??''} onChange={e=>set(key,type==='number'&&e.target.value!==''?Number(e.target.value):e.target.value)} required /></label>;
  return <fieldset><legend>取引 {index+1}</legend>
    <div className="agent-fields">{input('title')}{input('date','datetime-local')}{input('amount','number')}
      <label>区分<select value={data.type} onChange={e=>set('type',e.target.value)}><option value="expense">支出</option><option value="income">収入</option></select></label>
      <label>カテゴリ<select value={data.category} onChange={e=>set('category',e.target.value)}>{['食費','住まい','日用品','交通','娯楽','その他','収入'].map(v=><option key={v}>{v}</option>)}</select></label>
      {data.type==='expense' && <>{!hideLocation&&<>{input('merchant')}<MerchantAddressField id={`agent-address-${index}`} value={data.merchantAddress} onChange={value=>set('merchantAddress',value || null)}/></>}<label>支払方法<select value={data.paymentMethod??''} onChange={e=>set('paymentMethod',e.target.value)}><option value="">選択してください</option>{['cash','credit_card','e_money','bank_account'].map(v=><option value={v} key={v}>{values[v]}</option>)}</select></label></>}
    </div>
    {data.type==='expense' && <div className="agent-items">{(data.items||[]).map((item,i)=><div className="agent-item" key={i}><label>品目名 {i+1}<input value={item.name} onChange={e=>set('items',data.items.map((v,n)=>n===i?{...v,name:e.target.value}:v))}/></label><label>品目金額 {i+1}<input type="number" required min="1" value={item.amount} onChange={e=>set('items',data.items.map((v,n)=>n===i?{...v,amount:e.target.value===''?'':Number(e.target.value)}:v))}/></label><button type="button" className="secondary-button" onClick={()=>set('items',data.items.filter((_,n)=>n!==i))}>品目 {i+1} を削除</button></div>)}<button className="secondary-button" type="button" onClick={()=>set('items',[...(data.items||[]),{name:'',amount:0}])}>品目を追加</button></div>}
    <label className="agent-checkbox"><input type="checkbox" checked={!!data.confirmTime} onChange={e=>set('confirmTime',e.target.checked)}/>時刻を確認しました</label>
  </fieldset>;
}
export default function AgentProposal({proposal,onChange,onCommitted,busy,setBusy,readOnly=false}) {
  const [reconfirming,setReconfirming]=useState(false);
  const [editing,setEditing]=useState(false), [draft,setDraft]=useState(proposal.commands), [error,setError]=useState('');
  const referenceLabels={...proposal.metadata?.referenceLabels};
  for (const group of proposal.metadata?.placeCandidates||[]) referenceLabels[group.placeId]=group.candidates.find(c=>c.id===group.selectedCandidateId)?.name || proposal.metadata?.authorizedPlaces?.[group.placeId]?.name || `${group.query}（地点未確定）`;
  for (const group of proposal.metadata?.placeCandidates||[]) if(group.selectedPlaceId)referenceLabels[group.selectedPlaceId]=referenceLabels[group.placeId];
  const placeLabels={...referenceLabels};
  for (const value of proposal.after) value?.events?.forEach((event,index)=>{referenceLabels[event.id]=`訪問 ${index+1}`;});
  const groups=proposal.metadata?.placeCandidates||[];
  const unresolved=groups.some(g=>!g.selectedCandidateId);
  const receipt=proposal.metadata?.receiptReview;
  const receiptUrl=receipt && originalUrl(receipt.receiptId,proposal.status==='applied'?undefined:proposal.threadId);
  const matches=receipt?.matches||[];
  const target=matches.find(m=>m.transaction.id===proposal.metadata?.targetChoice)?.transaction;
  const needsOrder=proposal.metadata?.orderRequired&&!proposal.metadata?.orderConfirmed;
  const pending=proposal.status==='pending' && proposal.expiresAt>(snapshotTime??Date.now()/1000);
  const hasDeletion=proposal.commands.some(command=>command.kind==='trajectory.delete');
  const deleteOnly=proposal.commands.every(command=>command.kind==='trajectory.delete');
  const act=async(fn)=>{if(busy)return;setBusy(true);setError('');try{await fn();}catch(e){setError(e.message||'操作できませんでした。再試行してください。');}finally{setBusy(false);}};
  const approve=()=>act(async()=>{await api.approve(proposal.id,proposal.revision);onChange({...proposal,status:'applied'});await onCommitted();});
  if(reconfirming&&receipt&&!readOnly)return <ReceiptReview key={proposal.id} review={receipt} proposal={editing?{...proposal,commands:draft}:proposal} threadId={proposal.threadId} busy={busy} setBusy={setBusy} onProposed={next=>{onChange(next);setDraft(next.commands);setEditing(false);setReconfirming(false);}}/>;
  return <article className="agent-proposal" aria-label="変更案">
    <header><h2>{pending?`確認待ち · 第${proposal.revision}版`:({applied:'保存済み',rejected:'却下済み'}[proposal.status]||'期限切れ')}</h2><p>{readOnly?'保存時点の変更案を表示しています。':<>内容を確認してから保存してください。{pending&&' この案は24時間で期限切れになります。'}</>}</p></header>
    {receipt&&['pending','applied'].includes(proposal.status)&&<section aria-label="レシートの根拠">
      <h3>レシートと保存先</h3>
      {receipt.mimeType?.startsWith('image/')&&<img className="receipt-preview" alt="確認するレシート" src={receiptPreviewUrl(receipt.receiptId,proposal.status==='applied'?undefined:proposal.threadId)}/>}
      <p><a href={receiptUrl} target="_blank" rel="noreferrer">レシート原本を開く</a></p>
      <p>保存先: {target?`${target.date} ${target.title} ${target.amount}円 を編集`:'新しい取引として追加'}</p>
      <ReceiptCalculation review={receipt} current={editing?draft[0]?.data:proposal.after[0]}/>
      {matches.length>0&&<details><summary>重複の可能性がある取引</summary><ul>{matches.map(m=><li key={m.transaction.id}>{m.reason==='hash'?'同じレシート':'近い取引'}: {m.transaction.date} {m.transaction.title} {m.transaction.amount}円</li>)}</ul></details>}
    </section>}
    {proposal.commands.map((command,i)=>command.kind==='trajectory.delete'?<TrajectoryDeletion key={i} command={command} before={proposal.before[i]} after={proposal.after[i]} referenceLabels={placeLabels}/>:<section className="agent-change" key={i}><h3>{command.kind.startsWith('transaction')?'取引':'軌跡'}の{command.kind.endsWith('create')?'追加':'変更'}</h3><div className="agent-diff"><div><h4>変更前</h4><RecordView value={proposal.before[i]} referenceLabels={referenceLabels}/></div><div><h4>変更後</h4><RecordView value={proposal.after[i]} referenceLabels={referenceLabels}/></div></div></section>)}
    {!readOnly&&pending&&groups.map(g=><AgentPlaces key={`${g.placeId}:${proposal.revision}`} group={g} proposal={proposal} act={act} onChange={onChange} busy={busy||editing}/>)}
    {!readOnly&&pending&&needsOrder&&<div className="agent-notice"><p>時刻が不明・推定の訪問が複数あります。表示順を確認し、必要なら「内容を修正」で並び替えてください。</p><button type="button" className="secondary-button" disabled={busy||editing} onClick={()=>act(async()=>onChange(await api.confirmOrder(proposal.id,proposal.revision)))}>この訪問順を確認した</button></div>}
    {!readOnly&&pending&&receipt&&<button type="button" className="secondary-button" disabled={busy} onClick={()=>setReconfirming(true)}>店舗・住所を再確認</button>}
    {error&&<div role="alert" className="agent-error">{error}<button type="button" className="secondary-button" disabled={busy} onClick={()=>act(async()=>{const latest=await api.getProposal(proposal.id);onChange(latest);setEditing(false);if(latest.status==='applied')await onCommitted();})}>変更案を再読み込み</button></div>}
    {!readOnly&&pending&&<>{editing?<form onSubmit={e=>{e.preventDefault();act(async()=>{onChange(await api.revise(proposal.id,proposal.revision,draft));setEditing(false);});}}>
      {draft.map((c,i)=>c.kind.startsWith('transaction')?<TransactionFields key={i} command={c} index={i} onChange={next=>setDraft(draft.map((v,n)=>n===i?next:v))}/>:<TrajectoryFields key={i} command={c} onChange={next=>setDraft(draft.map((v,n)=>n===i?next:v))}/>)}
      <div className="agent-actions"><button className="primary-button" disabled={busy}>差分を更新</button><button className="secondary-button" type="button" disabled={busy} onClick={()=>setEditing(false)}>修正をやめる</button></div>
    </form>:<div className="agent-actions"><button type="button" className="primary-button" disabled={busy||unresolved||needsOrder} onClick={approve}>{hasDeletion?(deleteOnly?'確認して削除':'削除を含む変更を保存'):'確認して保存'}</button><button type="button" className="secondary-button" disabled={busy} onClick={()=>{setDraft(structuredClone(proposal.commands));setEditing(true);}}>内容を修正</button><button type="button" className="secondary-button" disabled={busy} onClick={()=>act(async()=>onChange(await api.reject(proposal.id,proposal.revision)))}>却下</button></div>}</>}
  </article>;
}
