import React, { useState } from 'react';
import * as api from './lib/agent-api.js';
const labels={title:'内容',date:'日時',type:'区分',category:'カテゴリ',amount:'金額',merchant:'店舗',paymentMethod:'支払方法',items:'品目',name:'名前',timeEstimated:'時刻は推定',events:'訪問',legs:'移動',placeId:'地点',time:'時刻',id:'識別子',transactionId:'関連取引',modeHint:'移動手段',from:'出発',to:'到着',coordinates:'座標',address:'住所',transportTransactionId:'交通費',viaPlaceIds:'経由地',timeEvidence:'時刻の根拠',timeEvidenceNote:'時刻の補足',modeEvidence:'移動手段の根拠',modeEvidenceNote:'移動の補足',placeEvidence:'地点の根拠',attribution:'出典',sourceURL:'参照先'};
const values={income:'収入',expense:'支出',cash:'現金',credit_card:'クレジットカード',e_money:'電子マネー',bank_account:'銀行口座',exact:'確定',estimated:'推定',unknown:'不明',legacy:'既存記録',inferred:'推定',fare:'交通費',user:'ユーザー指定',provider:'地点検索'};
export function RecordView({value}) {
  if(value===null || value===undefined) return <span>なし</span>;
  if(Array.isArray(value)) return value.length ? <ol>{value.map((v,i)=><li key={i}><RecordView value={v}/></li>)}</ol> : <span>なし</span>;
  if(typeof value==='object') return <dl className="agent-record">{Object.entries(value).filter(([key])=>key!=='id').map(([key,v])=><div key={key}><dt>{labels[key]||key}</dt><dd><RecordView value={v}/></dd></div>)}</dl>;
  return <span>{typeof value==='boolean'?(value?'はい':'いいえ'):values[value]||String(value)}</span>;
}
export function TransactionFields({command,index,onChange}) {
  const data=command.data;
  const set=(key,value)=>onChange({...command,data:{...data,[key]:value}});
  const input=(key,type='text')=><label>{labels[key]}<input aria-label={`${labels[key]} ${index+1}`} type={type} value={data[key]??''} onChange={e=>set(key,type==='number'?Number(e.target.value):e.target.value)} required /></label>;
  return <fieldset><legend>取引 {index+1}</legend>
    <div className="agent-fields">{input('title')}{input('date','datetime-local')}{input('amount','number')}
      <label>区分<select value={data.type} onChange={e=>set('type',e.target.value)}><option value="expense">支出</option><option value="income">収入</option></select></label>
      <label>カテゴリ<select value={data.category} onChange={e=>set('category',e.target.value)}>{['食費','住まい','日用品','交通','娯楽','その他','収入'].map(v=><option key={v}>{v}</option>)}</select></label>
      {data.type==='expense' && <>{input('merchant')}<label>支払方法<select value={data.paymentMethod??''} onChange={e=>set('paymentMethod',e.target.value)}><option value="">選択してください</option>{['cash','credit_card','e_money','bank_account'].map(v=><option value={v} key={v}>{values[v]}</option>)}</select></label></>}
    </div>
    {data.type==='expense' && <div className="agent-items">{(data.items||[]).map((item,i)=><div className="agent-item" key={i}><label>品目名 {i+1}<input value={item.name} onChange={e=>set('items',data.items.map((v,n)=>n===i?{...v,name:e.target.value}:v))}/></label><label>品目金額 {i+1}<input type="number" value={item.amount} onChange={e=>set('items',data.items.map((v,n)=>n===i?{...v,amount:Number(e.target.value)}:v))}/></label><button type="button" className="secondary-button" onClick={()=>set('items',data.items.filter((_,n)=>n!==i))}>品目 {i+1} を削除</button></div>)}<button className="secondary-button" type="button" onClick={()=>set('items',[...(data.items||[]),{name:'',amount:0}])}>品目を追加</button></div>}
    <label className="agent-checkbox"><input type="checkbox" checked={!!data.confirmTime} onChange={e=>set('confirmTime',e.target.checked)}/>時刻を確認しました</label>
  </fieldset>;
}
export default function AgentProposal({proposal,onChange,onCommitted,busy,setBusy}) {
  const [editing,setEditing]=useState(false), [draft,setDraft]=useState(proposal.commands), [error,setError]=useState('');
  const pending=proposal.status==='pending' && proposal.expiresAt>Date.now()/1000;
  const act=async(fn)=>{if(busy)return;setBusy(true);setError('');try{await fn();}catch(e){setError(e.message||'操作できませんでした。再試行してください。');}finally{setBusy(false);}};
  const approve=()=>act(async()=>{await api.approve(proposal.id,proposal.revision);onChange({...proposal,status:'applied'});await onCommitted();});
  return <article className="agent-proposal" aria-label="変更案">
    <header><h2>{pending?`確認待ち · 第${proposal.revision}版`:({applied:'保存済み',rejected:'却下済み'}[proposal.status]||'期限切れ')}</h2><p>内容を確認してから保存してください。{pending&&' この案は24時間で期限切れになります。'}</p></header>
    {proposal.commands.map((command,i)=><section className="agent-change" key={i}><h3>{command.kind.startsWith('transaction')?'取引':'軌跡'}の{command.kind.endsWith('create')?'追加':'変更'}</h3><div className="agent-diff"><div><h4>変更前</h4><RecordView value={proposal.before[i]}/></div><div><h4>変更後</h4><RecordView value={proposal.after[i]}/></div></div></section>)}
    {error&&<p role="alert" className="agent-error">{error}</p>}
    {pending&&<>{editing?<form onSubmit={e=>{e.preventDefault();act(async()=>{onChange(await api.revise(proposal.id,proposal.revision,draft));setEditing(false);});}}>
      {draft.map((c,i)=>c.kind.startsWith('transaction')?<TransactionFields key={i} command={c} index={i} onChange={next=>setDraft(draft.map((v,n)=>n===i?next:v))}/>:<p key={i}>軌跡の修正内容をメッセージで伝えてください。</p>)}
      <div className="agent-actions"><button className="primary-button" disabled={busy}>差分を更新</button><button className="secondary-button" type="button" disabled={busy} onClick={()=>setEditing(false)}>修正をやめる</button></div>
    </form>:<div className="agent-actions"><button type="button" className="primary-button" disabled={busy} onClick={approve}>確認して保存</button><button type="button" className="secondary-button" disabled={busy} onClick={()=>{setDraft(structuredClone(proposal.commands));setEditing(true);}}>内容を修正</button><button type="button" className="secondary-button" disabled={busy} onClick={()=>act(async()=>onChange(await api.reject(proposal.id,proposal.revision)))}>却下</button></div>}</>}
  </article>;
}
