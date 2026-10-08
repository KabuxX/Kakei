import React,{useState} from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import AgentProposal from '../components/agent/AgentProposal.jsx';
import * as api from '../lib/agent-api.js';
vi.mock('../lib/agent-api.js');
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('closes old edit session after reconfirmation and reopens the returned values',async()=>{
 const input={merchant:'店',branch:null,locality:null,merchantAddress:'本人住所'};
 const review={receiptId:'r',candidate:{merchant:'店',total:100,currency:'JPY'},missingFields:[],matches:[]};
 const command={kind:'transaction.create',identity:{},data:{title:'店',merchant:'店',merchantAddress:'本人住所',amount:100,items:[],type:'expense',category:'その他'}};
 const original={id:'p',threadId:'t',revision:1,status:'pending',expiresAt:Date.now()/1000+3600,commands:[command],before:[null],after:[command.data],metadata:{receiptReview:review,targetChoice:'new',receiptLocation:{input,method:'user_address'}}};
 api.getReceiptLocation.mockResolvedValue({id:'loc',receiptId:'r',revision:1,input,status:'resolved',expiresAt:Date.now()/1000+3600});
 api.reconfirmReceiptProposal.mockImplementation(async(id,body)=>({...original,revision:2,commands:[{...command,data:body.draft}],after:[body.draft]}));
 function Harness(){const [proposal,setProposal]=useState(original);return <AgentProposal proposal={proposal} onChange={setProposal} onCommitted={vi.fn()} busy={false} setBusy={vi.fn()}/>;}
 render(<Harness/>);
 fireEvent.click(screen.getByRole('button',{name:'内容を修正'}));
 fireEvent.change(screen.getByLabelText('金額 1'),{target:{value:'200'}});
 fireEvent.click(screen.getByRole('button',{name:'店舗・住所を再確認'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'変更案を確認'}).disabled).toBe(false));
 fireEvent.change(screen.getByLabelText('金額 1'),{target:{value:'300'}});
 fireEvent.submit(screen.getByRole('button',{name:'変更案を確認'}).closest('form'));
 await screen.findByText('確認待ち · 第2版');
 expect(screen.queryByRole('button',{name:'差分を更新'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'内容を修正'}));
 expect(screen.getByLabelText('金額 1').value).toBe('300');
});
