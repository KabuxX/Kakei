import React from 'react';
import userEvent from '@testing-library/user-event';
import {it,expect,vi,beforeEach,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import OfflineTrajectoryMap from '../components/trajectory/OfflineTrajectoryMap.jsx';
const state=vi.hoisted(()=>({maps:[],markers:[],supported:true,protocols:[]}));
vi.mock('maplibre-gl',()=>({addProtocol:vi.fn((...args)=>state.protocols.push(args)),removeProtocol:vi.fn(),Map:class{constructor(opts){this.opts=opts;this.handlers={};this.sources={};this.fitBounds=vi.fn();this.resize=vi.fn();this.remove=vi.fn();state.maps.push(this);}on(name,fn){this.handlers[name]=fn;}off=vi.fn();addSource(id,source){this.sources[id]={...source,setData:vi.fn()};}getSource(id){return this.sources[id];}addLayer=vi.fn();},Marker:class{constructor({element}){this.element=element;state.markers.push(this);}setLngLat(){return this;}addTo(map){map.opts.container.append(this.element);return this;}remove(){this.element.remove();}}}));
vi.mock('pmtiles',()=>({Protocol:class{tile=vi.fn();add=vi.fn();},PMTiles:class{constructor(source){this.source=source;}}}));
vi.mock('../../demo/maps/style.js',()=>({createOfflineStyle:()=>({version:8,sources:{},layers:[]})}));
const day={date:'2026-10-01',events:[{id:'a',coordinates:[139.7,35.6],place:{name:'A'}},{id:'b',coordinates:[139.8,35.7],place:{name:'B',coordinateEvidence:{status:'estimated'}}}],segments:[{fromEventId:'a',toEventId:'b',stageNumber:1,coordinates:[[139.7,35.6],[139.8,35.7]]}]};
beforeEach(()=>{state.maps=[];state.markers=[];state.protocols=[];state.supported=true;vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockImplementation(()=>state.supported?{getExtension:()=>null}:null);vi.stubGlobal('ResizeObserver',class{observe=vi.fn();disconnect=vi.fn();});vi.stubGlobal('matchMedia',()=>({matches:true}));});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
function load(){state.maps.at(-1).handlers.load();}
it('uses bounded map, local protocol, selectable numbered markers, updates without recreation and cleans up',async()=>{
 const select=vi.fn();const view=render(<OfflineTrajectoryMap day={day} selectedEventId="a" onSelectEvent={select}/>);expect(screen.getByRole('status').textContent).toContain('準備');const map=state.maps[0];expect(map.opts.maxZoom).toBe(16);expect(map.opts.maxBounds).toEqual([[138.90,35.45],[139.95,35.95]]);expect(state.protocols).toHaveLength(1);load();await screen.findByRole('button',{name:'1. A'});screen.getByRole('button',{name:'2. B（推定位置）'}).focus();await userEvent.keyboard('{Enter}');expect(select).toHaveBeenCalledWith('b');expect(map.fitBounds.mock.calls[0][1]).toMatchObject({maxZoom:16,duration:0});
 view.rerender(<OfflineTrajectoryMap day={day} selectedEventId="b" onSelectEvent={select}/>);expect(screen.getByRole('button',{name:'2. B（推定位置）'}).getAttribute('aria-pressed')).toBe('true');expect(state.maps).toHaveLength(1);
 view.rerender(<OfflineTrajectoryMap day={{...day,date:'2026-10-02',events:[] ,segments:[]}}/>);expect(map.resize).toHaveBeenCalled();expect(map.sources.stops.setData).toHaveBeenCalled();view.unmount();expect(map.remove).toHaveBeenCalled();expect(document.querySelector('.offline-trajectory-marker')).toBeNull();
});
it('keeps sources readable through failure and retries successfully',async()=>{
 render(<OfflineTrajectoryMap day={day}/>);state.maps[0].handlers.error({error:new Error('tile')});expect(await screen.findByText(/地図を読み込めません/)).toBeTruthy();expect(screen.getByRole('link',{name:/地図の出典/})).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'地図を再試行'}));load();expect(await screen.findByRole('button',{name:'1. A'})).toBeTruthy();
});
it('explains unavailable WebGL with timeline remaining available',()=>{state.supported=false;render(<OfflineTrajectoryMap day={day}/>);expect(screen.getByText(/WebGL/)).toBeTruthy();expect(state.maps).toHaveLength(0);});
