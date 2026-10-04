import React from 'react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';

// Keep the parent, offline component, protocol, PMTiles cache and Source real.
// WebGL is the boundary that jsdom cannot render.
const state=vi.hoisted(()=>({protocol:null,reads:[],maps:[],removals:0}));
vi.mock('@kakei/runtime',()=>({loadTrajectoryMap:()=>import('../components/trajectory/OfflineTrajectoryMap.jsx')}));
vi.mock('../lib/api.js',()=>({
 listTrajectoryDates:async()=>['2026-10-01','2026-10-02'],
 loadTrajectoryDay:async date=>({places:{p:{name:'保存地点',coordinates:[139.7,35.6],placeEvidence:'user'}},days:[{date,events:[{id:`${date}-event`,placeId:'p',time:null,timeEvidence:'unknown'}],legs:[]}]}),
}));
vi.mock('maplibre-gl',()=>({
 setWorkerUrl:vi.fn(),addProtocol:(_,handler)=>{state.protocol=handler;},removeProtocol:()=>{state.protocol=null;state.removals++;},
 Map:class{
  constructor(options){this.handlers={};this.options=options;state.maps.push(this);const read=state.protocol({url:options.style.sources.basemap.url,type:'json'},new AbortController());read.catch(()=>{});state.reads.push(read);}
  on(name,fn){this.handlers[name]=fn;}off(){}remove(){this.removed=true;}resize(){}fitBounds(){}addLayer(){}addSource(){}getSource(){return null;}
 },Marker:class{},
}));
function archive(){
 const bytes=new Uint8Array(16384),view=new DataView(bytes.buffer);
 bytes.set(new TextEncoder().encode('PMTiles'));bytes[7]=3;
 view.setUint32(8,127,true);view.setUint32(16,5,true);
 view.setUint32(56,132,true);view.setUint32(64,3,true);
 bytes.set([1,0,1,3,1],127);bytes.set([11,22,33],132);
 bytes[97]=1;bytes[98]=1;bytes[99]=1;bytes[101]=14;
 view.setInt32(102,1389000000,true);view.setInt32(106,354500000,true);
 view.setInt32(110,1399500000,true);view.setInt32(114,359500000,true);
 return bytes;
}
beforeEach(()=>{vi.resetModules();state.protocol=null;state.reads=[];state.maps=[];state.removals=0;vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue({getExtension:()=>null});});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
it('reuses a delayed no-Range acquisition across actual date unmount and page remount',async()=>{
 const {default:Trajectory}=await import('../pages/Trajectory.jsx');
 let finish;const fetchArchive=vi.fn(()=>new Promise(resolve=>{finish=()=>resolve(new Response(archive(),{status:200}));}));
 vi.stubGlobal('fetch',fetchArchive);
 const view=render(<Trajectory/>);
 const select=await screen.findByRole('combobox',{name:'表示する日付'});
 await waitFor(()=>expect(fetchArchive).toHaveBeenCalledTimes(1));
 fireEvent.change(select,{target:{value:'2026-10-02'}});
 await waitFor(()=>expect(state.maps).toHaveLength(2));
 expect(state.maps[0].removed).toBe(true);expect(state.removals).toBe(1);
 expect(fetchArchive).toHaveBeenCalledTimes(1);
 // Resolve the original HTTP read after the replacement map has mounted.
 finish();
 const results=await Promise.all(state.reads);
 expect(results.map(r=>r.data.bounds)).toEqual([[138.9,35.45,139.95,35.95],[138.9,35.45,139.95,35.95]]);
 expect(fetchArchive).toHaveBeenCalledTimes(1);
 view.unmount();expect(state.protocol).toBeNull();
 render(<Trajectory/>);
 await waitFor(()=>expect(state.maps).toHaveLength(3));
 expect((await state.reads[2]).data.maxzoom).toBe(14);
 const tile=await state.protocol({url:`${state.maps[2].options.style.sources.basemap.url}/0/0/0`,type:'arrayBuffer'},new AbortController());
 expect(Array.from(tile.data)).toEqual([11,22,33]);
 expect(fetchArchive).toHaveBeenCalledTimes(1);
});
it('retries a rejected PMTiles header after map failure without retaining its rejected promise',async()=>{
 const {default:Trajectory}=await import('../pages/Trajectory.jsx');
 const fetchArchive=vi.fn().mockResolvedValueOnce(new Response(null,{status:404})).mockImplementation(async()=>new Response(archive(),{status:200}));
 vi.stubGlobal('fetch',fetchArchive);
 render(<Trajectory/>);
 await waitFor(()=>expect(state.maps).toHaveLength(1));
 await expect(state.reads[0]).rejects.toThrow('Archive HTTP 404');
 // Deliver MapLibre's archive failure to the real component's error listener.
 act(()=>state.maps[0].handlers.error());
 fireEvent.click(await screen.findByRole('button',{name:'地図を再試行'}));
 await waitFor(()=>expect(state.maps).toHaveLength(2));
 expect((await state.reads[1]).data.maxzoom).toBe(14);
 expect(fetchArchive).toHaveBeenCalledTimes(2);
});
