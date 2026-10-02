import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App.jsx';
import { useTransactions } from './useTransactions.js';
import { detailHref } from './lib/transaction-detail.js';

vi.mock('./useTransactions.js', () => ({ useTransactions: vi.fn() }));
const record = { id: 'a/b %日本語', title: '食材', type: 'expense', date: '2026-09-27', category: '食費', amount: 1200 };

beforeEach(() => {
  useTransactions.mockReturnValue({ transactions: [record], status: 'ready', error: null, writePending: false, load: vi.fn(), refresh: vi.fn(), addTransaction: vi.fn(), deleteTransaction: vi.fn(), deleteSamples: vi.fn() });
  window.scrollTo = vi.fn();
});
afterEach(() => { cleanup(); window.location.hash = ''; });

it('opens an encoded direct detail URL and marks transactions active', () => {
  window.location.hash = detailHref(record.id);
  render(<App />);
  expect(screen.getByRole('heading', { name: '食材' })).toBeTruthy();
  expect(screen.getByRole('link', { name: '取引履歴' }).getAttribute('aria-current')).toBe('page');
});

it('opens a direct deletion URL for an ID containing reserved characters', () => {
  window.location.hash = '#transaction/a%2Fb%20%25%E6%97%A5%E6%9C%AC%E8%AA%9E/delete';
  render(<App />);
  expect(screen.getByRole('heading', { name: 'この取引を削除しますか？' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: '食材' })).toBeTruthy();
  expect(screen.getByRole('link', { name: '取引詳細へ戻る' }).getAttribute('href')).toBe(detailHref(record.id));
  expect(screen.getByRole('link', { name: '取引履歴' }).getAttribute('aria-current')).toBe('page');
});

it('shows a missing state without a delete action for an unknown deletion URL', () => {
  window.location.hash = '#transaction/unknown/delete';
  render(<App />);
  expect(screen.getByRole('heading', { level: 1, name: '取引が見つかりません' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: '削除する' })).toBeNull();
});

it('returns focus to the original transaction row', async () => {
  window.location.hash = '#transactions';
  render(<App />);
  fireEvent.click(screen.getByRole('link', { name: '食材' }));
  await waitFor(() => expect(screen.getByRole('heading', { name: '食材' })).toBeTruthy());
  fireEvent.click(screen.getByRole('link', { name: '取引履歴へ戻る' }));
  await waitFor(() => expect(document.activeElement?.textContent).toBe('食材'));
});
