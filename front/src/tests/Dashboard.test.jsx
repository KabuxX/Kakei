import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import Dashboard from '../pages/Dashboard.jsx';
import { dashboardForMonth } from '../lib/dashboard.js';

afterEach(cleanup);

const month = new Date(2026, 8, 1);
const records = [
  { id: 'pay', title: '給与', category: '収入', date: '2026-09-28', type: 'income', amount: 300000 },
  { id: 'food', title: '食材', category: '食費', date: '2026-09-27', type: 'expense', amount: 1200 },
];

it('shows the selected month, balance, and first action', () => {
  render(<Dashboard month={month} model={dashboardForMonth(records, month)} transactions={records} status="ready" onMonthChange={vi.fn()} onAdd={vi.fn()} />);
  expect(screen.getByText('2026年9月')).toBeTruthy();
  expect(screen.getByText('¥298,800')).toBeTruthy();
  expect(screen.getByRole('button', { name: '前の月' })).toBeTruthy();
});

it('filters rows while leaving the month total intact', () => {
  render(<Dashboard month={month} model={dashboardForMonth(records, month)} transactions={records} status="ready" onMonthChange={vi.fn()} onAdd={vi.fn()} />);
  fireEvent.change(screen.getByPlaceholderText('取引を検索'), { target: { value: '食材' } });
  expect(screen.getByRole('link', { name: '食材' })).toBeTruthy();
  expect(screen.queryByRole('link', { name: '給与' })).toBeNull();
  expect(screen.getByText('¥298,800')).toBeTruthy();
});

it('switches transaction type without changing the summary', () => {
  render(<Dashboard month={month} model={dashboardForMonth(records, month)} transactions={records} status="ready" onMonthChange={vi.fn()} onAdd={vi.fn()} />);
  fireEvent.change(screen.getByRole('combobox', { name: '取引種別' }), { target: { value: 'expense' } });
  expect(screen.getByRole('link', { name: '食材' })).toBeTruthy();
  expect(screen.queryByRole('link', { name: '給与' })).toBeNull();
  expect(screen.getByText('¥298,800')).toBeTruthy();
});

it('shows finite meters and excess amounts with all budgets zero',()=>{
  const budgets={'食費':0,'住まい':0,'日用品':0,'交通':0,'娯楽':0,'その他':0};
  const view=render(<Dashboard month={month} model={dashboardForMonth(records,month,budgets)} status="ready" budgetStatus="ready" onMonthChange={vi.fn()}/>);
  expect(screen.getByRole('meter',{name:'食費の予算使用率'}).getAttribute('aria-valuenow')).toBe('100');
  expect(screen.getByRole('meter',{name:'住まいの予算使用率'}).getAttribute('aria-valuenow')).toBe('0');
  expect(document.getElementById('remaining-budget').textContent).toBe('−¥1,200');
  expect(screen.getAllByText('¥1,200 超過').length).toBeGreaterThan(0);
  expect(view.container.innerHTML).not.toMatch(/NaN|Infinity/);
});
