import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import transactions from './data/september-transactions.json';
import { trajectoryResponse } from './trajectory-test-fixture.js';
import Trajectory from './Trajectory.jsx';

vi.mock('./TrajectoryMap.jsx', () => ({ default: ({ day, selectedEventId }) => <div data-testid="map-props">{day.date} {selectedEventId}</div> }));
beforeEach(() => vi.stubGlobal('fetch', vi.fn(trajectoryResponse)));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('test_trajectory_fetches_selected_day', async () => {
  const { container } = render(<Trajectory transactions={transactions} />);
  const select = await screen.findByRole('combobox', { name: '表示する日付' });
  expect(select.value).toBe('2026-09-19');
  expect(await screen.findByText('3地点')).toBeTruthy();
  expect(container.querySelector('.trajectory-summary').compareDocumentPosition(container.querySelector('.trajectory-map-panel')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  fireEvent.change(select, { target: { value: '2026-09-29' } });
  expect(await screen.findByText('JR恵比寿駅')).toBeTruthy();
  expect(fetch.mock.calls.map(([path]) => path)).toContain('/api/trajectory/2026-09-29');
});

it('test_trajectory_retry_after_api_failure', async () => {
  fetch.mockRejectedValueOnce(new Error('接続に失敗しました'));
  render(<Trajectory transactions={transactions} />);
  expect(await screen.findByRole('alert')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '再読み込み' }));
  expect(await screen.findByText('3地点')).toBeTruthy();
});

it('selects a timeline stop and pairs legs with map stage colors', async () => {
  const { container } = render(<Trajectory transactions={transactions} />);
  fireEvent.click(await screen.findByRole('button', { name: /13:05.*無印良品 渋谷公園通り/ }));
  await waitFor(() => expect(screen.getByTestId('map-props').textContent).toContain('2026-09-19-2'));
  expect([...container.querySelectorAll('.trajectory-stage-key')].map((element) => element.textContent)).toEqual(['区間1', '区間2']);
});

it('shows empty saved days and arbitrary years', async () => {
  vi.stubGlobal('fetch', vi.fn(async (path) => ({ ok: true, status: 200, json: async () => path === '/api/trajectory'
    ? { dates: ['2027-01-04'] } : { places: {}, days: [{ date: '2027-01-04', events: [], legs: [] }] } })));
  render(<Trajectory transactions={[]} />);
  expect(await screen.findByText('2027年1月4日')).toBeTruthy();
  expect(await screen.findByText('この日の訪問地点はまだありません。')).toBeTruthy();
});

it('renders a single unknown-time user coordinate without a source link',async()=>{
 vi.stubGlobal('fetch',vi.fn(async url=>({ok:true,status:200,json:async()=>url==='/api/trajectory'?{dates:['2027-01-04']}:{places:{p:{name:'手動の地点',address:null,sourceUrl:null,placeEvidence:'user',coordinates:[-73,40]}},days:[{date:'2027-01-04',events:[{id:'e',placeId:'p',time:null,timeEvidence:'unknown'}],legs:[]}]}})));
 render(<Trajectory transactions={[]}/>);
 expect(await screen.findByText('手動の地点')).toBeTruthy();
 expect(screen.getByText(/時刻不明/)).toBeTruthy();expect(screen.queryByRole('link',{name:/地点の出典/})).toBeNull();
});
it('trajectory_shows_store_and_coordinate_evidence',async()=>{
 vi.stubGlobal('fetch',vi.fn(async url=>({ok:true,status:200,json:async()=>url==='/api/trajectory'?{dates:['2027-01-04']}:{places:{p:{name:'店舗',address:'福岡市',sourceUrl:'https://example.com/store',coordinates:[130,33],sources:[{id:'s',title:'店舗案内',url:'https://example.com/store'}],geocoding:{provider:'mapbox',accuracy:'interpolated'}}},days:[{date:'2027-01-04',events:[{id:'e',placeId:'p',time:null,timeEvidence:'unknown'}],legs:[]}]}})));
 render(<Trajectory transactions={[]}/>);
 expect((await screen.findByRole('link',{name:/店舗情報/})).getAttribute('href')).toBe('https://example.com/store');
 expect(screen.getByText(/座標.*Mapbox.*補間/)).toBeTruthy();
});
