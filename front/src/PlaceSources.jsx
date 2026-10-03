import React from 'react';

function safeUrl(value){
  if(typeof value!=='string'||/[\s\\]/.test(value))return null;
  try {const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password?value:null;}catch{return null;}
}
function validSources(sources){return Array.isArray(sources)?sources.filter(s=>s&&typeof s.id==='string'&&safeUrl(s.url)):[];}
function ExternalLink({href,children,...props}){return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}<span className="sr-only">（新しいタブで開く）</span></a>;}

export function renderCitedText(text,sources=[]){
  const known=new Map(validSources(sources).map(s=>[s.id,s]));
  return String(text||'').split(/(\[source:[^\]\s]+\])/g).map((part,index)=>{
    const match=/^\[source:([^\]]+)\]$/.exec(part),source=match&&known.get(match[1]);
    return source?<ExternalLink key={index} href={source.url} className="place-citation" aria-label={`引用: ${source.title||'店舗情報'}（新しいタブで開く）`}>[{[...known.keys()].indexOf(source.id)+1}]</ExternalLink>:part;
  });
}
export default function PlaceSources({sources=[],geocoding,sourceUrl,attribution}){
  const valid=validSources(sources),legacy=safeUrl(sourceUrl);
  if(!valid.length&&!legacy&&!attribution&&!geocoding)return null;
  return <div className="place-sources">
    {valid.map(s=><ExternalLink key={s.id} href={s.url}>店舗情報 · {s.title||'出典'}</ExternalLink>)}
    {!valid.length&&legacy&&<ExternalLink href={legacy}>地点の出典を見る</ExternalLink>}
    {geocoding?.provider==='mapbox'?<span>座標: © Mapbox · {geocoding.verification==='needs_confirmation'?'住所表記は一致・位置の確認が必要':geocoding.verification==='user_confirmed'?`利用者が住所と地図を確認済み${geocoding.accuracy==='interpolated'?'・補間位置':''}`:geocoding.accuracy==='interpolated'?'住所に基づく補間位置（実際の入口とは異なる場合があります）':'住所を照合'}</span>:attribution&&<span>{attribution}</span>}
  </div>;
}

export function unresolvedReason(code){
 const reasons={address_precision_unconfirmed:'番地までの位置を確認できません。',address_not_found:'住所に一致する位置が見つかりません。',ambiguous_address:'住所に複数の位置が一致しました。',name_mismatch:'店舗名の一致を確認できません。',branch_unconfirmed:'支店名を確認できません。',locality_unconfirmed:'地域の一致を確認できません。',country_unconfirmed:'国を確認できません。',country_mismatch:'住所の国が一致しません。',outside_region:'指定地域と離れています。',address_mismatch:'住所が一致しません。',address_match_unconfirmed:'番地を含む住所の一致を確認できません。',address_number_missing:'番地を確認できません。',accuracy_unconfirmed:'座標の精度を確認できません。'};
 return reasons[code]||'位置を確認できませんでした。地域や住所を補足して再検索できます。';
}
