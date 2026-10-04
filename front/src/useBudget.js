import {useCallback, useEffect, useRef, useState} from 'react';
import {loadBudget, updateBudget} from './lib/budget-api.js';

export function useBudget() {
  const [categories, setCategories] = useState(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const mounted = useRef(false);
  const generation = useRef(0);
  const saving = useRef(false);
  const saved = useRef(null);

  const load = useCallback(async () => {
    if (saving.current) return false;
    const token = ++generation.current;
    setStatus('loading');
    setError(null);
    try {
      const next = await loadBudget();
      if (!mounted.current || token !== generation.current) return false;
      saved.current = next;
      setCategories(next);
      setStatus('ready');
      return true;
    } catch (cause) {
      if (mounted.current && token === generation.current) {
        setError(cause);
        setStatus('loadError');
      }
      return false;
    }
  }, []);

  const save = useCallback(async next => {
    if (saving.current) throw new Error('予算を保存中です。');
    if (!saved.current) throw new Error('予算を読み込んでからお試しください。');
    saving.current = true;
    ++generation.current;
    setBusy(true);
    try {
      const result = await updateBudget(next);
      if (mounted.current) {
        saved.current = result;
        setCategories(result);
        setError(null);
      }
      return result;
    } finally {
      saving.current = false;
      if (mounted.current) {
        setBusy(false);
        setStatus('ready');
      }
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    load();
    return () => {mounted.current = false; ++generation.current;};
  }, [load]);

  return {categories, status, error, busy, load, save};
}
