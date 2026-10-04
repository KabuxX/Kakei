import React from 'react';
import {demoPlaces} from '@kakei/runtime';
import {safeUrl} from './PlaceSources.jsx';
export default function DemoPlaceResults({placeIds=[],places=demoPlaces}) {
 if(!placeIds.length)return null;
 return <section className="google-place-results" aria-label="DEMOの地点情報"><p>DEMO用に独立した出典で照合した地点</p>{placeIds.map(id=>{const p=places?.[id];return <div key={id}>{p?<><strong>{p.name}</strong><p>{p.address}</p><p>{p.demoPositionUnconfirmed?'DEMO用の位置は未確認':p.demoNote}</p>{safeUrl(p.sourceUrl)&&<a href={p.sourceUrl} target="_blank" rel="noopener noreferrer">地点の出典</a>}<small>{p.attribution}</small></>:<p>この検索結果のDEMO用情報はありません。</p>}</div>;})}</section>;
}
