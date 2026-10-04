import React, { useEffect, useMemo, useRef, useState } from 'react';
import AppShell from './AppShell.jsx';
import {listTransactionAddresses} from './lib/api.js';
import AgentChat from './AgentChat.jsx';
import {useAgentChat} from './useAgentChat.js';
import Dashboard from './Dashboard.jsx';
import Trajectory from './Trajectory.jsx';
import TransactionDetail from './TransactionDetail.jsx';
import TransactionEdit from './TransactionEdit.jsx';
import TransactionDelete from './TransactionDelete.jsx';
import TransactionDialog from './TransactionDialog.jsx';
import { useTransactions } from './useTransactions.js';
import { dashboardForMonth, monthKey } from './lib/dashboard.js';
import { serializeTransactionsCsv } from './lib/transaction-data.js';
import { transactionMonthKey } from './lib/transaction-datetime.js';
import { detailHref, detailIdFromHash, deleteIdFromHash, editIdFromHash } from './lib/transaction-detail.js';

export default function App() {
  const now = new Date();
  const [month, setMonth] = useState(() => new Date(now.getFullYear(), now.getMonth() - 1, 1));
  const [route, setRoute] = useState(() => window.location.hash || '#overview');
  const [toast, setToast] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const addTrigger = useRef(null);
  const listReturn = useRef(null);
  const previousDetail = useRef(null);
  const previousTrajectory = useRef(false);
  const data = useTransactions();
  const model = useMemo(() => dashboardForMonth(data.transactions, month), [data.transactions, month]);
  const isAgent = route === '#agent';
  const agent = useAgentChat(isAgent && ['ready','stale'].includes(data.status));
  const [requestedTrajectoryDate,setRequestedTrajectoryDate]=useState(null);
  const [trajectoryRevision, setTrajectoryRevision] = useState(0);
  const isTrajectory = route === '#trajectory';
  const isDetail = ['ready', 'stale'].includes(data.status) && (route === '#transaction' || route.startsWith('#transaction/'));
  const isDelete = isDetail && route.endsWith('/delete');
  const isEdit = isDetail && route.endsWith('/edit');
  const detailId = isDetail ? (isDelete ? deleteIdFromHash(route) : isEdit ? editIdFromHash(route) : detailIdFromHash(route)) : null;
  const detailRecord = isDetail ? data.transactions.find((item) => item.id === detailId) : null;
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
  useEffect(() => {
    if (isDetail) {
      previousTrajectory.current = false;
      previousDetail.current = detailId;
      document.body.classList.add('detail-route');
      document.title = detailRecord ? `${isDelete ? '削除確認' : isEdit ? '取引を編集' : detailRecord.title} | Kakei` : '取引が見つかりません | Kakei';
      window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
      document.getElementById(isDelete ? 'delete-heading' : isEdit ? 'edit-heading' : 'detail-heading')?.focus({ preventScroll: true });
    } else {
      document.body.classList.remove('detail-route');
      document.title = isAgent ? 'Agent Chat | Kakei' : isTrajectory ? '軌跡 | Kakei' : '家計の概要 | Kakei';
      if (isAgent) {
        previousTrajectory.current = true;
        window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
        document.getElementById('agent-heading')?.focus({ preventScroll: true });
      } else if (isTrajectory) {
        previousTrajectory.current = true;
        window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
        document.getElementById('trajectory-heading')?.focus({ preventScroll: true });
      } else if (previousDetail.current !== null || previousTrajectory.current) {
        const saved = listReturn.current?.id === previousDetail.current ? listReturn.current : null;
        if (saved && route === '#transactions') {
          window.scrollTo(0, saved.scrollY);
          [...document.querySelectorAll('.transaction-link')].find((link) => link.dataset.id === saved.id)?.focus({ preventScroll: true });
        } else if (route === '#transactions') {
          document.getElementById('transactions')?.scrollIntoView?.();
          document.getElementById('transactions-title')?.focus({ preventScroll: true });
        } else if (route === '#budget' || route === '#insights') {
          document.querySelector(route)?.scrollIntoView();
        } else if (route === '#overview') {
          window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
          document.getElementById('dashboard-heading')?.focus({ preventScroll: true });
        }
        previousDetail.current = null;
        previousTrajectory.current = false;
      }
    }
    return () => document.body.classList.remove('detail-route');
  }, [isDetail, isDelete, isEdit, isTrajectory, isAgent, detailId, detailRecord, route, data.status]);
  useEffect(() => { setDeleteError(''); }, [route]);

  const changeMonth = (step) => setMonth((previous) => new Date(previous.getFullYear(), previous.getMonth() + step, 1));
  const openDialog = (event) => {
    if (data.status !== 'ready' || data.writePending || data.refreshing) return;
    addTrigger.current = event.currentTarget;
    setDialogOpen(true);
  };
  const closeDialog = () => {
    setDialogOpen(false);
    requestAnimationFrame(() => addTrigger.current?.focus({ preventScroll: true }));
  };
  const submitTransaction = async (draft) => {
    const refreshed = await data.addTransaction(draft);
    const [year, monthNumber] = transactionMonthKey(draft.date).split('-').map(Number);
    setMonth(new Date(year, monthNumber - 1, 1));
    setToast(refreshed ? '取引を追加しました。' : '取引を保存しました。表示を更新してください。');
    return refreshed;
  };
  const updateTransaction = async (draft) => {
    const refreshed = await data.updateTransaction(detailRecord.id, draft);
    const [year, monthNumber] = transactionMonthKey(draft.date).split('-').map(Number);
    setMonth(new Date(year, monthNumber - 1, 1));
    setTrajectoryRevision(v=>v+1);
    setToast(refreshed ? '取引を更新しました。' : '取引を保存しました。表示を更新してください。');
    return refreshed;
  };
  const cancelEdit = () => {
    const target = detailRecord ? detailHref(detailRecord.id) : '#transactions';
    window.location.hash=target;setRoute(target);
  };
  const deleteTransaction = async (record) => {
    if (data.status !== 'ready' || data.writePending || data.refreshing || deletePending) return;
    setDeletePending(true);
    setDeleteError('');
    try {
      const refreshed = await data.deleteTransaction(record.id);
      listReturn.current = null;
      window.location.hash = '#transactions';
      setRoute('#transactions');
      setToast(refreshed ? '取引を削除しました。' : '取引を削除しました。表示を更新してください。');
    } catch (_) { setDeleteError('削除できませんでした。サーバーへの接続を確認して、もう一度お試しください。'); }
    finally { setDeletePending(false); }
  };
  const [exporting,setExporting]=useState(false);
  const exportLock=useRef(false);
  const [prefillPending,setPrefillPending]=useState(false);
  const reviewAddress=({transactionId,date})=>{
    agent.prefillMessage(`${date}の取引（ID: ${transactionId}）の保存住所を確認し、対応する軌跡の位置を修正してください。`);
    setPrefillPending(true);window.location.hash='#agent';
  };
  useEffect(()=>{if(isAgent && prefillPending){document.querySelector('#agent-message')?.focus();setPrefillPending(false);}},[isAgent,prefillPending]);
  const exportCsv = async () => {
    if(exportLock.current)return;

    if (!model.items.length) { setToast('この月に保存できる取引はありません。'); return; }
    exportLock.current=true;setExporting(true);
    try {
    const contexts=await listTransactionAddresses();
    const url = URL.createObjectURL(new Blob([serializeTransactionsCsv(model.items,contexts)], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `kakei-${monthKey(month)}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setToast('CSVを保存しました。');
    } catch {setToast('住所を取得できませんでした。CSVで保存を押して再試行してください。');}
    finally {exportLock.current=false;setExporting(false);}
  };

  return <>
    <AppShell agent={isAgent && ['ready','stale'].includes(data.status) ? agent : null} route={route} onAdd={openDialog} addDisabled={data.status !== 'ready' || data.writePending || data.refreshing}>
      <div id="sync-status" className="sync-status" role="alert" hidden={isTrajectory || data.status !== 'stale'}><span id="sync-status-message">{data.staleAfterWrite ? 'サーバーへの保存は完了しましたが、表示を更新できませんでした。再読み込みしてください。' : '最新の取引を読み込めませんでした。再読み込みしてください。'}</span><button id="retry-sync" className="secondary-button" type="button" onClick={() => data.refresh()}>表示を再読み込み</button></div>
      <Dashboard month={month} model={model} status={data.status} error={data.error} onMonthChange={changeMonth} onAdd={openDialog} onRetry={data.load} onExport={exportCsv} exporting={exporting} onOpenDetail={(id) => { listReturn.current = { id, scrollY: window.scrollY }; }} writePending={data.writePending || data.refreshing} hidden={isDetail || isTrajectory || isAgent} />
      <div id="trajectory-view" hidden={!isTrajectory}>{isTrajectory && <Trajectory requestedDate={requestedTrajectoryDate} onReviewAddress={reviewAddress} transactions={data.transactions} refreshKey={trajectoryRevision} />}</div>
      {isAgent && (['ready','stale'].includes(data.status) ? <AgentChat session={agent} onOpenTrajectory={date=>{setRequestedTrajectoryDate(date);window.location.hash='trajectory';}} onCommitted={async () => { setTrajectoryRevision(v => v + 1); return await data.refresh(true); }} /> : <section><h1 id="agent-heading" tabIndex="-1">Agent Chat</h1>{data.status === 'loading' ? <p role="status">家計データを準備しています…</p> : <div role="alert"><p>家計データを読み込めませんでした。</p><button type="button" className="secondary-button" onClick={data.load}>再試行</button></div>}</section>)}
      {isDetail && (isDelete
        ? <TransactionDelete record={detailRecord} onConfirm={deleteTransaction} error={deleteError} busy={deletePending || data.writePending || data.refreshing || data.status !== 'ready'} />
        : isEdit ? <TransactionEdit record={detailRecord} onSubmit={updateTransaction} onCancel={cancelEdit} busy={data.writePending || data.refreshing} saveDisabled={data.status !== 'ready'}/>
        : <TransactionDetail record={detailRecord} busy={data.writePending || data.refreshing || data.status !== 'ready'} />)}
    </AppShell>
    <TransactionDialog open={dialogOpen} selectedMonth={month} busy={data.writePending || data.refreshing} onClose={closeDialog} onSubmit={submitTransaction} />
    <div id="toast" className={`toast${toast ? ' show' : ''}`} role="status" aria-live="polite">{toast}</div>
  </>;
}
