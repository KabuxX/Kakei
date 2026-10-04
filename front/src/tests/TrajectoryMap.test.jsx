import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { buildTrajectoryDays } from '../lib/trajectory-model.js';
import transactionsFixture from '../data/september-transactions.json';
import timelineFixture from '../data/september-timeline.json';

import {request} from '../lib/api.js';
vi.mock('../lib/api.js');
const mocks = vi.hoisted(() => ({ maps: [], overlays: [], markers: [] }));
vi.mock('mapbox-gl', () => ({
  default: {
    supported: vi.fn(() => true),
    Map: class {
      constructor(options) { this.options = options; this.controls = []; this.handlers = {}; this.fitBounds = vi.fn(); this.remove = vi.fn(); mocks.maps.push(this); }
      addControl(control) { this.controls.push(control); }
      on(name, callback) { this.handlers[name] = callback; }
      off(name) { delete this.handlers[name]; }
      getBearing() { return 0; }
    },
    Marker: class {
      constructor(options) { this.options = options; this.remove = vi.fn(); mocks.markers.push(this); }
      setLngLat(coordinates) { this.coordinates = coordinates; return this; }
      addTo(map) { this.map = map; return this; }
    },
  },
}));
vi.mock('@deck.gl/mapbox', () => ({
  MapboxOverlay: class {
    constructor(options) { this.options = options; this.setProps = vi.fn(); mocks.overlays.push(this); }
  },
}));

const places = {
  a: { name: 'A店', address: '東京都渋谷区', coordinates: [139.7, 35.65], sourceUrl: 'https://example.com/a' },
  b: { name: 'B店', address: '東京都渋谷区', coordinates: [139.71, 35.66], sourceUrl: 'https://example.com/b' },
};
const transactions = [
  { id: 'a', date: '2026-09-01', type: 'expense', category: '食費', amount: 100, merchant: 'A店', items: [{ name: 'A', amount: 100 }] },
  { id: 'b', date: '2026-09-02', type: 'expense', category: '食費', amount: 200, merchant: 'B店', items: [{ name: 'B', amount: 200 }] },
];
const days = buildTrajectoryDays(transactions, { places, days: [1, 2].map((number) => {
  const date = `2026-09-0${number}`;
  return { date, events: [
    { id: `${date}-a`, time: '09:00', placeId: 'a', transactionId: number === 1 ? 'a' : undefined },
    { id: `${date}-b`, time: '10:00', placeId: 'b', transactionId: number === 2 ? 'b' : undefined },
  ], legs: [{ fromEventId: `${date}-a`, toEventId: `${date}-b`, modeHint: 'walk' }] };
}) });

beforeEach(() => { request.mockReset(); request.mockResolvedValue({mapboxPublicToken:'pk.test-token'}); vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', 'pk.test-token'); mocks.maps.length = 0; mocks.overlays.length = 0; mocks.markers.length = 0; });
afterEach(() => { cleanup(); vi.unstubAllEnvs(); });

it('creates one map and overlay, fits each date, and releases the map', async () => {
  const { default: TrajectoryMap } = await import('../components/trajectory/TrajectoryMap.jsx');
  const onSelectEvent = vi.fn();
  const view = render(<TrajectoryMap day={days.get('2026-09-01')} selectedEventId={null} onSelectEvent={onSelectEvent} />);
  await waitFor(()=>expect(mocks.maps).toHaveLength(1));
  expect(mocks.overlays).toHaveLength(1);
  expect(mocks.maps[0].controls).toContain(mocks.overlays[0]);
  expect(mocks.maps[0].fitBounds).toHaveBeenCalled();
  mocks.maps[0].handlers.resize();
  expect(mocks.maps[0].fitBounds).toHaveBeenCalledTimes(2);
  view.rerender(<TrajectoryMap day={days.get('2026-09-02')} selectedEventId="2026-09-02-b" onSelectEvent={onSelectEvent} />);
  await waitFor(()=>expect(mocks.maps).toHaveLength(1));
  expect(mocks.overlays[0].setProps).toHaveBeenCalled();
  expect(mocks.markers.slice(0, 2).every((marker) => marker.remove.mock.calls.length === 1)).toBe(true);
  const lastLayers = mocks.overlays[0].setProps.mock.lastCall[0].layers;
  expect(lastLayers[0].props.data).toBe(days.get('2026-09-02').segments);
  lastLayers[1].props.onClick({ object: days.get('2026-09-02').events[1] });
  expect(onSelectEvent).toHaveBeenCalledWith('2026-09-02-b');
  view.unmount();
  expect(mocks.maps[0].remove).toHaveBeenCalledOnce();
  expect(mocks.markers.at(-1).remove).toHaveBeenCalledOnce();
});

it('configures Mapbox Standard with Japanese Noto Sans CJK JP labels', async () => {
  const { default: TrajectoryMap } = await import('../components/trajectory/TrajectoryMap.jsx');
  render(<TrajectoryMap day={days.get('2026-09-01')} selectedEventId={null} onSelectEvent={vi.fn()} />);
  await waitFor(()=>expect(mocks.maps).toHaveLength(1));
  expect(mocks.maps[0].options.style).toBe('mapbox://styles/mapbox/standard');
  expect(mocks.maps[0].options.config).toEqual({ basemap: { font: 'Noto Sans CJK JP' } });
  expect(mocks.maps[0].options.localIdeographFontFamily).toBe(false);
  expect(mocks.maps[0].options.language).toBe('ja');
});

it('shows distinct stage colors without direction or time annotations', async () => {
  const { default: TrajectoryMap } = await import('../components/trajectory/TrajectoryMap.jsx');
  const day = buildTrajectoryDays(transactionsFixture, timelineFixture).get('2026-09-29');
  render(<TrajectoryMap day={day} selectedEventId={null} onSelectEvent={vi.fn()} />);
  await waitFor(()=>expect(mocks.maps).toHaveLength(1));
  const layers = mocks.overlays[0].setProps.mock.lastCall[0].layers;
  const paths = layers.find((layer) => layer.id === 'trajectory-paths');
  expect(new Set(day.segments.map((segment) => paths.props.getColor(segment).join(','))).size).toBe(day.segments.length);
  expect(mocks.markers.filter((marker) => marker.options.element.className === 'trajectory-map-stage')).toHaveLength(0);
  expect(mocks.markers.filter((marker) => marker.options.element.className === 'trajectory-map-stop-number')).toHaveLength(day.events.length);
});

it('invalidates actual deck.gl marker attributes when selection changes', async () => {
  const { default: TrajectoryMap } = await import('../components/trajectory/TrajectoryMap.jsx');
  const day = days.get('2026-09-01');
  const view = render(<TrajectoryMap day={day} selectedEventId={null} onSelectEvent={vi.fn()} />);
  await waitFor(()=>expect(mocks.maps).toHaveLength(1));
  const previous = mocks.overlays[0].setProps.mock.lastCall[0].layers[1];
  view.rerender(<TrajectoryMap day={day} selectedEventId={day.events[1].id} onSelectEvent={vi.fn()} />);
  const next = mocks.overlays[0].setProps.mock.lastCall[0].layers[1];
  expect(next.props.data).toBe(previous.props.data);
  expect(next.props.updateTriggers.getFillColor).not.toEqual(previous.props.updateTriggers.getFillColor);
  expect(next.props.updateTriggers.getRadius).not.toEqual(previous.props.updateTriggers.getRadius);
  expect(next.props.getFillColor(day.events[1])).not.toEqual(previous.props.getFillColor(day.events[1]));
  expect(mocks.maps[0].fitBounds).toHaveBeenCalledOnce();
});

it('shows setup, WebGL, and map error messages', async () => {
  const { default: TrajectoryMap } = await import('../components/trajectory/TrajectoryMap.jsx');
  request.mockResolvedValueOnce({mapboxPublicToken:null});
  const missing = render(<TrajectoryMap day={days.get('2026-09-01')} onSelectEvent={vi.fn()} />);
  expect(await screen.findByText(/Mapbox.*トークン/)).toBeTruthy();
  missing.unmount();
  vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', 'pk.test-token');
  const mapbox = (await import('mapbox-gl')).default;
  mapbox.supported.mockReturnValueOnce(false);
  const unsupported = render(<TrajectoryMap day={days.get('2026-09-01')} onSelectEvent={vi.fn()} />);
  expect(await screen.findByText(/WebGL/)).toBeTruthy();
  unsupported.unmount();
  render(<TrajectoryMap day={days.get('2026-09-01')} onSelectEvent={vi.fn()} />);
  await waitFor(()=>expect(mocks.maps).toHaveLength(1));
  mocks.maps.at(-1).handlers.error(new Error('tile failed'));
  expect(await screen.findByText(/地図を読み込めません/)).toBeTruthy();
});

it('waits for runtime configuration then draws paths and stops without a build token',async()=>{
  vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN','');
  const {request}=await import('../lib/api.js');
  let resolve;request.mockReturnValueOnce(new Promise(done=>{resolve=done;}));
  const {default:TrajectoryMap}=await import('../components/trajectory/TrajectoryMap.jsx');
  const day=days.get('2026-09-01');
  render(<TrajectoryMap day={day} onSelectEvent={vi.fn()}/>);
  expect(screen.getByText('地図の設定を読み込み中…')).toBeTruthy();
  expect(mocks.maps).toHaveLength(0);
  await act(async()=>resolve({mapboxPublicToken:'pk.runtime-test'}));
  expect(mocks.maps[0].options.accessToken).toBe('pk.runtime-test');
  expect(mocks.overlays[0].setProps.mock.lastCall[0].layers[0].props.data).toBe(day.segments);
  expect(mocks.markers).toHaveLength(day.events.length);
  expect(mocks.maps[0].fitBounds).toHaveBeenCalledOnce();
});
it('can retry configuration failure and ignores a response after unmount',async()=>{
  const {request}=await import('../lib/api.js');
  request.mockRejectedValueOnce(new Error('offline'));
  const {default:TrajectoryMap}=await import('../components/trajectory/TrajectoryMap.jsx');
  const view=render(<TrajectoryMap day={days.get('2026-09-01')} onSelectEvent={vi.fn()}/>);
  fireEvent.click(await screen.findByRole('button',{name:'地図の設定を再取得'}));
  await waitFor(()=>expect(mocks.maps).toHaveLength(1));
  view.unmount();
  let resolve;request.mockReturnValueOnce(new Promise(done=>{resolve=done;}));
  const late=render(<TrajectoryMap day={days.get('2026-09-01')} onSelectEvent={vi.fn()}/>);
  late.unmount();await act(async()=>resolve({mapboxPublicToken:'pk.late'}));
  await waitFor(()=>expect(mocks.maps).toHaveLength(1));
});
