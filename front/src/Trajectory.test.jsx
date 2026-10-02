import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('./TrajectoryMap.jsx', () => ({ default: ({ day, selectedEventId }) => <div data-testid="map-props">{day.date} {selectedEventId}</div> }));

afterEach(cleanup);

it('shows the selected sample date and summary before the map and timeline', async () => {
  const { default: Trajectory } = await import('./Trajectory.jsx');
  const { container } = render(<Trajectory />);
  expect(screen.getByRole('heading', { level: 1, name: '生活軌跡' })).toBeTruthy();
  expect(screen.getByText(/2026年9月のサンプル/)).toBeTruthy();
  expect(screen.getByRole('combobox', { name: '表示する日付' }).value).toBe('2026-09-01');
  expect(screen.getByText('3地点')).toBeTruthy();
  expect(container.querySelector('.trajectory-summary').compareDocumentPosition(container.querySelector('.trajectory-map-panel')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect((await screen.findByTestId('map-props')).textContent).toContain('2026-09-01');
  expect(screen.getByRole('heading', { name: '時系列' })).toBeTruthy();
});

it('keeps the date within September and shows only the final selection', async () => {
  const { default: Trajectory } = await import('./Trajectory.jsx');
  render(<Trajectory />);
  const previous = screen.getByRole('button', { name: '前の日' });
  const next = screen.getByRole('button', { name: '次の日' });
  const select = screen.getByRole('combobox', { name: '表示する日付' });
  expect(previous.disabled).toBe(true);
  fireEvent.click(next);
  expect(select.value).toBe('2026-09-02');
  fireEvent.change(select, { target: { value: '2026-09-30' } });
  expect(next.disabled).toBe(true);
  fireEvent.change(select, { target: { value: '2026-09-15' } });
  fireEvent.change(select, { target: { value: '2026-09-21' } });
  expect(select.value).toBe('2026-09-21');
  expect(screen.getByText('Found MUJI 青山')).toBeTruthy();
  expect(screen.queryByText('無印良品 アトレ恵比寿')).toBeNull();
  await waitFor(() => expect(screen.getByTestId('map-props').textContent).toContain('2026-09-21'));
});

it('selects a timeline stop while retaining controls when the map is unavailable', async () => {
  const { default: Trajectory } = await import('./Trajectory.jsx');
  render(<Trajectory />);
  fireEvent.click(screen.getByRole('button', { name: /13:05.*無印良品 渋谷公園通り/ }));
  await waitFor(() => expect(screen.getByTestId('map-props').textContent).toContain('2026-09-01-2'));
  expect(screen.getByRole('combobox', { name: '表示する日付' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: '時系列' })).toBeTruthy();
});

it('pairs each timeline leg with its map stage color without a time range', async () => {
  const { default: Trajectory } = await import('./Trajectory.jsx');
  const { container } = render(<Trajectory />);
  expect([...container.querySelectorAll('.trajectory-leg-label')].map((element) => element.textContent)).toEqual([
    '区間1 · 徒歩（推定） · 約0.5 km',
    '区間2 · 徒歩（推定） · 約1.1 km',
  ]);
  expect([...container.querySelectorAll('.trajectory-stage-key')].map((element) => element.textContent)).toEqual([
    '区間1',
    '区間2',
  ]);
  expect(screen.getByRole('button', { name: /09:10.*スターバックス コーヒー 渋谷フクラス店/ })).toBeTruthy();
});
