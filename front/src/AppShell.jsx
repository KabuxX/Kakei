import React from 'react';

const nav = [
  ['overview', '概要', 'grid'],
  ['transactions', '取引履歴', 'list'],
  ['budget', '予算', 'wallet'],
  ['insights', '支出の分析', 'chart'],
];

export function Icon({ name }) {
  return <svg aria-hidden="true"><use href={`#i-${name}`} /></svg>;
}

export default function AppShell({ children, route, onAdd, addDisabled }) {
  const active = route.startsWith('#transaction/') ? 'transactions' : ['transactions', 'budget', 'insights'].includes(route.slice(1)) ? route.slice(1) : 'overview';
  const today = new Intl.DateTimeFormat('ja-JP', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' }).format(new Date());
  return <>
    <a className="skip-link" href="#main">メインコンテンツへ</a>
    <div className="app-shell">
      <aside className="sidebar" aria-label="サイドバー">
        <a className="brand" href="#overview" aria-label="Kakei ホーム"><span className="brand-mark"><img src="/assets/kakei-logo.png" alt="" width="44" height="44" /></span><span>Kakei</span></a>
        <nav className="side-nav" aria-label="メインナビゲーション">
          {nav.map(([id, label, icon]) => <a key={id} className={`nav-link${active === id ? ' active' : ''}`} href={`#${id}`} aria-label={label} aria-current={active === id ? 'page' : undefined}><Icon name={icon} /><span>{label}</span></a>)}
        </nav>
        <div className="sidebar-bottom"><div className="profile"><span className="avatar">K</span><span><strong>わたしの家計</strong><small>この端末のサーバーに保存</small></span><span className="profile-dot" aria-hidden="true" /></div></div>
      </aside>
      <main id="main" className="main-content">
        <header className="topbar" id="overview"><div className="mobile-brand"><span className="brand-mark"><img src="/assets/kakei-logo.png" alt="" width="44" height="44" /></span><strong>Kakei</strong></div><div className="breadcrumb"><strong id="current-page-label">{route.startsWith('#transaction/') ? '取引詳細' : '家計の概要'}</strong></div><div className="topbar-actions"><span className="today-label" id="today-label">{today}</span><button className="primary-button add-trigger" type="button" aria-label="取引を追加" onClick={onAdd} disabled={addDisabled}><Icon name="plus" /><span>取引を追加</span></button></div></header>
        <div className="content-wrap">{children}</div>
      </main>
    </div>
  </>;
}
