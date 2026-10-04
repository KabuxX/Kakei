import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import AppShell from '../components/layout/AppShell.jsx';

afterEach(cleanup);

it('offers overview and trajectory and agent as the three main destinations', () => {
  const { rerender } = render(<AppShell route="#overview" onAdd={vi.fn()} addDisabled={false}><p>内容</p></AppShell>);
  const navigation = screen.getByRole('navigation', { name: 'メインナビゲーション' });
  const links = [...navigation.querySelectorAll('a')];
  expect(links.map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
    ['概要', '#overview'],
    ['軌跡', '#trajectory'],
    ['Agent Chat', '#agent'],
  ]);
  rerender(<AppShell route="#trajectory" onAdd={vi.fn()} addDisabled={false}><p>内容</p></AppShell>);
  expect(screen.getByRole('link', { name: '軌跡' }).getAttribute('aria-current')).toBe('page');
  expect(screen.getByText('軌跡', { selector: '#current-page-label' })).toBeTruthy();
});

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
