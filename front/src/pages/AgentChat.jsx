import {receiptUrl as originalUrl,receiptPreviewUrl} from '@kakei/runtime';
import DemoPlaceResults from '../components/places/DemoPlaceResults.jsx';
import React, {useEffect, useRef, useState} from 'react';
import AgentProposal from '../components/agent/AgentProposal.jsx';
import AgentTrajectoryResult from '../components/agent/AgentTrajectoryResult.jsx';
import GooglePlaceResults from '../components/places/GooglePlaceResults.jsx';
import PlaceSources,{renderCitedText} from '../components/places/PlaceSources.jsx';
import ReceiptReview from '../components/receipts/ReceiptReview.jsx';
import {ChatButton,ChatIcon} from '../components/agent/AgentControls.jsx';

function useGreeting(){
  const get=()=>{const hour=new Date().getHours();return hour>=5&&hour<11?'おはよう':hour>=11&&hour<18?'こんにちは':'こんばんは';};
  const [greeting,setGreeting]=useState(get);
  useEffect(()=>{const update=()=>setGreeting(get());const timer=setInterval(update,60000);document.addEventListener('visibilitychange',update);return()=>{clearInterval(timer);document.removeEventListener('visibilitychange',update);};},[]);
  return greeting;
}

export default function AgentChat({session,onCommitted,onOpenTrajectory,readOnly=false}) {
  const {status,thread,messages=thread?.messages||[],sending=false,busy,setBusy,loading,error,draft,load,send,upload,change,proposed,setText,removeReceipt}=session;
  const greeting=useGreeting(), composer=useRef(null), file=useRef(null), conversation=useRef(null);
  const composing=useRef(false), [viewportInset,setViewportInset]=useState(0);
  const active=messages.length>0;
  const [refreshError,setRefreshError]=useState('');
  const latestMessage=useRef(null), progress=useRef(null);
  const receipt=draft.receipt;
  const unavailable=loading||!status?.available;
  useEffect(()=>{
    const viewport=window.visualViewport;if(!viewport)return;
    const update=()=>setViewportInset(Math.max(0,window.innerHeight-viewport.height-viewport.offsetTop));
    viewport.addEventListener('resize',update);viewport.addEventListener('scroll',update);update();
    return()=>{viewport.removeEventListener('resize',update);viewport.removeEventListener('scroll',update);};
  },[]);
  useEffect(()=>{
    if(active)(sending?progress.current:latestMessage.current)?.scrollIntoView?.({block:sending?'end':'start',behavior:'instant'});
  },[thread?.id,messages.length,sending,active]);
  const submit=async e=>{e?.preventDefault();setRefreshError('');const reply=await send();if(reply){composer.current?.focus({preventScroll:true});if(reply.trajectoryCreation?.counts.saved>0){try {if(await onCommitted?.()===false)setRefreshError('軌跡は保存済みですが、一覧を更新できませんでした。');}catch(error){setRefreshError('軌跡は保存済みです。'+(error.message||'一覧を更新できませんでした。'));}}}};
  const shortcut=e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)&&!e.nativeEvent.isComposing&&!composing.current&&e.keyCode!==229){e.preventDefault();submit();}};
  const receiptUrl=receipt?originalUrl(receipt.id,thread.id):null;
  return <section className={`agent-page${active?' agent-active':' agent-empty'}`} aria-label="Agent Chat" style={{'--keyboard-inset':`${viewportInset}px`}}>
    <h1 id="agent-heading" className="sr-only" tabIndex="-1">Agent Chat</h1>
    {active&&<div className="agent-history-content" ref={conversation}>
      <div className="agent-conversation" aria-label="会話の内容" aria-live="polite">
        {messages.map((m,i)=><article ref={i===messages.length-1?latestMessage:null} key={m.id} className={`agent-message ${m.role}`}><strong>{m.role==='user'?'あなた':'Agent'}</strong><p>{m.role==='assistant'?renderCitedText(m.text,m.sources):m.text}</p>{m.role==='assistant'&&<><PlaceSources sources={m.sources}/>{m.trajectoryCreation&&<AgentTrajectoryResult result={m.trajectoryCreation} onOpenTrajectory={onOpenTrajectory}/>} {!!m.placeSearch?.placeIds?.length&&(readOnly?<DemoPlaceResults placeIds={m.placeSearch.placeIds}/>:<GooglePlaceResults placeIds={m.placeSearch.placeIds}/>)}</>}{m.state==='failed'&&<small>{readOnly?'保存時点で応答を確認できませんでした。':'応答を確認できませんでした。入力欄から再送できます。'}</small>}</article>)}
      </div>
      {sending&&<div ref={progress} className="agent-message agent-processing" role="status" aria-label="Agentが処理中"><span className="agent-loading-dots" aria-hidden="true"><i/><i/><i/></span><span>Agentが処理中</span></div>}
      {thread?.receiptReviews?.filter(r=>!thread.proposals?.some(p=>p.metadata?.receiptId===r.receiptId)).map(r=><ReceiptReview readOnly={readOnly} key={r.receiptId} review={r} threadId={thread.id} busy={busy} setBusy={setBusy} onProposed={proposed}/>)}
      {thread?.proposals?.map(p=><AgentProposal readOnly={readOnly} key={p.id} proposal={p} onChange={change} onCommitted={onCommitted} busy={busy} setBusy={setBusy}/>)}
    </div>}
    {readOnly ? <div className="agent-input-region"><p className="agent-notice">{thread?"保存済みの会話を表示しています。":(loading?"会話履歴を読み込み中…":session.threads?.length?"会話履歴から表示する会話を選んでください。":"保存済みの会話はありません。")}</p>{error&&<div role="alert">{error}<button className="secondary-button" onClick={load}>再読み込み</button></div>}</div> : <div className="agent-input-region">
      {!active&&<h2 className="agent-greeting">{greeting}</h2>}
      {!loading&&status&&!status.available&&<p className="agent-notice">{status.message}</p>}
      {status?.available&&status.placesAvailable===false&&<p className="agent-notice">{status.placesMessage||'地点検索を利用できません。保存済み地点や座標指定は利用できます。'}</p>}
      <form className="agent-composer" aria-label="メッセージを作成" onSubmit={submit}>
        {receipt&&<div className="agent-attachment">
          <a href={receiptUrl} target="_blank" rel="noreferrer" aria-label="添付レシートを開く">{receipt.mimeType.startsWith('image/')?<img alt="添付レシート" src={receiptPreviewUrl(receipt.id,thread.id)}/>:<ChatIcon name="file"/>}<span>{receipt.name||'添付レシート'}</span></a>
          <ChatButton label="添付を外す" icon="close" disabled={busy} onClick={removeReceipt}/>
        </div>}
        <label className="sr-only" htmlFor="agent-message">メッセージ</label>
        <textarea id="agent-message" ref={composer} value={draft.text} onChange={e=>setText(e.target.value)} onKeyDown={shortcut} onCompositionStart={()=>{composing.current=true;}} onCompositionEnd={()=>{composing.current=false;}} rows={active?2:3} maxLength="16000" disabled={busy||unavailable} placeholder="記録したいこと、相談したいことを入力" aria-describedby="agent-input-help"/>
        <div className="agent-composer-tools">
          <input ref={file} id="agent-receipt" className="sr-only" tabIndex="-1" type="file" aria-label="レシートファイル" accept="image/jpeg,image/mpo,image/heic,image/heif,image/png,image/webp,application/pdf,.jpg,.jpeg,.mpo,.heic,.heif" disabled={busy||unavailable} onChange={e=>{upload(e.target.files?.[0]);e.target.value='';}}/>
          <ChatButton label="レシートを添付" icon="attach" disabled={busy||unavailable} onClick={()=>file.current?.click()}/>
          <span className="agent-compose-status" role="status">{loading?'接続を確認中…':busy&&!sending?'処理しています…':''}</span>
          <ChatButton type="submit" label={draft.retry&&!sending?'再送':'送信'} icon={busy&&!sending?'spinner':draft.retry&&!sending?'retry':'send'} className="agent-send" disabled={busy||unavailable||!draft.text.trim()}/>
        </div>
      </form>
      {refreshError&&<p role="alert">{refreshError}</p>}
      {error&&<div role="alert" className="agent-error">{error}<ChatButton label="状態を再読み込み" icon="retry" onClick={load} disabled={busy}/></div>}
      <div className="agent-input-help" id="agent-input-help"><span>AIへの送信に使用します · ⌘ / Ctrl + Enter で送信</span><details><summary>添付できるファイル</summary><p>JPEG・MPO・HEIC・HEIF・PNG・WebP・PDF / 10 MiBまで、PDFは3ページまで。iPhoneの写真はそのまま添付できます。</p></details></div>
    </div>}
  </section>;
}
