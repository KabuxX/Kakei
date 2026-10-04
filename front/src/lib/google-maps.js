let pending;
let sequence=0;
const loaded=()=>window.google?.maps?.Map&&window.google?.maps?.marker?.AdvancedMarkerElement;
const classes=()=>({Map:window.google.maps.Map,Polyline:window.google.maps.Polyline,AdvancedMarkerElement:window.google.maps.marker.AdvancedMarkerElement});
export function loadGoogleMaps({browserKey}) {
 if(!browserKey||typeof browserKey!=='string')return Promise.reject(new Error('Google Mapsのブラウザ用キーを設定してください。'));
 if(loaded())return Promise.resolve(classes());
 if(pending)return pending;
 pending=new Promise((resolve,reject)=>{
  const script=document.createElement('script'),callback=`__kakeiGoogleMaps${++sequence}`;
  script.dataset.kakeiGoogleMaps='';script.async=true;
  const params=new URLSearchParams({key:browserKey,loading:'async',callback,v:'quarterly',language:'ja',libraries:'maps,marker'});
  script.src=`https://maps.googleapis.com/maps/api/js?${params}`;
  const previousFailure=window.gm_authFailure;
  const clear=()=>{clearTimeout(timer);window[callback]=()=>{};window.gm_authFailure=previousFailure;};
  const fail=()=>{clear();script.remove();pending=null;reject(new Error('地図を読み込めませんでした。時系列はそのまま確認できます。'));};
  const timer=setTimeout(fail,15000);
  window[callback]=()=>{if(!loaded()){fail();return;}clear();resolve(classes());};
  window.gm_authFailure=fail;script.onerror=fail;document.head.append(script);
 });
 return pending;
}
