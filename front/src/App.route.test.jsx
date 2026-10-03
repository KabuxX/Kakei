import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App.jsx';
import { useTransactions } from './useTransactions.js';
import { detailHref } from './lib/transaction-detail.js';
import transactions from './data/september-transactions.json';
import { trajectoryResponse } from './trajectory-test-fixture.js';

vi.mock('./useTransactions.js', () => ({ useTransactions: vi.fn() }));
const record = { id: 'a/b %日本語', title: '食材', type: 'expense', date: '2026-09-27', category: '食費', amount: 1200 };

beforeEach(() => {
  useTransactions.mockReturnValue({ transactions: [record], status: 'ready', error: null, writePending: false, load: vi.fn(), refresh: vi.fn(), addTransaction: vi.fn(), deleteTransaction: vi.fn(), deleteSamples: vi.fn() });
  window.scrollTo = vi.fn();
});
afterEach(() => { cleanup(); window.location.hash = ''; vi.unstubAllGlobals(); });

it('opens an encoded direct detail URL within the overview destination', () => {
  window.location.hash = detailHref(record.id);
  render(<App />);
  expect(screen.getByRole('heading', { name: '食材' })).toBeTruthy();
  expect(screen.getByRole('link', { name: '概要' }).getAttribute('aria-current')).toBe('page');
});

it('opens a direct deletion URL for an ID containing reserved characters', () => {
  window.location.hash = '#transaction/a%2Fb%20%25%E6%97%A5%E6%9C%AC%E8%AA%9E/delete';
  render(<App />);
  expect(screen.getByRole('heading', { name: 'この取引を削除しますか？' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: '食材' })).toBeTruthy();
  expect(screen.getByRole('link', { name: '取引詳細へ戻る' }).getAttribute('href')).toBe(detailHref(record.id));
  expect(screen.getByRole('link', { name: '概要' }).getAttribute('aria-current')).toBe('page');
});

it('opens saved trajectory data from its direct URL', async () => {
  vi.stubGlobal('fetch', vi.fn(trajectoryResponse));
  useTransactions.mockReturnValue({ transactions, status: 'ready', refresh: vi.fn() });
  window.location.hash = '#trajectory';
  render(<App />);
  expect(document.title).toBe('軌跡 | Kakei');
  expect(screen.getByRole('link', { name: '軌跡' }).getAttribute('aria-current')).toBe('page');
  expect(document.getElementById('dashboard-view').hidden).toBe(true);
  expect(screen.getByRole('heading', { level: 1, name: '生活軌跡' })).toBeTruthy();
  expect((await screen.findByRole('combobox', { name: '表示する日付' })).value).toBe('2026-09-19');
  expect(await screen.findByRole('heading', { name: '時系列' })).toBeTruthy();
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
