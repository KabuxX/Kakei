import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App.jsx';
import { useTransactions } from './useTransactions.js';

vi.mock('./useTransactions.js', () => ({ useTransactions: vi.fn() }));
const sample = { id: 'sample-0', title: '給与', type: 'income', category: '収入', date: '2026-09-28T09:17', amount: 320000, timeEstimated: true };
let methods;

beforeEach(() => {
  window.location.hash = '#overview';
  window.scrollTo = vi.fn();
  window.confirm = vi.fn().mockReturnValue(true);
  methods = { addTransaction: vi.fn().mockResolvedValue(true), deleteTransaction: vi.fn().mockResolvedValue(true), deleteSamples: vi.fn().mockResolvedValue(true) };
  useTransactions.mockReturnValue({ transactions: [sample], status: 'ready', error: null, writePending: false, load: vi.fn(), refresh: vi.fn(), ...methods });
});
afterEach(() => { cleanup(); window.location.hash = ''; });

it('opens the dialog and submits one new transaction', async () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: '取引を追加' }));
  expect(screen.getByRole('dialog')).toBeTruthy();
  fireEvent.change(screen.getByLabelText(/日付と時刻/), { target: { value: '2026-10-03T09:17' } });
  fireEvent.click(screen.getByRole('radio', { name: '収入' }));
  fireEvent.change(screen.getByRole('textbox', { name: /内容/ }), { target: { value: '臨時収入' } });
  fireEvent.change(screen.getByRole('spinbutton', { name: /金額/ }), { target: { value: '1000' } });
  fireEvent.click(screen.getByRole('button', { name: '追加する' }));
  await waitFor(() => expect(methods.addTransaction).toHaveBeenCalledTimes(1));
  expect(methods.addTransaction).toHaveBeenCalledWith(expect.objectContaining({ date: '2026-10-03T09:17' }));
  expect(screen.getByText('2026年10月')).toBeTruthy();
});

it('confirms sample deletion before one request', async () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'サンプルを削除' }));
  await waitFor(() => expect(methods.deleteSamples).toHaveBeenCalledTimes(1));
  expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(/レシート原本/));
  expect(window.confirm.mock.calls[0][0]).toMatch(/軌跡/);
});

it('shows a dedicated confirmation before deleting the selected transaction', async () => {
  window.location.hash = '#transaction/sample-0';
  render(<App />);
  fireEvent.click(screen.getByRole('link', { name: '取引を削除' }));
  await waitFor(() => expect(screen.getByRole('heading', { name: 'この取引を削除しますか？' })).toBeTruthy());
  expect(screen.getByRole('heading', { name: '給与' })).toBeTruthy();
  expect(screen.getByRole('article', { name: '削除する取引' }).textContent).toContain('+¥320,000');
  expect(screen.getByText(/紐づくレシート原本/)).toBeTruthy();
  expect(screen.getByText(/交通費の参照/)).toBeTruthy();
  expect(methods.deleteTransaction).not.toHaveBeenCalled();
  expect(window.confirm).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '削除する' }));
  await waitFor(() => expect(methods.deleteTransaction).toHaveBeenCalledWith('sample-0'));
  await waitFor(() => expect(window.location.hash).toBe('#transactions'));
  expect(screen.getByRole('status').textContent).toContain('取引を削除しました');
});

it('returns to detail without deleting when confirmation is cancelled', async () => {
  window.location.hash = '#transaction/sample-0/delete';
  render(<App />);
  fireEvent.click(screen.getByRole('link', { name: '取引詳細へ戻る' }));
  await waitFor(() => expect(screen.getByRole('heading', { name: '取引詳細' })).toBeTruthy());
  expect(window.location.hash).toBe('#transaction/sample-0');
  expect(methods.deleteTransaction).not.toHaveBeenCalled();
});

it('keeps the delete action disabled while the request is pending', () => {
  methods.deleteTransaction.mockReturnValue(new Promise(() => {}));
  window.location.hash = '#transaction/sample-0/delete';
  render(<App />);
  expect(screen.getByText('削除後は元に戻せません。内容を確認してください。')).toBeTruthy();
  expect(screen.getByRole('article', { name: '削除する取引' }).textContent).toContain('2026年9月28日');
  fireEvent.click(screen.getByRole('button', { name: '削除する' }));
  expect(screen.getByRole('button', { name: '削除中…' }).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '削除中…' }));
  expect(methods.deleteTransaction).toHaveBeenCalledTimes(1);
});

it('keeps confirmation and the transaction visible after a failed deletion', async () => {
  methods.deleteTransaction.mockRejectedValueOnce(new Error('offline'));
  window.location.hash = '#transaction/sample-0/delete';
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: '削除する' }));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('削除できませんでした'));
  expect(window.location.hash).toBe('#transaction/sample-0/delete');
  expect(screen.getByRole('heading', { name: '給与' })).toBeTruthy();
  expect(screen.getByRole('button', { name: '削除する' }).disabled).toBe(false);
});
