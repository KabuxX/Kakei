import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App.jsx';
import { useTransactions } from './useTransactions.js';

vi.mock('./useTransactions.js', () => ({ useTransactions: vi.fn() }));
const sample = { id: 'sample-0', title: '給与', type: 'income', category: '収入', date: '2026-09-28', amount: 320000 };
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
  fireEvent.click(screen.getByRole('radio', { name: '収入' }));
  fireEvent.change(screen.getByRole('textbox', { name: /内容/ }), { target: { value: '臨時収入' } });
  fireEvent.change(screen.getByRole('spinbutton', { name: /金額/ }), { target: { value: '1000' } });
  fireEvent.click(screen.getByRole('button', { name: '追加する' }));
  await waitFor(() => expect(methods.addTransaction).toHaveBeenCalledTimes(1));
});

it('confirms sample deletion before one request', async () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'サンプルを削除' }));
  await waitFor(() => expect(methods.deleteSamples).toHaveBeenCalledTimes(1));
  expect(window.confirm).toHaveBeenCalled();
});

it('confirms detail deletion before one request', async () => {
  window.location.hash = '#transaction/sample-0';
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: '取引を削除' }));
  await waitFor(() => expect(methods.deleteTransaction).toHaveBeenCalledWith('sample-0'));
});
