import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import App from '../app/App.jsx';
const initial={'食費':60000,'住まい':90000,'日用品':25000,'交通':25000,'娯楽':30000,'その他':20000};
afterEach(()=>{cleanup();vi.unstubAllGlobals();window.location.hash='';});
function setup(fail=false) {
  let categories={...initial}, failNext=fail;
  const now=new Date(), month=new Date(now.getFullYear(),now.getMonth()-1,1);
  const date=`${month.getFullYear()}-${String(month.getMonth()+1).padStart(2,'0')}-01T12:00`;
  window.location.hash='#overview';window.scrollTo=vi.fn();
  vi.stubGlobal('fetch',async(url,options={})=>{
    let body={};
    if(url==='/api/status')body={initialized:true};
    else if(url==='/api/transactions')body={transactions:[{id:'fixture',title:'食材',date,type:'expense',category:'食費',amount:1200}]};
    else if(url==='/api/budget') {
      if(failNext){failNext=false;throw new Error('offline');}
      if(options.method==='PUT')categories=JSON.parse(options.body).categories;
      body={categories};
    } else throw new Error('unexpected '+url);
    return {ok:true,status:200,json:async()=>body};
  });
  return {month,getBudget:()=>categories};
}
it('keeps the financial summary when budgets fail and can retry',async()=>{
  const {month}=setup(true);render(<App/>);
  await screen.findByText('予算を読み込めませんでした。');
  expect(document.getElementById('month-label').textContent).toBe(`${month.getFullYear()}年${month.getMonth()+1}月`);
  expect(document.getElementById('balance-amount').textContent).toBe('−¥1,200');
  expect(screen.getByRole('link',{name:'食材'})).toBeTruthy();
  expect(screen.getByRole('button',{name:'予算を設定'}).disabled).toBe(true);
  expect(document.getElementById('remaining-budget').textContent).toBe('—');
  fireEvent.click(screen.getByRole('button',{name:'予算を再読み込み'}));
  await waitFor(()=>expect(document.getElementById('remaining-budget').textContent).toBe('¥248,800'));
});
it('updates totals and category progress only after saving',async()=>{
  const {getBudget}=setup();render(<App/>);
  const trigger=await screen.findByRole('button',{name:'予算を設定'});
  await waitFor(()=>expect(trigger.disabled).toBe(false));
  fireEvent.click(trigger);
  const dialog=screen.getByRole('dialog',{name:'予算を設定'});
  fireEvent.change(within(dialog).getByLabelText('食費（円）'),{target:{value:'70000'}});
  expect(document.getElementById('remaining-budget').textContent).toBe('¥248,800');
  fireEvent.click(within(dialog).getByRole('button',{name:'保存',exact:true}));
  await waitFor(()=>expect(document.getElementById('budget-limit').textContent).toBe('予算 ¥260,000'));
  expect(document.getElementById('remaining-budget').textContent).toBe('¥258,800');
  expect(getBudget()['食費']).toBe(70000);
  expect(screen.getByRole('meter',{name:'食費の予算使用率'}).getAttribute('aria-valuenow')).toBe('2');
  await waitFor(()=>expect(document.activeElement).toBe(trigger));
  expect(screen.getByRole('status').textContent).toContain('予算を保存しました');
});
