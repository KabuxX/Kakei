import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {fireEvent} from '@testing-library/react';
const requests=vi.hoisted(()=>[]);
vi.mock('@kakei/runtime',async()=>{const runtime=await import('../../demo/runtime.js');return {...runtime,apiFetch:(url,options={})=>{requests.push({url:String(url),method:options.method||'GET'});return runtime.apiFetch(url,options);}};});
import App from '../app/App.jsx';
import snapshot from '../../demo/data/snapshot.json';
let root,host;
beforeEach(()=>{requests.length=0;globalThis.IS_REACT_ACT_ENVIRONMENT=true;window.scrollTo=vi.fn();host=document.createElement('div');document.body.append(host);root=createRoot(host);location.hash='#overview';localStorage.setItem('kakei-transactions-v1','broken');});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();localStorage.clear();vi.restoreAllMocks();});
it('shows snapshot month, finances and no writing controls',async()=>{
 await act(async()=>root.render(<App/>));expect(host.textContent).toContain('DEMO・閲覧専用');expect(host.querySelector('#month-label').textContent).toBe('2026年10月');expect(host.querySelector('#transaction-count').textContent).toBe('4');expect(host.querySelector('.add-trigger')).toBeNull();expect(host.querySelector('.budget-edit-button')).toBeNull();
 await act(async()=>host.querySelector('#prev-month').click());expect(host.querySelector('#transaction-count').textContent).toBe('37');
});
it.each(['edit','delete'])('turns direct %s route into a readable detail with static receipts',async suffix=>{
 location.hash=`#transaction/${snapshot.transactions[0].id}/${suffix}`;await act(async()=>root.render(<App/>));expect(host.querySelector('#detail-title')?.textContent).toBe(snapshot.transactions[0].title);expect(host.textContent).toContain('閲覧専用のため、取引詳細を表示しています。');expect(host.querySelector('form')).toBeNull();expect(host.querySelector('#detail-delete')).toBeNull();
});

it('searches and exports snapshot records then selects every saved conversation using GET only',async()=>{
 const create=vi.fn(()=> 'blob:demo-csv');vi.stubGlobal('URL',class extends URL {static createObjectURL=create;static revokeObjectURL=vi.fn();});
 const downloads=[];vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(){downloads.push(this.download);});
 const external=vi.spyOn(globalThis,'fetch').mockRejectedValue(new Error('External requests are forbidden'));
 await act(async()=>root.render(<App/>));
 await act(async()=>fireEvent.change(host.querySelector('#transaction-search'),{target:{value:'コンビニ2'}}));
 expect(host.querySelectorAll('#transaction-rows tr')).toHaveLength(1);
 await act(async()=>host.querySelector('#export-button').click());expect(downloads).toEqual(['kakei-2026-10.csv']);expect(create.mock.calls[0][0].type).toBe('text/csv;charset=utf-8');
 await act(async()=>{location.hash='#agent';window.dispatchEvent(new HashChangeEvent('hashchange'));});
 for(const thread of snapshot.threads){
 const button=[...host.querySelectorAll('.agent-thread-link')].find(b=>b.textContent===thread.title);
 expect(button).toBeDefined();await act(async()=>button.click());
 expect(host.querySelector('.agent-conversation').textContent).toContain(thread.messages[0].text);
 }
 expect(requests.some(r=>r.url.includes('/api/agent/threads/'))).toBe(true);expect(requests.every(r=>r.method==='GET')).toBe(true);expect(external).not.toHaveBeenCalled();
 expect(localStorage.getItem('kakei-transactions-v1')).toBe('broken');vi.unstubAllGlobals();
});
