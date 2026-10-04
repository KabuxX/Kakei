import manifest from '../../demo/maps/manifest.json';
import {stageColor} from './trajectory-display.js';
const collection=features=>({type:'FeatureCollection',features});
export function offlineCoordinate(coordinates){
 const [west,south,east,north]=manifest.bounds;
 return Array.isArray(coordinates)&&coordinates.length===2&&coordinates.every(Number.isFinite)&&coordinates[0]>=west&&coordinates[0]<=east&&coordinates[1]>=south&&coordinates[1]<=north;
}
export function offlineFeatures(day){
 const allowed=new Map();
 const stops=day.events.flatMap((event,index)=>{
  if(event.locationStatus==='needs_review'||event.place?.demoPositionUnconfirmed||!offlineCoordinate(event.coordinates))return [];
  allowed.set(event.id,index);
  return [{type:'Feature',geometry:{type:'Point',coordinates:[...event.coordinates]},properties:{eventId:event.id,number:index+1,name:event.place?.name||'地点',estimated:event.place?.coordinateEvidence?.status==='estimated'}}];
 });
 const segments=day.segments.flatMap(segment=>{
  const from=allowed.get(segment.fromEventId),to=allowed.get(segment.toEventId);
  if(from===undefined||to!==from+1||!Array.isArray(segment.coordinates)||segment.coordinates.length<2||!segment.coordinates.every(offlineCoordinate))return [];
  return [{type:'Feature',geometry:{type:'LineString',coordinates:segment.coordinates.map(c=>[...c])},properties:{stageNumber:segment.stageNumber,color:stageColor(segment.stageNumber).hex}}];
 });
 return {stops:collection(stops),segments:collection(segments)};
}
