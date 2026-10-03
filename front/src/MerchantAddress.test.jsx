import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,fireEvent,waitFor} from '@testing-library/react';
import TransactionDetail from './TransactionDetail.jsx';
import {parseExpenseDraft} from './lib/transaction-data.js';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const record={id:'a',title:'買物',date:'2026-10-01T12:00',type:'expense',category:'食費',amount:100,merchant:'店',merchantAddress:'住所A'};
it('keeps optional addresses and enforces the Unicode limit',()=>{
 const draft={merchant:'店',paymentMethod:'cash',itemRows:[],manualAmount:100,merchantAddress:'𠮷'.repeat(500)};
 expect(parseExpenseDraft(draft).merchantAddress).toBe('𠮷'.repeat(500));
 expect(()=>parseExpenseDraft({...draft,merchantAddress:'𠮷'.repeat(501)})).toThrow();
});
it('cancels, preserves errors, and explicitly clears an address',async()=>{
 vi.stubGlobal('fetch',vi.fn(async url=>({ok:true,status:200,json:async()=>url.includes('addresses')?{address:{transactionId:'a',places:[]}}:{receipts:[]}})));
 const save=vi.fn().mockRejectedValueOnce(new Error('競合しました')).mockResolvedValue(true);
 render(<TransactionDetail record={record} onSaveAddress={save}/>);
 fireEvent.click(screen.getByRole('button',{name:'住所を編集'}));
 fireEvent.change(screen.getByLabelText('住所（任意）'),{target:{value:'住所B'}});
 fireEvent.click(screen.getByRole('button',{name:'キャンセル'}));expect(save).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'住所を編集'}));
 fireEvent.change(screen.getByLabelText('住所（任意）'),{target:{value:''}});
 fireEvent.click(screen.getByRole('button',{name:'住所を保存'}));
 expect(await screen.findByText('競合しました')).toBeTruthy();expect(screen.getByLabelText('住所（任意）').value).toBe('');
 fireEvent.click(screen.getByRole('button',{name:'住所を保存'}));
 await waitFor(()=>expect(save).toHaveBeenLastCalledWith(null,{merchant:'店',merchantAddress:'住所A'}));
});
