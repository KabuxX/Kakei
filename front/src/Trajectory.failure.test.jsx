import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

vi.mock('./TrajectoryMap.jsx', () => { throw new Error('map chunk unavailable'); });
afterEach(cleanup);

it('keeps date controls and timeline usable when the map module cannot load', async () => {
  const { default: Trajectory } = await import('./Trajectory.jsx');
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
  try {
    render(<Trajectory />);
    expect(await screen.findByText(/地図を読み込めません/)).toBeTruthy();
    const select = screen.getByRole('combobox', { name: '表示する日付' });
    fireEvent.change(select, { target: { value: '2026-09-29' } });
    expect(select.value).toBe('2026-09-29');
    expect(screen.getByText('JR恵比寿駅')).toBeTruthy();
    expect(screen.getByRole('heading', { name: '時系列' })).toBeTruthy();
  } finally {
    consoleError.mockRestore();
  }
});
