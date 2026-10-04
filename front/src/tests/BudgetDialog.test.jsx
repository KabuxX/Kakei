import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import BudgetDialog from '../components/budget/BudgetDialog.jsx';
const categories={'食費':60000,'住まい':90000,'日用品':25000,'交通':25000,'娯楽':30000,'その他':20000};
afterEach(cleanup);
it('preloads categories, derives total and saves the complete values',async()=>{
  let saved;
  const onClose=vi.fn();
  render(<BudgetDialog open categories={categories} busy={false} onClose={onClose} onSubmit={async value=>{saved=value;}}/>);
  const food=screen.getByLabelText('食費（円）');
  expect(document.activeElement).toBe(food);
  expect(food.value).toBe('60000');
  fireEvent.change(food,{target:{value:'70000'}});
  expect(screen.getByText('¥260,000')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
  await waitFor(()=>expect(saved).toEqual({...categories,'食費':70000}));
  expect(onClose).toHaveBeenCalledOnce();
});
it('keeps invalid values editable and does not submit them',async()=>{
  const onSubmit=vi.fn();
  render(<BudgetDialog open categories={categories} onClose={vi.fn()} onSubmit={onSubmit}/>);
  const food=screen.getByLabelText('食費（円）');
  for(const value of ['', '-1', '0.5', '1000000000']) {
    fireEvent.change(food,{target:{value}});
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
    expect(food.getAttribute('aria-invalid')).toBe('true');
    expect(food.getAttribute('aria-describedby')).toBeTruthy();
  }
  expect(onSubmit).not.toHaveBeenCalled();
});
it('keeps entered values after a failed save and permits retry',async()=>{
  const onSubmit=vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(categories);
  const onClose=vi.fn();
  render(<BudgetDialog open categories={categories} onClose={onClose} onSubmit={onSubmit}/>);
  fireEvent.change(screen.getByLabelText('食費（円）'),{target:{value:'70000'}});
  fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
  await screen.findByText(/保存できませんでした/);
  expect(screen.getByLabelText('食費（円）').value).toBe('70000');
  expect(onClose).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
  await waitFor(()=>expect(onClose).toHaveBeenCalledOnce());
});
it('resets cancelled edits when reopened and locks dismissal during save',()=>{
  const onClose=vi.fn();
  const props={categories,onClose,onSubmit:vi.fn()};
  const view=render(<BudgetDialog {...props} open/>);
  fireEvent.change(screen.getByLabelText('食費（円）'),{target:{value:'70000'}});
  fireEvent.click(screen.getByRole('button',{name:'キャンセル',exact:true}));
  expect(onClose).toHaveBeenCalledOnce();
  view.rerender(<BudgetDialog {...props} open={false}/>);
  view.rerender(<BudgetDialog {...props} open busy/>);
  expect(screen.getByLabelText('食費（円）').value).toBe('60000');
  expect(screen.getByLabelText('食費（円）').disabled).toBe(true);
  expect(screen.getByRole('button',{name:'キャンセル',exact:true}).disabled).toBe(true);
  fireEvent(screen.getByRole('dialog'),new Event('cancel',{bubbles:true,cancelable:true}));
  expect(onClose).toHaveBeenCalledOnce();
});
