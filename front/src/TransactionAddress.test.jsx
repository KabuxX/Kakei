import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import TransactionDetail from './TransactionDetail.jsx';

const record = { id: 'purchase', type: 'expense', title: 'コーヒー', merchant: 'カフェ', amount: 250, category: '食費', date: '2026-10-02T12:19' };
const address = '〒810-0001 福岡県福岡市中央区天神2-11-3 駅ビル地下1階';
const timeline = { places: { shop: { name: 'カフェ 西鉄福岡駅店', address, coordinates: [130.3990083, 33.5900778] }, other: { name: 'カフェ', address: '別支店の住所', coordinates: [139, 35] } }, days: [{ date: '2026-10-02', events: [{ transactionId: 'another', placeId: 'other' }, { transactionId: 'purchase', placeId: 'shop' }, { transactionId: 'purchase', placeId: 'shop' }] }] };
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
function mockFetch(getTimeline) {
  vi.stubGlobal('fetch', vi.fn((url) => url.startsWith('/api/transaction-addresses/') ? getTimeline(url).then(async result => { const body=await result.json(); if(!result.ok) return result; const ids=new Set((body.days||[]).flatMap(d=>d.events||[]).filter(e=>e.transactionId===decodeURIComponent(url.split('/').at(-1))).map(e=>e.placeId)); return response({address:{transactionId:decodeURIComponent(url.split('/').at(-1)),places:[...ids].map(id=>({...body.places[id],placeId:id,status:'trajectory_only'}))}}); }) : Promise.resolve(response({ receipts: [] }))));
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('shows the full address linked by transaction ID once, underneath the merchant', async () => {
  mockFetch(async () => response(timeline));
  render(<TransactionDetail record={record} />);
  expect(await screen.findByText(address)).toBeTruthy();
  expect(screen.getAllByText(address)).toHaveLength(1);
  expect(screen.queryByText('別支店の住所')).toBeNull();
  expect(screen.queryByRole('link', { name: /地図で見る/ })).toBeNull();
  expect(document.querySelector('#detail-merchant').parentElement.textContent).toContain(address);
  expect(fetch).toHaveBeenCalledWith('/api/transaction-addresses/purchase', expect.anything());
});

it('hides missing addresses and does not guess a match from the merchant name', async () => {
  mockFetch(async () => response({ ...timeline, days: [{ date: '2026-10-02', events: [{ transactionId: 'another', placeId: 'other' }] }] }));
  const { rerender } = render(<TransactionDetail record={record} />);
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/transaction-addresses/purchase', expect.anything()));
  expect(screen.queryByText('住所')).toBeNull();
  mockFetch(async () => response({ error: { message: '軌跡なし' } }, 404));
  rerender(<TransactionDetail record={{ ...record, id: 'missing' }} />);
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/transaction-addresses/missing', expect.anything()));
  expect(screen.queryByText('住所')).toBeNull();
  expect(await screen.findByText(/住所を読み込めません/)).toBeTruthy();
});

it('shows an address without a map link when coordinates are unavailable, and supports retry', async () => {
  let fail = true;
  mockFetch(async () => fail ? response({ error: { message: 'offline' } }, 503) : response({ ...timeline, places: { shop: { name: 'カフェ', address } } }));
  render(<TransactionDetail record={record} />);
  expect(await screen.findByText('住所を読み込めませんでした。')).toBeTruthy();
  fail = false;
  fireEvent.click(screen.getByRole('button', { name: '再読み込み' }));
  expect(await screen.findByText(address)).toBeTruthy();
  expect(screen.queryByRole('link', { name: /地図で見る/ })).toBeNull();
});

it('does not display a previous transaction address after switching records', async () => {
  let finish;
  mockFetch(() => new Promise(resolve => { finish = resolve; }));
  const { rerender } = render(<TransactionDetail record={record} />);
  const oldRequest = finish;
  rerender(<TransactionDetail record={{ ...record, id: 'different', date: '2026-10-03T10:00' }} />);
  await act(async () => {
    oldRequest(response(timeline));
    finish(response({ places: {}, days: [] }));
  });
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/transaction-addresses/different', expect.anything()));
  expect(screen.queryByText(address)).toBeNull();
});

it('shows only the direct address without address actions or linked-address labels',async()=>{
 mockFetch(async()=>response(timeline));
 render(<TransactionDetail record={{...record,merchantAddress:'取引住所'}} onSaveAddress={vi.fn()} onReviewAddress={vi.fn()}/>);
 expect(screen.getByText('取引住所')).toBeTruthy();
 expect(screen.queryByText(address)).toBeNull();
 expect(screen.queryByText('軌跡に保存された住所')).toBeNull();
 expect(screen.queryByRole('link',{name:/地図で見る/})).toBeNull();
 expect(screen.queryByRole('button',{name:/住所/})).toBeNull();
 expect(screen.getByRole('link',{name:'編集'}).getAttribute('href')).toBe('#transaction/purchase/edit');
});
