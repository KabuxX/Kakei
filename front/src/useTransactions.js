import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from './lib/api.js';
import { createSampleTransactions } from './lib/sample-data.js';

export function useTransactions() {
  const [transactions, setTransactions] = useState([]);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);
  const [writePending, setWritePending] = useState(false);
  const [staleAfterWrite, setStaleAfterWrite] = useState(false);
  const pendingRef = useRef(false);
  const refreshingRef = useRef(false);

  const load = useCallback(async () => {
    setStatus('loading');
    setError(null);
    try {
      const now = new Date();
      const sampleMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const next = await api.loadInitialTransactions({
        fetchImpl: fetch,
        storage: { getItem: (key) => window.localStorage.getItem(key) },
        sampleFactory: () => createSampleTransactions(sampleMonth),
      });
      setTransactions(next);
      setStatus('ready');
      return true;
    } catch (cause) {
      setError(cause);
      setStatus('loadError');
      return false;
    }
  }, []);

  const refresh = useCallback(async (afterWrite = false) => {
    if (refreshingRef.current) return false;
    refreshingRef.current = true;
    try {
      const next = await api.listTransactions(fetch);
      setTransactions(next);
      setError(null);
      setStaleAfterWrite(false);
      setStatus('ready');
      return true;
    } catch (cause) {
      setError(cause);
      setStaleAfterWrite(afterWrite);
      setStatus('stale');
      return false;
    } finally {
      refreshingRef.current = false;
    }
  }, []);

  const write = useCallback(async (operation) => {
    if (pendingRef.current) throw new Error('保存処理中です。');
    pendingRef.current = true;
    setWritePending(true);
    try {
      await operation();
      return await refresh(true);
    } finally {
      pendingRef.current = false;
      setWritePending(false);
    }
  }, [refresh]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'visible' && status === 'ready' && !pendingRef.current) refresh();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [refresh, status]);

  return {
    transactions, status, error, writePending, staleAfterWrite, load, refresh,
    addTransaction: (draft) => write(() => api.addTransaction(draft, fetch)),
    deleteTransaction: (id) => write(() => api.removeTransaction(id, fetch)),
    deleteSamples: () => write(() => api.removeSamples(fetch)),
  };
}
