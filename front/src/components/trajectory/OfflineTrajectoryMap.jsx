import React,{useEffect,useRef,useState} from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {Protocol,PMTiles} from 'pmtiles';
import {createOfflineStyle} from '../../../demo/maps/style.js';
import {createArchiveSource} from '../../../demo/maps/archive-source.js';
import manifest from '../../../demo/maps/manifest.json';
import {offlineFeatures} from '../../lib/offline-trajectory.js';
const asset=path=>`${import.meta.env.BASE_URL}${path}`;
// A protocol may be shared by overlapping mounted maps; release only its final user.
let protocol,protocolUsers=0;
function acquireProtocol(){
 if(!protocol){protocol=new Protocol();const url=new URL(asset('maps/tokyo.pmtiles'),location.href).href;protocol.add(new PMTiles(createArchiveSource(url,{maxBytes:manifest.bytes})));maplibregl.addProtocol('pmtiles',protocol.tile);}
 protocolUsers++;
 return ()=>{if(--protocolUsers===0){maplibregl.removeProtocol('pmtiles');protocol=undefined;}};
}
export default function OfflineTrajectoryMap({day,selectedEventId,onSelectEvent}){
 const container=useRef(null),mapRef=useRef(null),markers=useRef([]),current=useRef({day,selectedEventId,onSelectEvent});
 current.current={day,selectedEventId,onSelectEvent};
 const [message,setMessage]=useState('地図を準備しています…'),[attempt,setAttempt]=useState(0);
 const clearMarkers=()=>{markers.current.forEach(({marker,button})=>{button.onclick=null;marker.remove();});markers.current=[];};
 const update=()=>{
  const map=mapRef.current;if(!map?.getSource('stops'))return;
  const data=offlineFeatures(current.current.day);map.getSource('stops').setData(data.stops);map.getSource('segments').setData(data.segments);clearMarkers();
  data.stops.features.forEach(feature=>{
   const {eventId,number,name,estimated}=feature.properties;const button=document.createElement('button');button.type='button';button.className=`offline-trajectory-marker${estimated?' is-estimated':''}`;button.textContent=String(number);button.setAttribute('aria-label',`${number}. ${name}${estimated?'（推定位置）':''}`);button.setAttribute('aria-pressed',String(eventId===current.current.selectedEventId));button.onclick=()=>current.current.onSelectEvent?.(eventId);
   const marker=new maplibregl.Marker({element:button}).setLngLat(feature.geometry.coordinates).addTo(map);markers.current.push({marker,button,eventId});
  });
  const coords=[...data.stops.features.map(f=>f.geometry.coordinates),...data.segments.features.flatMap(f=>f.geometry.coordinates)];
  const bounds=coords.length?[[Math.min(...coords.map(c=>c[0])),Math.min(...coords.map(c=>c[1]))],[Math.max(...coords.map(c=>c[0])),Math.max(...coords.map(c=>c[1]))]]:[[manifest.bounds[0],manifest.bounds[1]],[manifest.bounds[2],manifest.bounds[3]]];
  map.resize();map.fitBounds(bounds,{padding:56,maxZoom:manifest.displayMaxZoom,duration:globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches?0:300});
 };
 useEffect(()=>{
  let map,release,observer,active=true;setMessage('地図を準備しています…');
  const dispose=()=>{observer?.disconnect();clearMarkers();if(map){map.off('load',loaded);map.off('error',failed);map.remove();map=undefined;}mapRef.current=null;release?.();release=undefined;};
  const failed=()=>{if(active){dispose();setMessage('地図を読み込めませんでした。時系列はそのまま確認できます。');}};
  const loaded=()=>{if(!active)return;try{map.addSource('stops',{type:'geojson',data:{type:'FeatureCollection',features:[]}});map.addSource('segments',{type:'geojson',data:{type:'FeatureCollection',features:[]}});map.addLayer({id:'trajectory-segments',type:'line',source:'segments',paint:{'line-color':['get','color'],'line-width':6,'line-opacity':0.9}});update();setMessage('');}catch{failed();}};
  try{
   const probe=document.createElement('canvas'),context=probe.getContext('webgl2');
   context?.getExtension('WEBGL_lose_context')?.loseContext();
   if(!context)setMessage('WebGLが利用できないため地図を表示できません。時系列はそのまま確認できます。');
   else{release=acquireProtocol();map=new maplibregl.Map({container:container.current,style:createOfflineStyle(new URL(import.meta.env.BASE_URL,location.href).href),center:[139.7,35.6],zoom:11,maxZoom:manifest.displayMaxZoom,maxBounds:[[manifest.bounds[0],manifest.bounds[1]],[manifest.bounds[2],manifest.bounds[3]]],attributionControl:false});mapRef.current=map;map.on('load',loaded);map.on('error',failed);if(globalThis.ResizeObserver){observer=new ResizeObserver(()=>map?.resize());observer.observe(container.current);}}
  }catch{failed();}
  return ()=>{active=false;dispose();};
 },[attempt]);
 useEffect(()=>{update();},[day]);
 useEffect(()=>{markers.current.forEach(({button,eventId})=>button.setAttribute('aria-pressed',String(eventId===selectedEventId)));},[selectedEventId]);
 return <div className="trajectory-offline-map"><div className="trajectory-map-frame" role="region" aria-label={`${day.date} の推定移動地図`}><div ref={container} className="trajectory-map-canvas"/>{message&&<div className="trajectory-map-message" role="status"><div><p>{message}</p>{!message.includes('準備')&&<button type="button" className="secondary-button" onClick={()=>setAttempt(n=>n+1)}>地図を再試行</button>}</div></div>}</div><p className="trajectory-map-usage">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a> · Protomaps · Natural Earth · <a href={asset('maps/licenses/MAP-LICENSE.txt')} target="_blank" rel="noopener noreferrer">地図の出典・ライセンス</a> · <a href={asset('maps/licenses/OFL.txt')} target="_blank" rel="noopener noreferrer">フォント OFL-1.1</a></p></div>;
}
