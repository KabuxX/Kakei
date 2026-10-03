import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import AgentChat from './AgentChat.jsx';
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
  await screen.findByRole('button',{name:'新しい会話'});
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
 const input=await screen.findByLabelText('レシートを添付');
 fireEvent.change(input,{target:{files:[new File(['image'],'receipt.png',{type:'image/png'})]}});
 expect(await screen.findByRole('img',{name:'添付レシート'})).toBeTruthy();
 expect(api.sendMessage).not.toHaveBeenCalled();expect(api.approve).not.toHaveBeenCalled();
});
