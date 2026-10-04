import React from 'react';
const methods={page_text:'ページ本文の掲載値',structured_geo:'店舗の構造化データ',map_pin_url:'店舗ピンの地図リンク',same_building:'同じ建物・施設を基準',relative_offset:'基準地点からの距離と方角',area_anchor:'地区・街区を基準'};
const precisions={building:'建物・施設内の推定',nearby:'基準地点付近の推定',area:'地区・街区内の推定'};
const directions={0:'北',45:'北東',90:'東',135:'南東',180:'南',225:'南西',270:'西',315:'北西'};
export default function CoordinateEvidence({evidence}){
 if(!evidence)return null;
 const estimated=evidence.status==='estimated',addressMatched=evidence.status==='address_matched',basis=evidence.basis;
 return <div className="coordinate-evidence">
  <strong className="coordinate-status">{addressMatched?'住所に対応する座標':estimated?'推定位置':'掲載座標'}</strong>
  <span>{addressMatched?'Geolonia · 番地・住居番号まで照合':methods[evidence.method]||'Web出典'}{estimated&&` · ${precisions[evidence.precision]||'範囲未確認'}`}</span>
  {addressMatched&&<><p>照合住所: {evidence.addressMatch?.matchedAddress}</p><span>Geolonia japanese-addresses-v2（加工して利用） · <a href="https://github.com/geolonia/japanese-addresses-v2" target="_blank" rel="noopener noreferrer">データセット<span className="sr-only">（新しいタブで開く）</span></a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0<span className="sr-only">（新しいタブで開く）</span></a></span></>}
  {basis&&<p>基準: {basis.anchorName} · {basis.anchorAddress}{evidence.method==='relative_offset'&&` · ${directions[basis.bearingDegrees]||'指定方角'}へ${basis.distanceMeters}m（直線）`}</p>}
  {evidence.note&&<p>{evidence.note}</p>}
  <span>{evidence.verification==='user_confirmed'?'利用者が位置を確認済み':'位置の確認が必要'}</span>
 </div>;
}
