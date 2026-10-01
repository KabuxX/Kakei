import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import TransactionDetail from './TransactionDetail.jsx';

afterEach(cleanup);

it('shows a direct detail link for an old expense without inventing fields', () => {
  render(<TransactionDetail record={{ id: 'a/b %日本語', title: '食材', type: 'expense', date: '2026-09-27', category: '食費', amount: 1200 }} onDelete={vi.fn()} />);
  expect(screen.getByRole('heading', { name: '食材' })).toBeTruthy();
  expect(screen.getAllByText('未登録')).toHaveLength(2);
  expect(screen.getByText('品目は登録されていません')).toBeTruthy();
  expect(screen.getByRole('link', { name: '取引履歴へ戻る' }).getAttribute('href')).toBe('#transactions');
});

it('shows a missing state for an unknown detail ID', () => {
  render(<TransactionDetail record={null} onDelete={vi.fn()} />);
  expect(screen.getByRole('heading', { name: '取引が見つかりません' })).toBeTruthy();
});
