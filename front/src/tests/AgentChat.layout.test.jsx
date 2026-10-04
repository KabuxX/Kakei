import React from 'react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import App from '../app/App.jsx';
import {useTransactions} from '../useTransactions.js';
import * as api from '../lib/agent-api.js';
vi.mock('../useTransactions.js');vi.mock('../lib/agent-api.js');
beforeEach(()=>{
 vi.resetAllMocks();window.location.hash='#agent';window.scrollTo=vi.fn();
 useTransactions.mockReturnValue({transactions:[],status:'ready',refresh:vi.fn(),load:vi.fn()});
 api.status.mockResolvedValue({available:true,placesAvailable:true});
 api.listThreads.mockResolvedValue([{id:'a',title:'食材の記録'},{id:'b',title:'昨日の軌跡'}]);
 api.getThread.mockImplementation(async id=>({id,title:id==='a'?'食材の記録':'昨日の軌跡',messages:[{id:'m',role:'assistant',text:'続けて入力できます'}],proposals:[]}));
 api.createThread.mockResolvedValue({id:'new-id',title:'新しい会話'});
 api.sendMessage.mockResolvedValue({});
});
afterEach(()=>{cleanup();vi.useRealTimers();vi.unstubAllGlobals();window.location.hash='';});
it('moves history below Agent Chat and combines attachment and icon submit in one form',async()=>{
 render(<App/>);
 const history=await screen.findByRole('button',{name:'食材の記録'});
 expect(document.getElementById('app-sidebar').contains(history)).toBe(true);
 expect(screen.queryByText('今日は何を記録しますか？')).toBeNull();
 expect(screen.queryByText('家計のアシスタント')).toBeNull();
 const form=screen.getByRole('textbox',{name:'メッセージ'}).closest('form');
 expect(within(form).getByRole('button',{name:'レシートを添付'})).toBeTruthy();
 expect(within(form).getByRole('button',{name:'送信'}).textContent).toBe('');
});
it('preserves separate drafts when switching conversations and after leaving chat',async()=>{
 render(<App/>);fireEvent.click(await screen.findByRole('button',{name:'食材の記録'}));
 await screen.findByText('続けて入力できます');
 fireEvent.change(screen.getByRole('textbox',{name:'メッセージ'}),{target:{value:'食材の下書き'}});
 fireEvent.click(screen.getByRole('button',{name:'昨日の軌跡'}));
 await vi.waitFor(()=>expect(screen.getByRole('textbox',{name:'メッセージ'}).value).toBe(''));
 fireEvent.change(screen.getByRole('textbox',{name:'メッセージ'}),{target:{value:'軌跡の下書き'}});
 fireEvent.click(screen.getByRole('button',{name:'食材の記録'}));
 await vi.waitFor(()=>expect(screen.getByRole('textbox',{name:'メッセージ'}).value).toBe('食材の下書き'));
 fireEvent.click(screen.getByRole('link',{name:'概要'}));
 await vi.waitFor(()=>expect(screen.queryByRole('textbox',{name:'メッセージ'})).toBeNull());
 fireEvent.click(screen.getByRole('link',{name:'Agent Chat'}));
 expect(await screen.findByRole('textbox',{name:'メッセージ'})).toHaveProperty('value','食材の下書き');
});
it('sends with command Enter but not ordinary Enter or Japanese composition',async()=>{
 render(<App/>);const field=await screen.findByRole('textbox',{name:'メッセージ'});
 fireEvent.change(field,{target:{value:'記録して'}});
 fireEvent.keyDown(field,{key:'Enter'});fireEvent.keyDown(field,{key:'Enter',metaKey:true,isComposing:true});
 expect(api.sendMessage).not.toHaveBeenCalled();
 fireEvent.keyDown(field,{key:'Enter',metaKey:true});
 await vi.waitFor(()=>expect(api.sendMessage).toHaveBeenCalledTimes(1));
});
it('updates the local-time greeting while the page stays open',async()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date(2026,9,3,10,59,30));
 render(<App/>);await act(async()=>{});
 expect(screen.getByRole('heading',{name:'おはよう'})).toBeTruthy();
 await act(async()=>{vi.advanceTimersByTime(60000);});
 expect(screen.getByRole('heading',{name:'こんにちは'})).toBeTruthy();
 vi.setSystemTime(new Date(2026,9,3,18,0));
 await act(async()=>{document.dispatchEvent(new Event('visibilitychange'));});
 expect(screen.getByRole('heading',{name:'こんばんは'})).toBeTruthy();
});
