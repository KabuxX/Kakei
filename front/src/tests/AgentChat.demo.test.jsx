import React,{act} from 'react';import {createRoot} from 'react-dom/client';import {it,expect,vi} from 'vitest';
vi.mock('@kakei/runtime',()=>import('../../demo/runtime.js'));
import AgentChat from '../pages/AgentChat.jsx';import {AgentThreads} from '../components/agent/AgentControls.jsx';import AgentProposal from '../components/agent/AgentProposal.jsx';import snapshot from '../../demo/data/snapshot.json';
it('keeps saved messages, differences and originals while hiding composer and thread writes',async()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;const host=document.createElement('div');document.body.append(host);const root=createRoot(host);const thread=snapshot.threads.find(t=>t.proposals.some(p=>p.metadata?.receiptReview));const session={thread,threads:snapshot.threads,draft:{text:'',receipt:null},status:{available:false},select:async()=>true};
 await act(async()=>root.render(<><AgentThreads session={session} readOnly/><AgentChat session={session} readOnly/></>));expect(host.textContent).toContain(thread.messages[0].text);expect(host.querySelector('textarea')).toBeNull();expect(host.querySelector('[aria-label="新しい会話"]')).toBeNull();expect(host.querySelector('.agent-actions')).toBeNull();expect(host.querySelector('a[href*="demo-data/receipts/"]')).not.toBeNull();await act(async()=>root.unmount());host.remove();
});
it('renders pending state at snapshot time without approval controls',async()=>{
 const clock=vi.spyOn(Date,'now').mockReturnValue(4102444800000);const host=document.createElement('div');const root=createRoot(host);await act(async()=>root.render(<AgentProposal readOnly proposal={{id:'p',revision:1,status:'pending',expiresAt:1792000000,commands:[],before:[],after:[],metadata:{}}}/>));expect(host.textContent).toContain('確認待ち');expect(host.querySelector('button')).toBeNull();await act(async()=>root.render(<AgentProposal readOnly proposal={{id:'expired',revision:1,status:'pending',expiresAt:1,commands:[],before:[],after:[],metadata:{}}}/>));expect(host.textContent).toContain('期限切れ');expect(host.querySelector('button')).toBeNull();await act(async()=>root.unmount());clock.mockRestore();
});

it('explains a snapshot with no conversations without inviting creation',async()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;const host=document.createElement('div');const root=createRoot(host);
 await act(async()=>root.render(<AgentChat readOnly session={{threads:[],draft:{text:'',receipt:null},status:{available:false}}}/>));
 expect(host.textContent).toContain('保存済みの会話はありません。');expect(host.textContent).not.toContain('選んでください');expect(host.querySelector('form')).toBeNull();await act(async()=>root.unmount());
});
