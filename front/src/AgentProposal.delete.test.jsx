import React from 'react';
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import AgentProposal from './AgentProposal.jsx';

afterEach(cleanup);
const events=[{id:'a',placeId:'p',time:'09:00'}, {id:'b',placeId:'q',time:'10:00'}, {id:'c',placeId:'r',time:'11:00'}];
const legs=[{fromEventId:'a',toEventId:'b'}, {fromEventId:'b',toEventId:'c'}];
function proposal(kind='day') {
  const identity={kind,date:'2027-01-04',...(kind==='event'?{id:'b'}:kind==='leg'?{fromEventId:'a',toEventId:'b'}:{})};
  return {id:'p',revision:1,status:'pending',expiresAt:Date.now()/1000+86400,
    commands:[{kind:'trajectory.delete',identity,data:{}}],
    before:[{date:'2027-01-04',events,legs}],
    after:[kind==='day'?null:{date:'2027-01-04',events:kind==='event'?[events[0],events[2]]:events,legs:kind==='event'?[]:[legs[1]]}],
    metadata:{referenceLabels:{p:'出発店',q:'削除する店',r:'到着店'}}};
}
function show(value) {
  return render(<AgentProposal proposal={value} onChange={vi.fn()} onCommitted={vi.fn()} busy={false} setBusy={vi.fn()}/>);
}
it('clearly identifies whole-day deletion and its scope',()=>{
  show(proposal());
  expect(screen.getByRole('heading',{name:'一日の軌跡を削除'})).toBeTruthy();
  expect(screen.getByText(/2027-01-04.*訪問3件.*移動2区間/)).toBeTruthy();
  expect(screen.getByText('この日の軌跡はなくなります。')).toBeTruthy();
  expect(screen.getByRole('button',{name:'確認して削除'})).toBeTruthy();
});
it('shows the selected visit and connected legs without presenting retained visits as deleted',()=>{
  show(proposal('event'));
  expect(screen.getByRole('heading',{name:'訪問を削除'})).toBeTruthy();
  const targets=screen.getByRole('region',{name:'削除する訪問'});
  expect(within(targets).getByText(/10:00.*削除する店/)).toBeTruthy();
  expect(within(targets).queryByText(/出発店/)).toBeNull();
  expect(screen.getByText(/訪問1件.*移動2区間/)).toBeTruthy();
  expect(screen.getByText(/残った訪問間に移動区間は自動生成しません/)).toBeTruthy();
});
it('shows a leg deletion while keeping visits',()=>{
  show(proposal('leg'));
  expect(screen.getByRole('heading',{name:'移動区間を削除'})).toBeTruthy();
  expect(screen.getByText(/訪問0件.*移動1区間/)).toBeTruthy();
  expect(screen.getByText(/削除後.*訪問3件.*移動1区間/)).toBeTruthy();
});
it('keeps place names when event IDs overlap place IDs',()=>{
  const value=proposal('leg');
  value.before[0]={date:'2027-01-04',events:events.map((event,i)=>({...event,id:['p','q','r'][i]})),legs:[{fromEventId:'p',toEventId:'q'},{fromEventId:'q',toEventId:'r'}]};
  value.after[0]={...value.before[0],legs:[value.before[0].legs[1]]};
  value.commands[0].identity={kind:'leg',date:'2027-01-04',fromEventId:'p',toEventId:'q'};
  show(value);
  expect(within(screen.getByRole('region',{name:'削除する移動区間'})).getByText(/09:00.*出発店.*10:00.*削除する店/)).toBeTruthy();
});
it('distinguishes repeated unknown-time visits to the same place by their saved order',()=>{
  const value=proposal('event');
  value.before[0].events=events.map(event=>({...event,placeId:'p',time:null}));
  value.after[0].events=[value.before[0].events[0],value.before[0].events[2]];
  show(value);
  const targets=screen.getByRole('region',{name:'削除する訪問'});
  expect(within(targets).getByText('訪問 2 · 時刻不明 · 出発店')).toBeTruthy();
  expect(within(targets).queryByText('訪問 1 · 時刻不明 · 出発店')).toBeNull();
});
it('can open the revision form for a day deletion without expecting event data',()=>{
  show(proposal());
  fireEvent.click(screen.getByRole('button',{name:'内容を修正'}));
  expect(screen.getByText(/削除対象を変更する場合はメッセージで伝えてください/)).toBeTruthy();
  expect(screen.getByRole('button',{name:'差分を更新'})).toBeTruthy();
});
