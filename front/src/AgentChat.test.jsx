import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import AgentChatView from './AgentChat.jsx';
import {useAgentChat} from './useAgentChat.js';
import {AgentThreads} from './AgentControls.jsx';
function AgentChat(props){const session=useAgentChat(true);return <><AgentThreads session={session}/><AgentChatView {...props} session={session}/></>;}

import * as api from './lib/agent-api.js';
vi.mock('./lib/agent-api.js');
let proposal;
beforeEach(() => {
  vi.resetAllMocks();
  proposal = { id: 'p', revision: 1, status: 'pending', expiresAt: Date.now()/1000+86400, before:[null], after:[{title:'給与',amount:100,date:'2026-10-01T12:00',type:'income',category:'収入'}], commands:[{kind:'transaction.create',identity:{},data:{title:'給与',amount:100,date:'2026-10-01T12:00',type:'income',category:'収入'}}] };
  api.status.mockResolvedValue({available:true}); api.listThreads.mockResolvedValue([]);
  api.createThread.mockResolvedValue({id:'t',title:'新しい会話'});
  api.getThread.mockImplementation(async () => ({id:'t',messages:[{id:'m',role:'assistant',text:'確認してください'}],proposals:[proposal]}));
  api.sendMessage.mockResolvedValue({message:{id:'m',role:'assistant',text:'確認してください'},proposal});
  api.revise.mockImplementation(async (id, revision, commands) => { proposal={...proposal,revision:2,commands,after:commands.map(c=>c.data)}; return proposal; });
  api.approve.mockResolvedValue({transactions:[]});
});
afterEach(cleanup);
async function start() {
  await vi.waitFor(()=>expect(screen.getByRole('button',{name:'送信'}).closest('form').querySelector('textarea').disabled).toBe(false));
  fireEvent.change(screen.getByRole('textbox',{name:'メッセージ'}),{target:{value:'給与を記録して'}});
  fireEvent.click(screen.getByRole('button',{name:'送信'}));
  await screen.findByText('確認してください');
}
it('stages and edits a transaction before explicit approval', async () => {
  render(<AgentChat onCommitted={vi.fn()} />); await start();
  expect(api.approve).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'内容を修正'}));
  fireEvent.change(screen.getByRole('spinbutton',{name:'金額 1'}),{target:{value:'200'}});
  fireEvent.click(screen.getByRole('button',{name:'差分を更新'}));
  await screen.findByText('確認待ち · 第2版');
  expect(api.revise).toHaveBeenCalledWith('p',1,expect.arrayContaining([expect.objectContaining({data:expect.objectContaining({amount:200})})]));
  expect(api.approve).not.toHaveBeenCalled();
});
it('retries lost approval response and refreshes app once', async () => {
  const onCommitted=vi.fn().mockResolvedValue(true);
  api.approve.mockRejectedValueOnce(new Error('通信が途切れました')).mockResolvedValueOnce({transactions:[]});
  render(<AgentChat onCommitted={onCommitted} />); await start();
  fireEvent.click(screen.getByRole('button',{name:'確認して保存'}));
  await screen.findByRole('alert'); expect(onCommitted).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'確認して保存'}));
  await screen.findByText('保存済み');
  expect(api.approve.mock.calls).toEqual([['p',1],['p',1]]);
  expect(onCommitted).toHaveBeenCalledTimes(1);
});
it('keeps plain Enter in composer from approving a pending proposal', async () => {
  render(<AgentChat onCommitted={vi.fn()} />); await start();
  fireEvent.keyDown(screen.getByRole('textbox',{name:'メッセージ'}),{key:'Enter'});
  expect(api.approve).not.toHaveBeenCalled();
});

it('uploads a receipt without submitting or approving it',async()=>{
 api.uploadReceipt.mockResolvedValue({id:'r',mimeType:'image/png'});
 render(<AgentChat onCommitted={vi.fn()}/>);
 const input=await screen.findByLabelText('レシートファイル');
 await vi.waitFor(()=>expect(input.disabled).toBe(false));
 fireEvent.change(input,{target:{files:[new File(['image'],'receipt.png',{type:'image/png'})]}});
 expect(await screen.findByRole('img',{name:'添付レシート'})).toBeTruthy();
 expect(api.sendMessage).not.toHaveBeenCalled();expect(api.approve).not.toHaveBeenCalled();
});
it('refreshes application data when proposal reload discovers committed approval',async()=>{
 const onCommitted=vi.fn().mockResolvedValue(true);
 api.approve.mockRejectedValueOnce(new Error('lost response'));
 api.getProposal.mockResolvedValue({...proposal,status:'applied'});
 render(<AgentChat onCommitted={onCommitted}/>);await start();
 fireEvent.click(screen.getByRole('button',{name:'確認して保存'}));
 fireEvent.click(await screen.findByRole('button',{name:'変更案を再読み込み'}));
 await screen.findByText('保存済み');
 expect(onCommitted).toHaveBeenCalledTimes(1);
});
it('keeps receipt source and destination context in the final approval and edit card',async()=>{
 proposal={...proposal,threadId:'t',metadata:{receiptId:'r',targetChoice:'existing',receiptReview:{receiptId:'r',mimeType:'image/png',matches:[{reason:'hash',transaction:{id:'existing',title:'既存の食材',date:'2026-10-01T12:00',amount:100}}]}}};
 render(<AgentChat onCommitted={vi.fn()}/>);await start();
 expect(screen.getByRole('img',{name:'確認するレシート'}).getAttribute('src')).toBe('/api/agent/threads/t/receipts/r');
 expect(screen.getByRole('link',{name:'レシート原本を開く'})).toBeTruthy();
 expect(screen.getByText(/保存先:.*既存の食材/)).toBeTruthy();expect(screen.getByText(/同じレシート/)).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'内容を修正'}));
 expect(screen.getByRole('link',{name:'レシート原本を開く'})).toBeTruthy();
});

function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
async function enterMessage(text='先に表示するメッセージ'){
 await vi.waitFor(()=>expect(screen.getByRole('textbox',{name:'メッセージ'}).disabled).toBe(false));
 fireEvent.change(screen.getByRole('textbox',{name:'メッセージ'}),{target:{value:text}});
 fireEvent.click(screen.getByRole('button',{name:'送信'}));
}
it('shows the user bubble before thread creation or response and replaces loading with the answer',async()=>{
 const creation=deferred(),response=deferred();api.createThread.mockReturnValue(creation.promise);api.sendMessage.mockReturnValue(response.promise);
 render(<AgentChat onCommitted={vi.fn()}/>);await enterMessage();
 expect(await screen.findByText('先に表示するメッセージ')).toBeTruthy();
 expect(screen.getByRole('textbox',{name:'メッセージ'}).value).toBe('');
 expect(screen.getByRole('status',{name:'Agentが処理中'})).toBeTruthy();
 expect(screen.queryByText('確認してください')).toBeNull();
 creation.resolve({id:'t',title:'新しい会話'});
 await vi.waitFor(()=>expect(api.sendMessage).toHaveBeenCalledTimes(1));
 const body=api.sendMessage.mock.calls[0][1];
 api.getThread.mockResolvedValue({id:'t',messages:[{id:'u',clientMessageId:`user:${body.clientMessageId}`,role:'user',text:body.text},{id:'a',role:'assistant',text:'確認してください'}],proposals:[]});
 response.resolve({});
 await screen.findByText('確認してください');
 expect(screen.getAllByText('先に表示するメッセージ')).toHaveLength(1);
 expect(screen.queryByRole('status',{name:'Agentが処理中'})).toBeNull();
});
it('keeps the failed bubble and retries the same turn without duplicating it',async()=>{
 api.sendMessage.mockRejectedValueOnce(new Error('応答が途切れました'));
 const response=deferred();api.sendMessage.mockReturnValueOnce(response.promise);
 render(<AgentChat onCommitted={vi.fn()}/>);await enterMessage('再送するメッセージ');
 await screen.findByRole('alert');
 expect(screen.getAllByText('再送するメッセージ').filter(el=>el.tagName!=='TEXTAREA')).toHaveLength(1);
 expect(screen.queryByRole('status',{name:'Agentが処理中'})).toBeNull();
 expect(screen.getByRole('textbox',{name:'メッセージ'}).value).toBe('再送するメッセージ');
 const body=api.sendMessage.mock.calls[0][1];
 api.getThread.mockResolvedValue({id:'t',messages:[{id:'u',clientMessageId:`user:${body.clientMessageId}`,role:'user',text:body.text},{id:'a',role:'assistant',text:'再送完了'}],proposals:[]});
 fireEvent.click(screen.getByRole('button',{name:'再送'}));
 await vi.waitFor(()=>expect(api.sendMessage).toHaveBeenCalledTimes(2));
 expect(api.sendMessage.mock.calls[1][1]).toEqual(body);
 expect(screen.getAllByText('再送するメッセージ')).toHaveLength(1);
 response.resolve({});await screen.findByText('再送完了');
 expect(screen.getAllByText('再送するメッセージ')).toHaveLength(1);
});
it('retains text and the user bubble if conversation creation fails',async()=>{
 api.createThread.mockRejectedValueOnce(new Error('会話作成に失敗'));
 render(<AgentChat onCommitted={vi.fn()}/>);await enterMessage('失わない入力');
 await screen.findByRole('alert');
 expect(screen.getAllByText('失わない入力').filter(el=>el.tagName!=='TEXTAREA')).toHaveLength(1);
 expect(screen.queryByRole('status',{name:'Agentが処理中'})).toBeNull();
 expect(screen.getByRole('textbox',{name:'メッセージ'}).value).toBe('失わない入力');
});
it('does not present receipt uploading as agent generation and restores the attachment after a failed turn',async()=>{
 const upload=deferred();api.uploadReceipt.mockReturnValue(upload.promise);
 api.sendMessage.mockRejectedValue(new Error('レシート処理に失敗'));
 render(<AgentChat onCommitted={vi.fn()}/>);
 const input=screen.getByLabelText('レシートファイル');
 await vi.waitFor(()=>expect(input.disabled).toBe(false));
 fireEvent.change(input,{target:{files:[new File(['image'],'receipt.png',{type:'image/png'})]}});
 await vi.waitFor(()=>expect(api.uploadReceipt).toHaveBeenCalledTimes(1));
 expect(screen.queryByRole('status',{name:'Agentが処理中'})).toBeNull();
 upload.resolve({id:'r',mimeType:'image/png'});
 await screen.findByRole('img',{name:'添付レシート'});
 fireEvent.click(screen.getByRole('button',{name:'送信'}));
 await screen.findByRole('alert');
 expect(screen.getByRole('img',{name:'添付レシート'}).getAttribute('src')).toContain('/receipts/r');
 expect(api.sendMessage.mock.calls[0][1].receiptId).toBe('r');
 expect(screen.getByRole('textbox',{name:'メッセージ'}).value).toBe('このレシートを読み取ってください。');
});
it('does not offer resend when only the sidebar refresh fails after a completed response',async()=>{
 api.listThreads.mockResolvedValueOnce([]).mockRejectedValueOnce(new Error('一覧を更新できません'));
 render(<AgentChat onCommitted={vi.fn()}/>);await start();
 await screen.findByRole('alert');
 expect(screen.getByRole('textbox',{name:'メッセージ'}).value).toBe('');
 expect(screen.queryByRole('button',{name:'再送'})).toBeNull();
 expect(screen.queryByRole('status',{name:'Agentが処理中'})).toBeNull();
});
it('sources_survive_message_reload and user citation syntax stays plain',async()=>{
 const source={id:'s',title:'店舗案内',url:'https://example.com/store'};
 api.listThreads.mockResolvedValue([{id:'t',title:'出典の会話'}]);
 api.sendMessage.mockRejectedValueOnce(new Error('通信が途切れました')).mockResolvedValueOnce({});
 api.getThread.mockResolvedValue({id:'t',messages:[{id:'u',role:'user',text:'検索 [source:s]',sources:[source]},{id:'a',role:'assistant',text:'店舗を確認 [source:s]',sources:[source]}],proposals:[]});
 render(<AgentChat onCommitted={vi.fn()}/>);await enterMessage('検索 [source:s]');await screen.findByRole('alert');
 fireEvent.click(screen.getByRole('button',{name:'再送'}));
 expect(await screen.findByRole('link',{name:/引用.*店舗案内/})).toBeTruthy();
 expect(screen.getByText('検索 [source:s]').closest('article').querySelector('a')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'新しい会話'}));
 await vi.waitFor(()=>expect(screen.queryByRole('link',{name:/引用/})).toBeNull());
 await vi.waitFor(()=>expect(screen.getByRole('button',{name:'出典の会話'}).disabled).toBe(false));
 fireEvent.click(screen.getByRole('button',{name:'出典の会話'}));
 expect(await screen.findByRole('link',{name:/店舗情報/})).toBeTruthy();
});
