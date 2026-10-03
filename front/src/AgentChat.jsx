import React, { useEffect, useRef, useState } from 'react';
import * as api from './lib/agent-api.js';
import AgentProposal from './AgentProposal.jsx';

export default function AgentChat({onCommitted}) {
  const [status,setStatus]=useState(null), [threads,setThreads]=useState([]), [thread,setThread]=useState(null);
  const [text,setText]=useState(''), [busy,setBusy]=useState(false), [loading,setLoading]=useState(true), [error,setError]=useState('');
  const retry=useRef(null), composer=useRef(null);
  const load=async()=>{setLoading(true);setError('');try{const [s,t]=await Promise.all([api.status(),api.listThreads()]);setStatus(s);setThreads(t);}catch(e){setError(e.message);}finally{setLoading(false);}};
  useEffect(()=>{load();},[]);
  const act=async(fn)=>{if(busy)return;setBusy(true);setError('');try{await fn();}catch(e){setError(e.message||'通信できませんでした。再送できます。');}finally{setBusy(false);}};
  const send=async(e)=>{e.preventDefault();if(!text.trim()||!status?.available)return;await act(async()=>{
    const current=thread||await api.createThread(); if(!thread)setThread({...current,messages:[],proposals:[]});
    const body=retry.current?.text===text?retry.current:{clientMessageId:crypto.randomUUID(),text};retry.current=body;
    await api.sendMessage(current.id,body);retry.current=null;setText('');
    setThread(await api.getThread(current.id));setThreads(await api.listThreads());composer.current?.focus();
  });};
  const select=(id)=>act(async()=>{setThread(id?await api.getThread(id):null);retry.current=null;setText('');});
  const change=(proposal)=>setThread(current=>({...current,proposals:current.proposals.map(p=>p.id===proposal.id?proposal:p)}));
  return <section className="agent-page" aria-labelledby="agent-heading">
    <div className="agent-heading"><div><p className="eyebrow">家計のアシスタント</p><h1 id="agent-heading" tabIndex="-1">Agent Chat</h1><p>取引の記録や、一日の軌跡づくりを相談できます。</p></div><span className="agent-status" role="status">{loading?'接続を確認中':status?.available?'利用できます':'設定が必要です'}</span></div>
    {error&&<div role="alert" className="agent-error">{error}<button type="button" className="secondary-button" onClick={load} disabled={busy}>状態を再読み込み</button></div>}
    {!loading&&status&&!status.available&&<p className="agent-notice">{status.message}</p>}
    {!loading&&<><div className="agent-threadbar"><label>会話<select aria-label="会話" value={thread?.id||''} disabled={busy} onChange={e=>select(e.target.value)}><option value="">新しい会話</option>{threads.map(t=><option value={t.id} key={t.id}>{t.title}</option>)}{thread&&!threads.some(t=>t.id===thread.id)&&<option value={thread.id}>{thread.title}</option>}</select></label><button type="button" className="secondary-button" disabled={busy} onClick={()=>select('')}>新しい会話</button>{thread&&<button type="button" className="secondary-button" disabled={busy} onClick={()=>{if(window.confirm('会話と未保存の変更案を削除しますか？ 保存済みの取引は残ります。'))act(async()=>{await api.deleteThread(thread.id);setThread(null);setThreads(await api.listThreads());});}}>会話を削除</button>}</div>
    <div className="agent-conversation" aria-label="会話の内容" aria-live="polite">
      {!thread?.messages?.length&&<div className="agent-welcome"><h2>今日は何を記録しますか？</h2><p>「9月29日の取引から軌跡を作って」のように話しかけてください。</p><p>変更内容は保存前に確認できます。</p></div>}
      {thread?.messages?.map(m=><article key={m.id} className={`agent-message ${m.role}`}><strong>{m.role==='user'?'あなた':'Agent'}</strong><p>{m.text}</p></article>)}
    </div>
    {thread?.proposals?.map(p=><AgentProposal key={p.id} proposal={p} onChange={change} onCommitted={onCommitted} busy={busy} setBusy={setBusy}/>)}
    <form className="agent-composer" onSubmit={send}><label htmlFor="agent-message">メッセージ</label><textarea id="agent-message" ref={composer} value={text} onChange={e=>setText(e.target.value)} rows="3" maxLength="16000" disabled={busy||!status?.available} placeholder="記録したいこと、修正したいことを入力"/><div className="agent-actions"><span role="status">{busy?'処理しています…':'送信した内容は AI の処理に使われます。'}</span><button type="submit" className="primary-button" disabled={busy||!status?.available||!text.trim()}>{retry.current?'再送':'送信'}</button></div></form></>}
  </section>;
}
