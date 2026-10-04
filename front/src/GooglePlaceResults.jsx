import React,{useEffect,useState} from 'react';
import {safeUrl} from './PlaceSources.jsx';
export default function GooglePlaceResults({placeIds=[]}) {
 const signature=JSON.stringify(placeIds),[state,setState]=useState({signature:null,items:[]});
 useEffect(()=>{
  let active=true;const controller=new AbortController();
  setState({signature,items:[]});
  Promise.all(placeIds.map(async id=>{
   try {const response=await fetch(`/api/places/google/${encodeURIComponent(id)}`,{signal:controller.signal,cache:'no-store'});if(!response.ok)throw new Error();return {id,...await response.json()};}
   catch{return {id,unavailable:true};}
  })).then(items=>{if(active)setState({signature,items});});
  return()=>{active=false;controller.abort();};
 },[signature]);
 if(!placeIds.length)return null;
 const items=state.signature===signature?state.items:[];
 return <div className="google-place-results" aria-label="Googleの地点情報">
  <a href="https://maps.google.com/" target="_blank" rel="noopener noreferrer" className="google-maps-attribution">Google Maps</a>
  {!items.length&&<p role="status">地点情報を読み込んでいます…</p>}
  {items.map(item=><div key={item.id}>{item.unavailable?<p>地点情報を取得できませんでした。</p>:<><strong>{item.name}</strong><p>{item.address}</p>{safeUrl(item.mapsUri)&&<a href={item.mapsUri} target="_blank" rel="noopener noreferrer">Google Mapsで見る</a>}{item.attributions?.map((a,i)=>safeUrl(a.providerUri)?<a key={i} href={a.providerUri} target="_blank" rel="noopener noreferrer">{a.provider}</a>:<span key={i}>{a.provider}</span>)}</>}</div>)}
 </div>;
}
