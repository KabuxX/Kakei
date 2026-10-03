import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import AgentProposal from './AgentProposal.jsx';
import * as api from './lib/agent-api.js';
vi.mock('./lib/agent-api.js');afterEach(cleanup);
it('selects server bound candidate ID and blocks approval until resolved',async()=>{
 const candidate={id:'c1',name:'同名店',address:'New York',coordinates:[-73,40],sourceUrl:'https://example.com',attribution:'OSM'};
 const proposal={id:'p',revision:1,status:'pending',expiresAt:Date.now()/1000+86400,commands:[{kind:'trajectory.create',identity:{kind:'day',date:'2027-01-04'},data:{events:[],legs:[]}}],before:[null],after:[{date:'2027-01-04',events:[],legs:[]}],metadata:{placeCandidates:[{placeId:'x',query:'同名店',candidates:[candidate,{...candidate,id:'c2',address:'London'}]}]}};
 const onChange=vi.fn();api.selectPlaceCandidate.mockResolvedValue({...proposal,revision:2});
 render(<AgentProposal proposal={proposal} onChange={onChange} onCommitted={vi.fn()} busy={false} setBusy={vi.fn()}/>);
 expect(screen.getByRole('button',{name:'確認して保存'}).disabled).toBe(true);
 fireEvent.click(screen.getByRole('radio',{name:/New York/}));
 fireEvent.click(screen.getByRole('button',{name:'この地点を選ぶ'}));
 await vi.waitFor(()=>expect(api.selectPlaceCandidate).toHaveBeenCalledWith('p',1,'c1'));
 expect(onChange).toHaveBeenCalled();
});
