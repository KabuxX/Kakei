import React,{useEffect,useRef,useState} from 'react';
import {GoogleAttributions} from './PlaceSources.jsx';
import {loadGoogleMaps,subscribeGoogleMapsAuthFailure} from './lib/google-maps.js';
import {request} from './lib/api.js';
import {stageColor} from './lib/trajectory-display.js';
export default function GoogleTrajectoryMap({day,selectedEventId,onSelectEvent}) {
 const container=useRef(null),markers=useRef([]),select=useRef(onSelectEvent),selected=useRef(selectedEventId);
 select.current=onSelectEvent;selected.current=selectedEventId;
 const [message,setMessage]=useState('地図を準備しています…'),[attempt,setAttempt]=useState(0);
 useEffect(()=>{
  let active=true,map,lines=[];setMessage('地図を準備しています…');
  const release=()=>{markers.current.forEach(m=>{m.content.onclick=null;m.map=null;});markers.current=[];lines.forEach(line=>line.setMap(null));map?.unbindAll?.();container.current?.replaceChildren();};
  const releaseAuth=subscribeGoogleMapsAuthFailure(()=>{if(active){release();setMessage('Google Mapsの認証に失敗しました。ブラウザ用キーの設定を確認して再試行してください。');}});
  (async()=>{
   const config=await request('GET','/api/map-config');
   if(!active)return;
   if(!config?.googleMapsBrowserKey)throw new Error('Google Mapsのブラウザ用キーを設定すると地図を表示できます。時系列はそのまま確認できます。');
   const {Map,Polyline,AdvancedMarkerElement}=await loadGoogleMaps({browserKey:config.googleMapsBrowserKey,mapId:config.googleMapId});
   if(!active)return;
   map=new Map(container.current,{center:{lng:139.7,lat:35.6},zoom:12,mapId:config.googleMapId||'DEMO_MAP_ID',gestureHandling:'cooperative'});
   day.segments.filter(s=>s.coordinates).forEach(segment=>lines.push(new Polyline({map,path:segment.coordinates.map(([lng,lat])=>({lng,lat})),strokeColor:stageColor(segment.stageNumber).hex,strokeWeight:6,strokeOpacity:0.9})));
   day.events.forEach((event,index)=>{
    if(!event.coordinates)return;
    const content=document.createElement('button');content.type='button';content.className='google-trajectory-marker';content.textContent=String(index+1);content.setAttribute('aria-label',`${index+1}. ${event.place.name}`);content.setAttribute('aria-pressed',String(selected.current===event.id));content.onclick=()=>select.current?.(event.id);
    const [lng,lat]=event.coordinates;const marker=new AdvancedMarkerElement({map,position:{lng,lat},content,title:`${index+1}. ${event.place.name}`});marker.eventId=event.id;markers.current.push(marker);
   });
   if(day.bounds){const [west,south,east,north]=day.bounds;if(west===east&&south===north){map.setCenter({lng:west,lat:south});map.setZoom(15);}else map.fitBounds({west,south,east,north},56);}
   setMessage('');
  })().catch(error=>{if(active){release();setMessage(error.message?.includes('ブラウザ用キー')?error.message:'地図を読み込めませんでした。時系列はそのまま確認できます。');}});
  return()=>{active=false;releaseAuth?.();release();};
 },[day,attempt]);
 useEffect(()=>{markers.current.forEach(marker=>marker.content.setAttribute('aria-pressed',String(marker.eventId===selectedEventId)));},[selectedEventId]);
 return <div className="trajectory-google-map">
  <div className="trajectory-map-frame" role="region" aria-label={`${day.date} の推定移動地図`}>
   <div ref={container} className="trajectory-map-canvas"/>
   {message&&<div className="trajectory-map-message" role="status"><div><p>{message}</p><button type="button" className="secondary-button" onClick={()=>setAttempt(n=>n+1)}>地図を再試行</button></div></div>}
  </div>
  {day.events.some(e=>e.place.provider==='google')&&<GoogleAttributions attributions={[...new Map(day.events.flatMap(e=>e.place.attributions||[]).map(a=>[`${a.provider} ${a.providerUri}`,a])).values()]}/>}
  <p className="trajectory-map-usage"><a href="/google-maps-usage.html" target="_blank" rel="noopener noreferrer">Google Mapsの利用・データ取扱い</a></p>
 </div>;
}
