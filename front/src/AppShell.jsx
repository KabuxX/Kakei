import React, {useEffect, useRef, useState} from 'react';
import {AgentThreads, ChatButton} from './AgentControls.jsx';

const nav = [
  ['overview', '概要', 'grid'],
  ['trajectory', '軌跡', 'trail'],
  ['agent', 'Agent Chat', 'chat'],
];

export function Icon({ name }) {
  return <svg aria-hidden="true"><use href={`#i-${name}`} /></svg>;
}

export default function AppShell({ children, route, onAdd, addDisabled, agent }) {
  const [sidebarHidden, setSidebarHidden] = useState(false);
  const [compact,setCompact]=useState(()=>window.matchMedia?.('(max-width: 1050px)').matches||false);
  const [historyOpen,setHistoryOpen]=useState(false);
  const historyDialog=useRef(null);
  const drawer=compact||sidebarHidden;
  useEffect(()=>{const media=window.matchMedia?.('(max-width: 1050px)');if(!media)return;const change=()=>setCompact(media.matches);media.addEventListener('change',change);return()=>media.removeEventListener('change',change);},[]);
  useEffect(()=>{if(route!=='#agent'||!drawer)setHistoryOpen(false);},[route,drawer]);
  useEffect(()=>{const dialog=historyDialog.current;if(!dialog)return;if(historyOpen){if(dialog.showModal)dialog.showModal();else dialog.setAttribute('open','');}else if(dialog.open){if(dialog.close)dialog.close();else dialog.removeAttribute('open');}},[historyOpen]);
  const active = route === '#agent' ? 'agent' : route === '#trajectory' ? 'trajectory' : 'overview';
  const today = new Intl.DateTimeFormat('ja-JP', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' }).format(new Date());
  return <>
    <a className="skip-link" href="#main">メインコンテンツへ</a>
    <div id="overview" className={`app-shell${sidebarHidden ? ' sidebar-hidden' : ''}${active==='agent'?' agent-shell':''}`}>
      <aside id="app-sidebar" className="sidebar" aria-label="サイドバー">
        <a className="brand" href="#overview" aria-label="Kakei ホーム"><span className="brand-mark"><img src="/assets/kakei-logo.png" alt="" width="44" height="44" /></span><span>Kakei</span></a>
        <nav className="side-nav" aria-label="メインナビゲーション">
          {nav.map(([id, label, icon]) => <React.Fragment key={id}><a className={`nav-link${active === id ? ' active' : ''}`} href={`#${id}`} aria-label={label} aria-current={active === id ? 'page' : undefined}><Icon name={icon} /><span>{label}</span></a>{id==='agent'&&agent&&!drawer&&<AgentThreads session={agent}/>}</React.Fragment>)}
        </nav>
      </aside>
      <main id="main" className="main-content">
        <header className="topbar"><div className="mobile-brand"><span className="brand-mark"><img src="/assets/kakei-logo.png" alt="" width="44" height="44" /></span><strong>Kakei</strong></div><div className="topbar-leading"><button className="sidebar-toggle" type="button" aria-label={sidebarHidden ? 'サイドバーを表示' : 'サイドバーを隠す'} title={sidebarHidden ? 'サイドバーを表示' : 'サイドバーを隠す'} aria-controls="app-sidebar" aria-expanded={!sidebarHidden} onClick={() => setSidebarHidden((hidden) => !hidden)}><Icon name={sidebarHidden ? 'panel-open' : 'panel-close'} /></button><div className="breadcrumb"><strong id="current-page-label">{route === '#agent' ? 'Agent Chat' : route === '#trajectory' ? '軌跡' : route.startsWith('#transaction/') ? route.endsWith('/delete') ? '削除確認' : route.endsWith('/edit') ? '取引を編集' : '取引詳細' : '家計の概要'}</strong></div></div><div className="topbar-actions">{agent&&drawer&&<ChatButton label="会話履歴を開く" icon="history" aria-haspopup="dialog" aria-expanded={historyOpen} onClick={()=>setHistoryOpen(true)}/>}<span className="today-label" id="today-label">{today}</span><button className="primary-button add-trigger" type="button" aria-label="取引を追加" onClick={onAdd} disabled={addDisabled}><Icon name="plus" /><span>取引を追加</span></button></div></header>
        <div className="content-wrap">{children}</div>
      </main>
    </div>
    {agent&&drawer&&<dialog ref={historyDialog} className="agent-history-dialog" aria-labelledby="agent-history-title" onClose={()=>setHistoryOpen(false)} onCancel={()=>setHistoryOpen(false)} onClick={e=>{if(e.target===e.currentTarget)setHistoryOpen(false);}}>
      <header><h2 id="agent-history-title">会話履歴</h2><ChatButton label="会話履歴を閉じる" icon="close" onClick={()=>setHistoryOpen(false)}/></header>
      <AgentThreads session={agent} onSelected={()=>setHistoryOpen(false)}/>
    </dialog>}
  </>;
}
