import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { buildTrajectoryDays } from './lib/trajectory-model.js';

const mocks = vi.hoisted(() => ({ maps: [], overlays: [] }));
vi.mock('mapbox-gl', () => ({
  default: {
    supported: vi.fn(() => true),
    Map: class {
      constructor(options) { this.options = options; this.controls = []; this.handlers = {}; this.fitBounds = vi.fn(); this.remove = vi.fn(); mocks.maps.push(this); }
      addControl(control) { this.controls.push(control); }
      on(name, callback) { this.handlers[name] = callback; }
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

beforeEach(() => { vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', 'pk.test-token'); mocks.maps.length = 0; mocks.overlays.length = 0; });
afterEach(() => { cleanup(); vi.unstubAllEnvs(); });

it('creates one map and overlay, fits each date, and releases the map', async () => {
  const { default: TrajectoryMap } = await import('./TrajectoryMap.jsx');
  const onSelectEvent = vi.fn();
  const view = render(<TrajectoryMap day={days.get('2026-09-01')} selectedEventId={null} onSelectEvent={onSelectEvent} />);
  expect(mocks.maps).toHaveLength(1);
  expect(mocks.overlays).toHaveLength(1);
  expect(mocks.maps[0].controls).toContain(mocks.overlays[0]);
  expect(mocks.maps[0].fitBounds).toHaveBeenCalled();
  view.rerender(<TrajectoryMap day={days.get('2026-09-02')} selectedEventId="2026-09-02-b" onSelectEvent={onSelectEvent} />);
  expect(mocks.maps).toHaveLength(1);
  expect(mocks.overlays[0].setProps).toHaveBeenCalled();
  const lastLayers = mocks.overlays[0].setProps.mock.lastCall[0].layers;
  expect(lastLayers[0].props.data).toBe(days.get('2026-09-02').segments);
  lastLayers[1].props.onClick({ object: days.get('2026-09-02').events[1] });
  expect(onSelectEvent).toHaveBeenCalledWith('2026-09-02-b');
  view.unmount();
  expect(mocks.maps[0].remove).toHaveBeenCalledOnce();
});

it('invalidates actual deck.gl marker attributes when selection changes', async () => {
  const { default: TrajectoryMap } = await import('./TrajectoryMap.jsx');
  const day = days.get('2026-09-01');
  const view = render(<TrajectoryMap day={day} selectedEventId={null} onSelectEvent={vi.fn()} />);
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
  const { default: TrajectoryMap } = await import('./TrajectoryMap.jsx');
  vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', '');
  const missing = render(<TrajectoryMap day={days.get('2026-09-01')} onSelectEvent={vi.fn()} />);
  expect(screen.getByText(/Mapbox.*トークン/)).toBeTruthy();
  missing.unmount();
  vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', 'pk.test-token');
  const mapbox = (await import('mapbox-gl')).default;
  mapbox.supported.mockReturnValueOnce(false);
  const unsupported = render(<TrajectoryMap day={days.get('2026-09-01')} onSelectEvent={vi.fn()} />);
  expect(screen.getByText(/WebGL/)).toBeTruthy();
  unsupported.unmount();
  render(<TrajectoryMap day={days.get('2026-09-01')} onSelectEvent={vi.fn()} />);
  mocks.maps.at(-1).handlers.error(new Error('tile failed'));
  expect(await screen.findByText(/地図を読み込めません/)).toBeTruthy();
});
