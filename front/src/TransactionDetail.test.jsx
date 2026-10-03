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
  expect(screen.getByRole('link', { name: '取引を削除' }).getAttribute('href')).toBe('#transaction/a%2Fb%20%25%E6%97%A5%E6%9C%AC%E8%AA%9E/delete');
});

it('shows a missing state for an unknown detail ID', () => {
  render(<TransactionDetail record={null} onDelete={vi.fn()} />);
  expect(screen.getByRole('heading', { name: '取引が見つかりません' })).toBeTruthy();
});

it('shows estimated and entered times distinctly', () => {
  const record = {
    id: 'legacy-income', title: '給与', type: 'income', date: '2026-10-03T09:17',
    category: '収入', amount: 1000, timeEstimated: true,
  };
  const { rerender } = render(<TransactionDetail record={record} />);
  expect(screen.getByText('2026年10月3日 09:17')).toBeTruthy();
  expect(screen.getByText('時刻は仮設定')).toBeTruthy();

  rerender(<TransactionDetail record={{ ...record, timeEstimated: false }} />);
  expect(screen.getByText('2026年10月3日 09:17')).toBeTruthy();
  expect(screen.queryByText('時刻は仮設定')).toBeNull();
});

it('opens an approved receipt from its transaction',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,status:200,json:async()=>({receipts:[{id:'r',mimeType:'image/png'}]})})));
 render(<TransactionDetail record={{id:'t',title:'食材',type:'expense',date:'2026-10-03T12:00',amount:100,category:'食費'}}/>);
 expect((await screen.findByRole('link',{name:'レシート 1 を開く'})).getAttribute('href')).toBe('/api/receipts/r');
 vi.unstubAllGlobals();
});
