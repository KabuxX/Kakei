import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import App from './App.jsx';
const initial={id:'a/b 日本語',title:'買物',date:'2026-10-01T12:00',type:'expense',category:'食費',amount:300,merchant:'店',merchantAddress:'住所A',paymentMethod:'cash',items:[{name:'パン',amount:100},{name:'飲物',amount:200}],timeEstimated:true};
function setup({fail=false,refreshFail=false,category=initial.category,backgroundFail=false}={}){
 let record={...initial,category},saved=false,reads=0;
 window.scrollTo=vi.fn();window.location.hash='#transaction/a%2Fb%20%E6%97%A5%E6%9C%AC%E8%AA%9E/edit';
 vi.stubGlobal('fetch',vi.fn(async(url,options={})=>{
  let body={},status=200;
  if(url==='/api/status')body={initialized:true};
  else if(url==='/api/transactions'){
   if((saved&&refreshFail)||(backgroundFail&&reads++>0)){status=503;body={error:{message:'offline'}};}else body={transactions:[record]};
  }else if(options.method==='PUT'){
   if(fail){status=503;body={error:{message:'offline'}};}else {record={...record,...JSON.parse(options.body)};saved=true;body={transaction:record};}
  }else if(url.includes('transaction-addresses'))body={address:{transactionId:record.id,places:[]}};
  else body={receipts:[{id:'existing-receipt',mimeType:'image/png'}]};
  return {ok:status<400,status,json:async()=>body};
 }));
 return ()=>record;
}
afterEach(()=>{cleanup();window.location.hash='';vi.unstubAllGlobals();});
it('opens an encoded editing URL with existing fields and saves item totals into detail',async()=>{
 const current=setup();render(<App/>);
 await screen.findByRole('heading',{name:'取引を編集'});
 expect(screen.getByRole('textbox',{name:/内容/}).value).toBe('買物');
 expect(screen.getByRole('textbox',{name:'住所（任意）',exact:true}).value).toBe('住所A');
 expect(screen.getByRole('spinbutton',{name:/^金額/}).value).toBe('300');
 fireEvent.change(screen.getByRole('textbox',{name:/内容/}),{target:{value:'修正した買物'}});
 fireEvent.change(screen.getByRole('spinbutton',{name:'品目2の金額（円）'}),{target:{value:'250'}});
 fireEvent.change(screen.getByRole('textbox',{name:'住所（任意）',exact:true}),{target:{value:''}});
 fireEvent.click(screen.getByRole('button',{name:'保存する'}));
 await screen.findByRole('heading',{name:'修正した買物'});
 expect((await screen.findByRole('link',{name:'レシート 1 を開く'})).getAttribute('href')).toBe('/api/receipts/existing-receipt');
 expect(current().amount).toBe(350);expect(current().merchantAddress).toBe(null);expect(current().timeEstimated).toBe(true);
 expect(screen.getByRole('status').textContent).toContain('取引を更新しました');
});
it('keeps inputs after save failure and cancels without changing the saved record',async()=>{
 const current=setup({fail:true});render(<App/>);await screen.findByRole('heading',{name:'取引を編集'});
 fireEvent.change(screen.getByRole('textbox',{name:/内容/}),{target:{value:'未保存の変更'}});
 fireEvent.click(screen.getByRole('button',{name:'保存する'}));
 await screen.findByText(/保存できませんでした/);
 expect(screen.getByRole('textbox',{name:/内容/}).value).toBe('未保存の変更');
 fireEvent.click(screen.getByRole('button',{name:'キャンセル',exact:true}));
 await screen.findByRole('heading',{name:'買物'});expect(current().title).toBe('買物');
});
it('shows a completed-save warning without resubmitting when refresh fails',async()=>{
 const current=setup({refreshFail:true});render(<App/>);await screen.findByRole('heading',{name:'取引を編集'});
 fireEvent.change(screen.getByRole('textbox',{name:/内容/}),{target:{value:'保存済みの変更'}});
 fireEvent.click(screen.getByRole('button',{name:'保存する'}));
 await screen.findByRole('heading',{name:'取引詳細'});
 expect(current().title).toBe('保存済みの変更');
 expect(screen.getByRole('alert').textContent).toContain('サーバーへの保存は完了');
});
it('shows a missing state for an unknown edit URL',async()=>{
 setup();window.location.hash='#transaction/unknown/edit';render(<App/>);
 await screen.findByRole('heading',{name:'取引が見つかりません'});
 expect(screen.queryByRole('button',{name:'保存する'})).toBeNull();
});

it('honestly displays a legacy category and requires a supported category before saving',async()=>{
 const current=setup({category:'旧カテゴリ'});render(<App/>);await screen.findByRole('heading',{name:'取引を編集'});
 expect(screen.getByRole('combobox',{name:'カテゴリ'}).value).toBe('旧カテゴリ');
 fireEvent.click(screen.getByRole('button',{name:'保存する'}));
 await screen.findByText('カテゴリを選び直してください。');
 expect(current().category).toBe('旧カテゴリ');
 fireEvent.change(screen.getByRole('combobox',{name:/カテゴリ/}),{target:{value:'日用品'}});
 fireEvent.click(screen.getByRole('button',{name:'保存する'}));
 await screen.findByRole('heading',{name:'取引詳細'});expect(current().category).toBe('日用品');
});

it('allows cancelling unsaved changes after a background refresh fails',async()=>{
 setup({backgroundFail:true});const visibility=vi.spyOn(document,'visibilityState','get').mockReturnValue('visible');
 render(<App/>);await screen.findByRole('heading',{name:'取引を編集'});
 fireEvent.change(screen.getByRole('textbox',{name:/内容/}),{target:{value:'未保存の入力'}});
 fireEvent(document,new Event('visibilitychange'));
 await screen.findByText(/最新の取引を読み込めませんでした/);
 expect(screen.getByRole('textbox',{name:/内容/}).value).toBe('未保存の入力');
 expect(screen.getByRole('button',{name:'保存する'}).disabled).toBe(true);
 expect(screen.getByRole('button',{name:'キャンセル',exact:true}).disabled).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'キャンセル',exact:true}));
 await screen.findByRole('heading',{name:'取引詳細'});visibility.mockRestore();
});
