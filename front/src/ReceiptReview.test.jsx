import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import ReceiptReview from './ReceiptReview.jsx';
import * as api from './lib/agent-api.js';
vi.mock('./lib/agent-api.js');afterEach(cleanup);
it('requires explicit duplicate selection and preserves missing fields and discrepancy',async()=>{
 const review={receiptId:'r',mimeType:'image/png',candidate:{merchant:'店',date:null,time:null,total:90,currency:'JPY',payment_method:null,items:[{name:'品目',amount:100}]},missingFields:['date','time','payment_method'],itemMismatch:true,matches:[{reason:'near',transaction:{id:'t',title:'食材',date:'2026-10-03T12:00',amount:90}}]};
 render(<ReceiptReview review={review} threadId="thread" busy={false} setBusy={vi.fn()} onProposed={vi.fn()}/>);
 expect(screen.getByRole('img',{name:'レシートのプレビュー'}).getAttribute('src')).toContain('/receipts/r');
 expect(screen.getByText(/品目合計と合計金額が一致しません/)).toBeTruthy();
 expect(screen.getByRole('button',{name:'変更案を確認'}).disabled).toBe(true);
 fireEvent.change(screen.getByRole('combobox',{name:'保存先'}),{target:{value:'t'}});
 expect(api.proposeReceipt).not.toHaveBeenCalled();
 expect(screen.getByLabelText('日時 1').value).toBe('');
});
it('uses calculated net amounts and keeps original evidence visible after manual edits',()=>{
 const review={receiptId:'r',candidate:{merchant:'店',date:'2026-10-01',time:'08:45',total:1161,paid_total:1139,currency:'JPY',items:[{name:'商品',amount:130}]},missingFields:[],matches:[],preparedDraft:{amount:1139,items:[{name:'商品',amount:1139}]},calculation:{issues:[],grossTotal:1161,discountTotal:22,paidTotal:1139,rows:[{name:'商品',printed:130,basis:'exclusive',rate:8,addedTax:10,gross:140,discount:3,net:137}]}};
 render(<ReceiptReview review={review} threadId="thread" busy={false} setBusy={vi.fn()} onProposed={vi.fn()}/>);
 expect(screen.getByLabelText('金額 1').value).toBe('1139');
 expect(screen.getByLabelText('品目金額 1').value).toBe('1139');
 expect(screen.getByRole('region',{name:'税込金額の計算根拠'})).toBeTruthy();
 fireEvent.change(screen.getByLabelText('金額 1'),{target:{value:'1200'}});
 expect(screen.getByText(/自動計算後に変更されています/)).toBeTruthy();
});
it('requires explicit manual verification when tax evidence is inconsistent',()=>{
 const review={receiptId:'r',candidate:{total:100,currency:'JPY',items:[{name:'商品',amount:100}]},missingFields:[],matches:[],calculation:{rows:[],issues:['税区分を確認してください。']},preparedDraft:null};
 render(<ReceiptReview review={review} threadId="thread" busy={false} setBusy={vi.fn()} onProposed={vi.fn()}/>);
 fireEvent.change(screen.getByRole('combobox',{name:'保存先'}),{target:{value:'new'}});
 expect(screen.getByRole('button',{name:'変更案を確認'}).disabled).toBe(true);
 fireEvent.click(screen.getByLabelText('原本と照合し、金額・品目を確認しました'));
 expect(screen.getByRole('button',{name:'変更案を確認'}).disabled).toBe(false);
});
it('keeps address edits separate for each receipt target',()=>{
 const review={receiptId:'r',candidate:{merchant:'店',total:100,currency:'JPY'},missingFields:[],matches:['A','B'].map(id=>({reason:'near',transaction:{id,title:id,merchantAddress:'住所'+id}}))};
 render(<ReceiptReview review={review} threadId="t" busy={false} setBusy={vi.fn()} onProposed={vi.fn()}/>);
 const select=screen.getByLabelText('保存先');
 fireEvent.change(select,{target:{value:'A'}});expect(screen.getByLabelText('住所（任意）').value).toBe('住所A');
 fireEvent.change(screen.getByLabelText('住所（任意）'),{target:{value:'修正A'}});
 fireEvent.change(select,{target:{value:'B'}});expect(screen.getByLabelText('住所（任意）').value).toBe('住所B');
 fireEvent.change(select,{target:{value:'new'}});expect(screen.getByLabelText('住所（任意）').value).toBe('');
 fireEvent.change(select,{target:{value:'A'}});expect(screen.getByLabelText('住所（任意）').value).toBe('修正A');
});
