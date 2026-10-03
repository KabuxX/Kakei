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
