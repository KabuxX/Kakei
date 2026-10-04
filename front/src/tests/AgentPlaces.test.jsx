import React from 'react';
import {geoloniaEvidence} from '../../tests/fixtures/geolonia.js';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import AgentProposal from '../components/agent/AgentProposal.jsx';
import * as api from '../lib/agent-api.js';
vi.mock('../lib/agent-api.js');afterEach(cleanup);
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
it('keeps candidate choices available after selection while allowing approval',async()=>{
 const candidate={id:'c1',name:'同名店',address:'New York',coordinates:[-73,40]};
 const proposal={id:'p',revision:2,status:'pending',expiresAt:Date.now()/1000+86400,commands:[],before:[],after:[],metadata:{placeCandidates:[{placeId:'x',query:'同名店',selectedCandidateId:'c1',candidates:[candidate,{...candidate,id:'c2',address:'London'}]}]}};
 api.selectPlaceCandidate.mockResolvedValue({...proposal,revision:3});
 render(<AgentProposal proposal={proposal} onChange={vi.fn()} onCommitted={vi.fn()} busy={false} setBusy={vi.fn()}/>);
 expect(screen.getByRole('button',{name:'確認して保存'}).disabled).toBe(false);
 fireEvent.click(screen.getByRole('radio',{name:/London/}));
 fireEvent.click(screen.getByRole('button',{name:'この地点を選ぶ'}));
 await vi.waitFor(()=>expect(api.selectPlaceCandidate).toHaveBeenCalledWith('p',2,'c2'));
});
it('unlocated_store_cannot_be_selected',()=>{
 const proposal={id:'p',revision:1,status:'pending',expiresAt:Date.now()/1000+86400,commands:[],before:[],after:[],metadata:{placeCandidates:[{placeId:'x',query:'店舗',candidates:[],unlocatedCandidates:[{id:'w',name:'住所のみ判明した店舗',address:'福岡市',unresolved:['address_precision_unconfirmed'],sources:[{id:'s',title:'店舗案内',url:'https://example.com/store'}]}]}]}};
 render(<AgentProposal proposal={proposal} onChange={vi.fn()} onCommitted={vi.fn()} busy={false} setBusy={vi.fn()}/>);
 expect(screen.getByText('位置未確認')).toBeTruthy();expect(screen.getByText('住所のみ判明した店舗')).toBeTruthy();
 expect(screen.queryByRole('radio')).toBeNull();expect(screen.getByRole('link',{name:/店舗情報/})).toBeTruthy();
 expect(screen.getByText(/番地まで/)).toBeTruthy();
});
it('shows result truncation even when a legacy result has no error message',()=>{
 const proposal={id:'p',revision:1,status:'pending',expiresAt:Date.now()/1000+86400,commands:[],before:[],after:[],metadata:{placeCandidates:[{placeId:'x',query:'店舗',candidates:[],truncated:true,omittedCandidates:3,omittedSources:2}]}};
 render(<AgentProposal proposal={proposal} onChange={vi.fn()} onCommitted={vi.fn()} busy={false} setBusy={vi.fn()}/>);
 expect(screen.getByText(/候補3件・出典2件を省略/)).toBeTruthy();
});
it('requires address and map confirmation for an uncertain provider match',async()=>{
 const candidate={id:'review',name:'店舗',address:'福岡市天神2-11-3',coordinates:[130.4,33.59],geocoding:{provider:'mapbox',verification:'needs_confirmation',matchedAddress:'日本, 福岡市天神２丁目１１番３号',accuracy:'rooftop'}};
 const proposal={id:'p',revision:1,status:'pending',expiresAt:Date.now()/1000+86400,commands:[],before:[],after:[],metadata:{placeCandidates:[{placeId:'x',query:'店舗',candidates:[candidate]}]}};
 api.selectPlaceCandidate.mockResolvedValue({...proposal,revision:2});
 render(<AgentProposal proposal={proposal} onChange={vi.fn()} onCommitted={vi.fn()} busy={false} setBusy={vi.fn()}/>);
 fireEvent.click(screen.getByRole('radio'));
 expect(screen.getByRole('button',{name:'この地点を選ぶ'}).disabled).toBe(true);
 expect(screen.getByRole('link',{name:/地図で位置を確認/}).getAttribute('href')).toContain('mlat=33.59');
 expect(screen.getByText(/Mapboxの照合情報が不十分/)).toBeTruthy();
 fireEvent.click(screen.getByRole('checkbox',{name:'住所と地図を確認しました'}));
 fireEvent.click(screen.getByRole('button',{name:'この地点を選ぶ'}));
 await vi.waitFor(()=>expect(api.selectPlaceCandidate).toHaveBeenCalledWith('p',1,'review',true));
});
it('resets confirmation when switching published and estimated candidates',async()=>{
 const base={name:'店舗',address:'福岡市',coordinates:[130.4,33.59],sources:[],coordinateEvidence:{status:'published',method:'page_text',verification:'needs_confirmation',note:'誤差未確認'}};
 const candidates=[{...base,id:'published'},{...base,id:'estimated',address:'福岡市（施設）',coordinateEvidence:{...base.coordinateEvidence,status:'estimated',method:'same_building',precision:'building',basis:{anchorName:'施設',anchorAddress:'福岡市'}}}];
 const proposal={id:'p',revision:1,status:'pending',expiresAt:Date.now()/1000+86400,commands:[],before:[],after:[],metadata:{placeCandidates:[{placeId:'x',query:'店舗',candidates}]}};
 api.selectPlaceCandidate.mockResolvedValue({...proposal,revision:2});
 render(<AgentProposal proposal={proposal} onChange={vi.fn()} onCommitted={vi.fn()} busy={false} setBusy={vi.fn()}/>);
 fireEvent.click(screen.getAllByRole('radio')[0]);fireEvent.click(screen.getByRole('checkbox',{name:'住所・出典と地図の位置を確認しました'}));
 expect(screen.getByRole('button',{name:'この地点を選ぶ'}).disabled).toBe(false);
 fireEvent.click(screen.getAllByRole('radio')[1]);expect(screen.getByRole('button',{name:'この地点を選ぶ'}).disabled).toBe(true);
 const checkbox=screen.getByRole('checkbox',{name:'この推定位置を確認しました'});expect(checkbox.checked).toBe(false);fireEvent.click(checkbox);fireEvent.click(screen.getByRole('button',{name:'この地点を選ぶ'}));
 await vi.waitFor(()=>expect(api.selectPlaceCandidate).toHaveBeenCalledWith('p',1,'estimated',true));
});
it('switching_geolonia_candidate_resets_confirmation',()=>{
 const candidates=[{id:'geo',name:'店舗',address:'東京都文京区本郷1-2-3',coordinates:[139.7,35.7],sources:[],coordinateEvidence:geoloniaEvidence},{id:'web',name:'店舗',address:'東京都文京区本郷1-2-3',coordinates:[139.7,35.7],sources:[],coordinateEvidence:{status:'published',method:'page_text',verification:'needs_confirmation'}}];
 const proposal={id:'p',revision:1,status:'pending',expiresAt:Date.now()/1000+86400,commands:[],before:[],after:[],metadata:{placeCandidates:[{placeId:'x',query:'店舗',candidates}]}};
 render(<AgentProposal proposal={proposal} onChange={vi.fn()} onCommitted={vi.fn()} busy={false} setBusy={vi.fn()}/>);
 fireEvent.click(screen.getAllByRole('radio')[0]);expect(screen.getByRole('button',{name:'この地点を選ぶ'}).disabled).toBe(true);
 fireEvent.click(screen.getByRole('checkbox',{name:'住所・出典と地図の位置を確認しました'}));
 expect(screen.getByRole('button',{name:'この地点を選ぶ'}).disabled).toBe(false);
 fireEvent.click(screen.getAllByRole('radio')[1]);expect(screen.getByRole('checkbox',{name:'住所・出典と地図の位置を確認しました'}).checked).toBe(false);
 expect(screen.getByRole('button',{name:'この地点を選ぶ'}).disabled).toBe(true);
});
