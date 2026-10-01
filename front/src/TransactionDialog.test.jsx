import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import TransactionDialog from './TransactionDialog.jsx';

afterEach(cleanup);

const props = { open: true, selectedMonth: new Date(2026, 8, 1), busy: false, onClose: vi.fn(), onSubmit: vi.fn().mockResolvedValue(true) };

it('keeps the manual amount when item rows are added then removed', () => {
  render(<TransactionDialog {...props} />);
  const amount = screen.getByRole('spinbutton', { name: /金額/ });
  fireEvent.change(amount, { target: { value: '500' } });
  fireEvent.click(screen.getByRole('button', { name: '＋ 品目を追加' }));
  expect(amount.readOnly).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: /品目1を削除/ }));
  expect(amount.value).toBe('500');
  expect(amount.readOnly).toBe(false);
});

it('validates expense fields and focuses the first error', async () => {
  const onSubmit = vi.fn();
  render(<TransactionDialog {...props} onSubmit={onSubmit} />);
  fireEvent.click(screen.getByRole('button', { name: '追加する' }));
  await waitFor(() => expect(screen.getByText('内容を入力してください。')).toBeTruthy());
  expect(document.activeElement?.getAttribute('name')).toBe('title');
  expect(onSubmit).not.toHaveBeenCalled();
});

it('submits income without expense fields', async () => {
  const onSubmit = vi.fn().mockResolvedValue(true);
  render(<TransactionDialog {...props} onSubmit={onSubmit} />);
  fireEvent.click(screen.getByRole('radio', { name: '収入' }));
  fireEvent.change(screen.getByRole('textbox', { name: /内容/ }), { target: { value: '給与' } });
  fireEvent.change(screen.getByRole('spinbutton', { name: /金額/ }), { target: { value: '1000' } });
  fireEvent.click(screen.getByRole('button', { name: '追加する' }));
  await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ title: '給与', type: 'income', amount: 1000, category: '収入' })));
});
