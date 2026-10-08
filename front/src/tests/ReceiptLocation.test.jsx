import {it,expect,vi,afterEach} from 'vitest';
import {renderHook,act,cleanup} from '@testing-library/react';
import useReceiptLocation from '../components/receipts/useReceiptLocation.js';
import * as api from '../lib/agent-api.js';
vi.mock('../lib/agent-api.js');
afterEach(()=>{cleanup();vi.clearAllMocks();});
const input={merchant:'店',branch:null,locality:null,merchantAddress:'住所'};
const resolution={id:'current-resolution',receiptId:'r',revision:1,input,status:'resolved',expiresAt:Date.now()/1000+3600,sourceTransactionId:null};
it('invalidates_on_branch_locality_or_merchant_change',()=>{const {result,rerender}=renderHook(p=>useReceiptLocation(p),{initialProps:{threadId:'t',receiptId:'r',initialResolution:resolution,input,target:'new'}});expect(result.current.resolved).toBe(true);for(const key of ['branch','locality','merchant']){rerender({threadId:'t',receiptId:'r',initialResolution:resolution,input:{...input,[key]:'変更'},target:'new'});expect(result.current.resolved).toBe(false);}});
it('ignores_late_response_after_receipt_switch',async()=>{let finish;api.searchReceiptLocation.mockReturnValue(new Promise(r=>finish=r));const {result,rerender}=renderHook(p=>useReceiptLocation(p),{initialProps:{threadId:'t',receiptId:'r',initialResolution:resolution,input,target:'new'}});act(()=>{result.current.search();});rerender({threadId:'t',receiptId:'r2',initialResolution:null,input,target:'new'});await act(async()=>finish(resolution));expect(result.current.resolved).toBe(false);});
it('keeps_target_specific_confirmations_separate',()=>{const initial={...resolution,sourceTransactionId:'A'};const {result,rerender}=renderHook(p=>useReceiptLocation(p),{initialProps:{threadId:'t',receiptId:'r',initialResolution:initial,input,target:'A'}});expect(result.current.resolved).toBe(true);rerender({threadId:'t',receiptId:'r',initialResolution:initial,input,target:'B'});expect(result.current.resolved).toBe(false);});
it('ordinary search does not inherit a target reference and cancels requests on input change',async()=>{
 let finish;api.searchReceiptLocation.mockReturnValue(new Promise(r=>finish=r));const props={threadId:'t',receiptId:'r',initialResolution:resolution,input,target:{id:'A',merchantPlace:{placeId:'saved'}}};
 const {result,rerender}=renderHook(p=>useReceiptLocation(p),{initialProps:props});act(()=>{result.current.search();});
 expect(api.searchReceiptLocation.mock.lastCall[2]).not.toHaveProperty('sourceTransactionId');const signal=api.searchReceiptLocation.mock.lastCall[3];rerender({...props,input:{...input,locality:'変更'}});expect(signal.aborted).toBe(true);await act(async()=>finish(resolution));expect(result.current.resolved).toBe(false);
});
it('focuses_error_summary_and_announces_status',async()=>{
 const {default:ReceiptLocation}=await import('../components/receipts/ReceiptLocation.jsx');const React=await import('react');const {render,screen}=await import('@testing-library/react');
 const error=Object.assign(new Error('支店名を確認してください'),{field:'branch'});
 render(React.createElement(ReceiptLocation,{location:{resolution:null,pending:false,error,resolved:false},input,onInputChange:vi.fn()}));
 expect(screen.getByRole('alert')).toBe(document.activeElement);expect(screen.getByLabelText('支店名').getAttribute('aria-invalid')).toBe('true');expect(screen.getByRole('status').textContent).toContain('店舗名');
});
it('explains classified unavailable reasons with recovery actions',async()=>{
 const {default:ReceiptLocation}=await import('../components/receipts/ReceiptLocation.jsx');const React=await import('react');const {render,screen}=await import('@testing-library/react');
 for(const [reason,description] of [['provider_configuration','設定'],['provider_unavailable','通信'],['budget_exceeded','時間'],['expired','期限'],['cancelled','中断']]){
  const view=render(React.createElement(ReceiptLocation,{location:{resolution:{status:'unavailable',reason},pending:false,resolved:false},input,onInputChange:vi.fn()}));
  expect(screen.getByRole('status').textContent).toContain(description);
  expect(screen.getByRole('button',{name:'この住所を確認した'}).disabled).toBe(false);view.unmount();
 }
});
