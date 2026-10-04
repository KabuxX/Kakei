import React,{useState} from 'react';
import {afterEach,expect,it} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {TransactionFields,RecordView} from '../components/agent/AgentProposal.jsx';
afterEach(cleanup);
it('does not turn omitted address into a delete while editing another field',()=>{
 function Harness(){const [command,set]=useState({kind:'transaction.update',identity:{id:'a'},data:{type:'expense',title:'旧取引',category:'食費'}});return <><TransactionFields command={command} index={0} onChange={set}/><output>{JSON.stringify(command.data)}</output></>;}
 render(<Harness/>);fireEvent.change(screen.getByLabelText('内容 1'),{target:{value:'変更'}});
 expect(JSON.parse(screen.getByRole('status').textContent)).not.toHaveProperty('merchantAddress');
 fireEvent.change(screen.getByLabelText('住所（任意）'),{target:{value:'住所A'}});fireEvent.change(screen.getByLabelText('住所（任意）'),{target:{value:''}});
 expect(JSON.parse(screen.getByRole('status').textContent).merchantAddress).toBeNull();
});
it('labels address additions, edits and removals in the proposal',()=>{
 render(<><RecordView value={{merchantAddress:'住所A'}}/><RecordView value={{merchantAddress:null}}/></>);
 expect(screen.getAllByText('取引先住所')).toHaveLength(2);expect(screen.getByText('住所A')).toBeTruthy();expect(screen.getByText('なし')).toBeTruthy();
});
