import React from 'react';

export function ChatIcon({name}) {
  const paths={
    attach:<><path d="m8 12 6-6a3 3 0 0 1 4 4l-8 8a5 5 0 0 1-7-7l9-9"/><path d="m6 14 8-8"/></>,
    send:<><path d="M12 19V5m-6 6 6-6 6 6"/></>,
    new:<><path d="M12 5v14M5 12h14"/></>,
    close:<path d="m6 6 12 12M18 6 6 18"/>,
    history:<><path d="M3 11a9 9 0 1 1 2.5 7M3 5v6h6"/><path d="M12 7v5l3 2"/></>,
    delete:<><path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6m4-6v6"/></>,
    file:<><path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6m-6 4h6"/></>,
    retry:<><path d="M4 10a8 8 0 1 1 1 7M4 4v6h6"/></>,
    spinner:<path d="M12 3a9 9 0 0 1 9 9"/>,
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={name==='spinner'?'agent-spinner':undefined}>{paths[name]}</svg>;
}
export function ChatButton({label,icon,className='',...props}) {
  return <button type="button" {...props} className={`chat-icon-button ${className}`} aria-label={label} title={label}><ChatIcon name={icon}/></button>;
}

export function AgentThreads({session,onSelected,readOnly=false}) {
  const {threads,thread,busy,loading,select,removeThread}=session;
  const choose=async id=>{if(await select(id))onSelected?.();};
  return <section className="agent-threads" aria-label="会話一覧">
    <div className="agent-threads-heading"><span>会話</span>{!readOnly&&<ChatButton label="新しい会話" icon="new" disabled={busy||loading} onClick={()=>choose('')}/>}</div>
    {loading?<p role="status">読み込み中…</p>:threads.length===0?<p className="agent-history-empty">会話はまだありません</p>:<ul>{threads.map(t=><li key={t.id} className={thread?.id===t.id?'selected':''}>
      <button type="button" className="agent-thread-link" aria-current={thread?.id===t.id?'true':undefined} disabled={busy} onClick={()=>choose(t.id)} title={t.title}>{t.title}</button>
      {!readOnly&&thread?.id===t.id&&<ChatButton label={`会話「${t.title}」を削除`} icon="delete" disabled={busy} onClick={()=>removeThread(t.id)}/>}
    </li>)}</ul>}
  </section>;
}
