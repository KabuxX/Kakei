import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import AppShell from './AppShell.jsx';

afterEach(cleanup);

it('hides and restores the sidebar while keeping the choice across in-app navigation', () => {
  const onAdd = vi.fn();
  const view = (route) => <AppShell route={route} onAdd={onAdd} addDisabled={false}><p>内容</p></AppShell>;
  const { rerender } = render(view('#overview'));

  const hide = screen.getByRole('button', { name: 'サイドバーを隠す' });
  expect(hide.getAttribute('aria-expanded')).toBe('true');
  expect(hide.textContent).toBe('');
  expect(hide.querySelector('svg use')).toBeTruthy();
  fireEvent.click(hide);

  const show = screen.getByRole('button', { name: 'サイドバーを表示' });
  expect(show.getAttribute('aria-expanded')).toBe('false');
  expect(show.textContent).toBe('');
  rerender(view('#transactions'));
  expect(screen.getByRole('button', { name: 'サイドバーを表示' })).toBeTruthy();
  fireEvent.click(show);
  expect(screen.getByRole('button', { name: 'サイドバーを隠す' }).getAttribute('aria-expanded')).toBe('true');
});
