import {it,expect} from 'vitest';
import {offlineFeatures} from './offline-trajectory.js';
import {buildTrajectoryDays} from './trajectory-model.js';
import snapshot from '../../demo/data/snapshot.json';
const event=(id,coordinates=[139.7,35.6],extra={})=>({id,coordinates,place:{name:id},...extra});
it('preserves visit numbers and never bridges skipped events',()=>{
 const day={events:[event('a'),event('b',null),event('c')],segments:[{fromEventId:'a',toEventId:'c',stageNumber:1,coordinates:[[139.7,35.6],[139.7,35.6]]}]};
 expect(offlineFeatures(day).stops.features.map(f=>f.properties.number)).toEqual([1,3]);expect(offlineFeatures(day).segments.features).toHaveLength(0);
});
it('rejects review, unconfirmed, outside and invalid coordinates, including vias',()=>{
 const events=[event('a'),event('b',[139.8,35.7])];
 const segment={fromEventId:'a',toEventId:'b',stageNumber:2,coordinates:[events[0].coordinates,[130,33],events[1].coordinates]};
 expect(offlineFeatures({events,segments:[segment]}).segments.features).toHaveLength(0);
 for(const e of [event('x',[130,33]),event('x',[NaN,35.6]),event('x',undefined,{locationStatus:'needs_review'}),event('x',undefined,{place:{demoPositionUnconfirmed:true}})])expect(offlineFeatures({events:[e],segments:[]}).stops.features).toHaveLength(0);
});
it('handles zero and one stop and retains estimated evidence and stage colors',()=>{
 expect(offlineFeatures({events:[],segments:[]}).stops.features).toHaveLength(0);
 const a=event('a',undefined,{place:{name:'A',coordinateEvidence:{status:'estimated'}}}),b=event('b',[139.8,35.7]);
 expect(offlineFeatures({events:[a],segments:[]}).stops.features[0].properties.estimated).toBe(true);
 expect(offlineFeatures({events:[a,b],segments:[{fromEventId:'a',toEventId:'b',stageNumber:1,coordinates:[a.coordinates,b.coordinates]}]}).segments.features[0].properties.color).toBe('#415eee');
});
it('renders all thirteen snapshot days without mutating data or exposing outside coordinates',()=>{
 const before=JSON.stringify(snapshot);const days=buildTrajectoryDays(snapshot.transactions,snapshot.timeline);expect(days.size).toBe(13);
 for(const day of days.values()){const features=offlineFeatures(day);expect(features.stops.features).toHaveLength(day.events.length);for(const f of features.segments.features)expect(f.geometry.coordinates.every(c=>c[0]>=138.9&&c[0]<=139.95&&c[1]>=35.45&&c[1]<=35.95)).toBe(true);}
 expect(JSON.stringify(snapshot)).toBe(before);
});
