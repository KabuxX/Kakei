import React, { useEffect, useMemo, useState } from 'react';
import AppShell from './AppShell.jsx';
import Dashboard from './Dashboard.jsx';
import { useTransactions } from './useTransactions.js';
import { dashboardForMonth, monthKey } from './lib/dashboard.js';
import { serializeTransactionsCsv } from './lib/transaction-data.js';

export default function App() {
  const now = new Date();
  const [month, setMonth] = useState(() => new Date(now.getFullYear(), now.getMonth() - 1, 1));
  const [route, setRoute] = useState(() => window.location.hash || '#overview');
  const [toast, setToast] = useState('');
  const data = useTransactions();
  const model = useMemo(() => dashboardForMonth(data.transactions, month), [data.transactions, month]);
  useEffect(() => {
    const onHash = () => setRoute(window.location.hash || '#overview');
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(''), 3500);
    return () => clearTimeout(timer);
  }, [toast]);

  const changeMonth = (step) => setMonth((previous) => new Date(previous.getFullYear(), previous.getMonth() + step, 1));
  const exportCsv = () => {
    if (!model.items.length) { setToast('この月に保存できる取引はありません。'); return; }
    const url = URL.createObjectURL(new Blob([serializeTransactionsCsv(model.items)], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `kakei-${monthKey(month)}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setToast('CSVを保存しました。');
  };

  return <>
    <AppShell route={route} onAdd={() => {}} addDisabled={data.status !== 'ready' || data.writePending}>
      <div id="sync-status" className="sync-status" role="alert" hidden={data.status !== 'stale'}><span id="sync-status-message">最新の取引を読み込めませんでした。再読み込みしてください。</span><button id="retry-sync" className="secondary-button" type="button" onClick={data.refresh}>表示を再読み込み</button></div>
      <Dashboard month={month} model={model} transactions={data.transactions} status={data.status} error={data.error} onMonthChange={changeMonth} onAdd={() => {}} onRetry={data.load} onClearSamples={() => {}} onExport={exportCsv} writePending={data.writePending} />
    </AppShell>
    <div id="toast" className={`toast${toast ? ' show' : ''}`} role="status" aria-live="polite">{toast}</div>
  </>;
}
