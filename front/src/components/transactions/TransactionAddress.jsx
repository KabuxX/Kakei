import React,{useEffect,useState} from 'react';
import GooglePlaceResults from '../places/GooglePlaceResults.jsx';
import DemoPlaceResults from '../places/DemoPlaceResults.jsx';
import {getTransactionAddress} from '../../lib/api.js';
export default function TransactionAddress({record,readOnly=false}) {
 const [places,setPlaces]=useState([]),[failed,setFailed]=useState(false),[attempt,setAttempt]=useState(0);
 useEffect(()=>{
  let active=true;setPlaces([]);setFailed(false);
  if(!record.merchantAddress&&!record.merchantPlace&&!readOnly)getTransactionAddress(record.id).then(context=>{if(active)setPlaces(context.places);}).catch(()=>{if(active)setFailed(true);});
  return ()=>{active=false;};
 },[record.id,record.merchantAddress,record.merchantPlace?.placeId,readOnly,attempt]);
 if(!record.merchantAddress&&record.merchantPlace) return <dd className="detail-address">{readOnly?<DemoPlaceResults placeIds={[record.merchantPlace.placeId]}/>:<GooglePlaceResults key={record.merchantPlace.placeId} placeIds={[record.merchantPlace.placeId]}/>}</dd>;
 const addresses=record.merchantAddress ? [record.merchantAddress] : [...new Set(places.map(p=>p.address).filter(Boolean))];
 if(!addresses.length && !failed)return null;
 return <dd className="detail-address">
  {addresses.map(address=><p key={address}>{address}</p>)}
  {failed && <div role="alert"><p>住所を読み込めませんでした。</p><button className="secondary-button" onClick={()=>setAttempt(n=>n+1)}>再読み込み</button></div>}
 </dd>;
}
