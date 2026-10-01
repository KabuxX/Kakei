import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { useTransactions } from './useTransactions.js';
import * as api from './lib/api.js';

vi.mock('./lib/api.js', () => ({
  loadInitialTransactions: vi.fn(), listTransactions: vi.fn(),
  addTransaction: vi.fn(), removeTransaction: vi.fn(), removeSamples: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  api.loadInitialTransactions.mockResolvedValue([{ id: 'a' }]);
  api.listTransactions.mockResolvedValue([{ id: 'a' }]);
});
afterEach(cleanup);

it('loads initial server data and can retry after an error', async () => {
  api.loadInitialTransactions.mockRejectedValueOnce(new Error('offline'));
  const { result } = renderHook(() => useTransactions());
  await waitFor(() => expect(result.current.status).toBe('loadError'));
  expect(result.current.error.message).toBe('offline');
  await act(async () => { await result.current.load(); });
  expect(result.current.status).toBe('ready');
  expect(result.current.transactions).toEqual([{ id: 'a' }]);
});

it('keeps a successful write single when refresh fails', async () => {
  const { result } = renderHook(() => useTransactions());
  await waitFor(() => expect(result.current.status).toBe('ready'));
  api.addTransaction.mockResolvedValue({ id: 'b' });
  api.listTransactions.mockRejectedValueOnce(new Error('offline'));
  let refreshed;
  await act(async () => { refreshed = await result.current.addTransaction({ title: '食材' }); });
  expect(refreshed).toBe(false);
  expect(result.current.status).toBe('stale');
  expect(api.addTransaction).toHaveBeenCalledTimes(1);
  await act(async () => { await result.current.refresh(); });
  expect(result.current.status).toBe('ready');
  expect(api.addTransaction).toHaveBeenCalledTimes(1);
});
