import React, { useState } from 'react';
import { Icon } from '../components/layout/AppShell.jsx';
import { yen } from '../lib/dashboard.js';
import {budgetUsage} from '../lib/budget.js';
import { detailHref } from '../lib/transaction-detail.js';

const weeks = ['1–7日', '8–14日', '15–21日', '22–28日', '29日–'];

export default function Dashboard({ month, model, status, error, onMonthChange, onAdd, onRetry, onExport, exporting = false, onOpenDetail, writePending = false, hidden = false, budgetStatus = 'loading', budgetError, onRetryBudget, onEditBudget, budgetBusy = false }) {
  const [query, setQuery] = useState('');
  const [type, setType] = useState('all');
  const ready = status === 'ready';
  const disabled = !ready || writePending;
  const { items, income, expense, balance, remaining, totalBudget, categoryTotals, weekly } = model;
  const budgetReady = budgetStatus === 'ready' && totalBudget !== null;
  const usage = budgetReady ? budgetUsage(expense, totalBudget) : null;
  const visibleCategories = categoryTotals.filter((item) => item.amount > 0).sort((a, b) => b.amount - a.amount);
  const filtered = items.filter((item) => (type === 'all' || item.type === type) && (!query.trim() || `${item.title} ${item.category}`.toLocaleLowerCase('ja-JP').includes(query.trim().toLocaleLowerCase('ja-JP'))));
  let point = 0;
  const stops = visibleCategories.map((item) => { const start = point; point += item.amount / expense * 100; return `${item.color} ${start}% ${point}%`; });
  const chartMax = Math.max(...weekly, 1);
  return <div id="dashboard-view" className={ready ? 'data-ready' : ''} aria-busy={status === 'loading' ? 'true' : undefined} hidden={hidden}>
    <h1 id="dashboard-heading" className="sr-only" tabIndex="-1">家計ダッシュボード</h1>
    <div className="dashboard-grid">
      <section className="balance-card" aria-labelledby="balance-title">
        <div className="balance-top"><span className="card-kicker" id="balance-title">月の収支</span><div className="month-picker" aria-label="表示月"><button id="prev-month" className="icon-button" type="button" aria-label="前の月" onClick={() => onMonthChange(-1)}><Icon name="chevron" /></button><span id="month-label" aria-live="polite">{month.getFullYear()}年{month.getMonth() + 1}月</span><button id="next-month" className="icon-button next" type="button" aria-label="次の月" onClick={() => onMonthChange(1)}><Icon name="chevron" /></button></div></div>
        <div className="balance-main"><span id="balance-amount" className="balance-amount">{ready ? `${balance < 0 ? '−' : ''}${yen(balance)}` : '—'}</span><p id="balance-message">{status === 'loading' ? '取引を読み込んでいます' : status === 'loadError' ? '取引を読み込めませんでした' : status === 'stale' ? '表示を更新してください' : items.length ? balance >= 0 ? '収入が支出を上回っています' : '支出が収入を上回っています' : '取引を追加して収支を確認しましょう'}</p><div id="data-status" className="data-status" role="status" aria-live="polite" hidden={status !== 'loadError'}><span id="data-status-message">{error?.message || 'サーバーへの接続を確認してください。'}</span><button id="retry-load" className="secondary-button" type="button" onClick={onRetry}>再試行</button></div></div>
        <div className="balance-decoration" aria-hidden="true"><span className="orbit orbit-one" /><span className="orbit orbit-two" /><span className="orbit orbit-three" /></div>
        <div className="balance-bottom"><div><span className="stat-icon income"><Icon name="arrow-down" /></span><span><small>収入</small><strong id="income-total">{ready ? yen(income) : '—'}</strong></span></div><div><span className="stat-icon expense"><Icon name="arrow-up" /></span><span><small>支出</small><strong id="expense-total">{ready ? yen(expense) : '—'}</strong></span></div></div>
      </section>
      <section className="budget-overview card" aria-labelledby="budget-overview-title">
        <div className="card-head"><div><h2 id="budget-overview-title">月の予算</h2><span className="card-note">毎月共通</span></div><button className="secondary-button budget-edit-button" type="button" onClick={onEditBudget} disabled={!budgetReady || budgetBusy}><Icon name="wallet"/>予算を設定</button></div>
        <div className="budget-overview-body"><span className="muted-label">あと使える金額</span><strong id="remaining-budget" className="big-number">{budgetReady ? `${remaining < 0 ? '−' : ''}${yen(remaining)}` : '—'}</strong>
          <div className="progress-track"><span id="budget-progress" className={usage?.over ? 'over' : ''} style={{width:`${usage?.percent ?? 0}%`}}/></div>
          <div className="progress-copy"><span id="budget-used">{yen(expense)} 使用済み</span><span id="budget-limit">予算 {budgetReady ? yen(totalBudget) : '—'}</span></div>
          {usage?.over && <p className="budget-excess">{yen(usage.excess)} 超過</p>}
          {budgetStatus === 'loading' && <p className="budget-state" role="status">予算を読み込んでいます…</p>}
          {budgetStatus === 'loadError' && <div className="budget-load-error" role="alert"><p>予算を読み込めませんでした。</p><p>{budgetError?.message}</p><button type="button" className="secondary-button" onClick={onRetryBudget}>予算を再読み込み</button></div>}
        </div>
      </section>
      <section id="insights" className="insights-card card" aria-labelledby="insights-title"><div className="card-head"><div><h2 id="insights-title">支出の内訳</h2></div><span className="card-note">カテゴリ別</span></div><div className="insights-body"><div className="donut-wrap"><div id="donut" className="donut" role="img" aria-label={expense ? `支出合計 ${yen(expense)}。${visibleCategories.map((item) => `${item.name} ${yen(item.amount)}`).join('、')}` : 'この月の支出はまだありません'} style={{ background: expense ? `conic-gradient(${stops.join(',')})` : '#dce2eb' }}><div className="donut-hole"><small>支出合計</small><strong id="donut-total">{yen(expense)}</strong></div></div></div><div id="category-list" className="category-list">{visibleCategories.length ? visibleCategories.map((item) => <div className="category-row" key={item.name}><span className="category-name"><span className="category-dot" style={{ background: item.color }} />{item.name}</span><span className="category-value">{yen(item.amount)} <span className="category-percent">{Math.round(item.amount / expense * 100)}%</span></span></div>) : <p className="category-empty">支出を記録すると、ここに内訳が表示されます。</p>}</div></div></section>
      <section id="budget" className="budget-card card" aria-labelledby="budget-title"><div className="card-head"><div><h2 id="budget-title">カテゴリ別の予算</h2></div><span className="card-note" id="budget-period">{month.getMonth()+1}月の利用状況</span></div><div id="budget-list" className="budget-list">{categoryTotals.map(item => {
        const current = budgetReady ? budgetUsage(item.amount,item.budget) : null;
        const valueText = current?.over ? `${yen(current.excess)} 超過` : `${Math.round(current?.percent ?? 0)}パーセント`;
        return <div className="budget-line" key={item.name}><div className="budget-line-top"><strong>{item.name}</strong><span>{yen(item.amount)} / {budgetReady ? yen(item.budget) : '—'}</span></div>
          <div className="progress-track" role={budgetReady ? 'meter' : undefined} aria-label={budgetReady ? `${item.name}の予算使用率` : undefined} aria-valuemin={budgetReady ? 0 : undefined} aria-valuemax={budgetReady ? 100 : undefined} aria-valuenow={budgetReady ? Math.round(current.percent) : undefined} aria-valuetext={budgetReady ? valueText : undefined}><span className={current?.over ? 'over' : current?.percent >= 80 ? 'warning' : 'safe'} style={{width:`${current?.percent ?? 0}%`}}/></div>
          {current?.over && <p className="budget-excess">{yen(current.excess)} 超過</p>}
        </div>;
      })}</div></section>
      <section className="trend-card card" aria-labelledby="trend-title"><div className="card-head"><div><h2 id="trend-title">週ごとの支出</h2></div><span className="card-note">円 / 週</span></div><div id="weekly-chart" className="weekly-chart" aria-label={`週ごとの支出。${weekly.map((amount, index) => `${weeks[index]} ${yen(amount)}`).join('、')}`}>{weekly.map((amount, index) => <div className="week-column" key={index}><span className="week-value">{yen(amount)}</span><span className="week-bar" style={{ height: `${Math.max(3, amount / chartMax * 102)}px` }} /><span className="week-label">{weeks[index]}</span></div>)}</div><p className="chart-caption">月内の各週に記録された支出を表示しています。</p></section>
      <section id="transactions" className="transactions-card card" aria-labelledby="transactions-title"><div className="card-head transaction-heading"><div><h2 id="transactions-title" tabIndex="-1">取引履歴 <span id="transaction-count" className="count-pill">{items.length}</span></h2></div><button id="export-button" className="secondary-button" type="button" aria-label="取引をCSVで保存" onClick={onExport} disabled={disabled || exporting}><Icon name="download" /><span>CSVで保存</span></button></div><div className="transaction-tools"><label className="search-field"><Icon name="search" /><span className="sr-only">取引を検索</span><input id="transaction-search" type="search" placeholder="取引を検索" value={query} onChange={(event) => setQuery(event.target.value)} /></label><label className="select-wrap"><span className="sr-only">取引種別</span><select id="type-filter" value={type} onChange={(event) => setType(event.target.value)}><option value="all">すべての取引</option><option value="expense">支出のみ</option><option value="income">収入のみ</option></select></label></div><div className="table-scroll" hidden={!filtered.length}><table><thead><tr><th scope="col">取引</th><th scope="col">カテゴリ</th><th scope="col">日付</th><th scope="col" className="amount-col">金額</th></tr></thead><tbody id="transaction-rows">{filtered.map((item) => <tr key={item.id}><td><div className="transaction-name"><span className={`transaction-icon${item.type === 'income' ? ' income' : ''}`}><Icon name={item.type === 'income' ? 'arrow-down' : 'arrow-up'} /></span><a className="transaction-link" href={detailHref(item.id)} data-id={item.id} onClick={() => onOpenDetail?.(item.id)}>{item.title}</a></div></td><td><span className="category-pill">{item.category}</span></td><td>{Number(item.date.slice(5, 7))}月{Number(item.date.slice(8, 10))}日</td><td className="amount-col"><span className={`amount${item.type === 'income' ? ' income' : ''}`}>{item.type === 'income' ? '+' : '−'}{yen(item.amount)}</span></td></tr>)}</tbody></table></div><div id="transaction-empty" className="empty-state" hidden={filtered.length > 0}><span className="empty-mark"><Icon name="list" /></span><strong>取引がありません</strong><p>検索条件を変えるか、新しい取引を追加してください。</p><button className="text-link add-trigger" type="button" onClick={onAdd} disabled={disabled}>取引を追加する <span aria-hidden="true">↗</span></button></div></section>
    </div>
  </div>;
}
