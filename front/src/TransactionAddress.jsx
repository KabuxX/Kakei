import React, {useEffect,useRef,useState} from 'react';
import {getTransactionAddress} from './lib/api.js';
import {normalizeMerchantAddress} from './lib/transaction-data.js';
import MerchantAddressField from './MerchantAddressField.jsx';
function mapHref(coordinates) {
  if (!Array.isArray(coordinates) || coordinates.length !== 2) return null;
  const [longitude,latitude]=coordinates;
  if (!Number.isFinite(longitude)||!Number.isFinite(latitude)||Math.abs(longitude)>180||Math.abs(latitude)>90) return null;
  return `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=18/${latitude}/${longitude}`;
}
export default function TransactionAddress({record,busy=false,onSave,onReviewAddress}) {
  const [places,setPlaces]=useState([]),[failed,setFailed]=useState(false),[attempt,setAttempt]=useState(0);
  const [editing,setEditing]=useState(false),[value,setValue]=useState(''),[error,setError]=useState(''),[saving,setSaving]=useState(false);
  const pending=useRef(false), expected=useRef(null);
  useEffect(()=>{
    let active=true;setPlaces([]);setFailed(false);
    getTransactionAddress(record.id).then(context=>{if(active)setPlaces(context.places);}).catch(()=>{if(active)setFailed(true);});
    return ()=>{active=false;};
  },[record.id,record.merchantAddress,attempt]);
  const begin=(address=record.merchantAddress || '')=>{
    expected.current={merchant:record.merchant ?? null,merchantAddress:record.merchantAddress ?? null};
    setValue(address);setError('');setEditing(true);
  };
  const save=async()=>{
    if(pending.current||busy)return;
    try {
      const address=normalizeMerchantAddress(value);pending.current=true;setSaving(true);setError('');
      const refreshed=await onSave(address,expected.current);
      if(refreshed===false) {setError('保存は完了しました。表示を再読み込みしてください。');return;}
      setEditing(false);setAttempt(n=>n+1);
    } catch(cause){setError(cause.message);} finally{pending.current=false;setSaving(false);}
  };
  const needsReview=places.some(p=>p.status==='needs_review');
  return <><dt className="detail-address-label">{record.merchantAddress?'住所':'軌跡に保存された住所'}</dt><dd className="detail-address">
    {record.merchantAddress && <p>{record.merchantAddress}</p>}
    {needsReview && <p role="status">住所が変わったため、位置の再確認が必要です</p>}
    {needsReview && onReviewAddress && <button className="secondary-button" onClick={()=>onReviewAddress({transactionId:record.id,date:record.date.slice(0,10)})}>Agentで位置を再確認</button>}
    {failed && <div role="alert"><p>住所を読み込めませんでした。</p><button className="secondary-button" onClick={()=>setAttempt(n=>n+1)}>住所を再読み込み</button></div>}
    {places.filter(p=>p.address).map(place=><div key={place.placeId} className="detail-address-place">
      {(!record.merchantAddress || place.status==='needs_review') && <>{record.merchantAddress && <small>軌跡に保存された住所</small>}<p>{place.address}</p></>}
      {place.status!=='needs_review' && mapHref(place.coordinates) && <a className="detail-map-link" href={mapHref(place.coordinates)} target="_blank" rel="noopener noreferrer">地図で見る<span className="sr-only">（新しいタブで開く）</span></a>}
      {!record.merchantAddress && onSave && <button className="secondary-button" disabled={busy||saving} onClick={()=>begin(place.address)}>この住所を取引に保存</button>}
    </div>)}
    {onSave && (editing?<div className="address-editor"><MerchantAddressField id="detail-address-input" value={value} onChange={setValue} error={error} disabled={busy||saving}/><p className="form-note">空欄で保存すると取引の住所を消去します。軌跡の記録は残ります。</p><div className="address-actions"><button className="secondary-button" disabled={saving} onClick={()=>setEditing(false)}>キャンセル</button><button className="primary-button" disabled={busy||saving} onClick={save}>住所を保存</button></div></div>:<button className="secondary-button" disabled={busy} onClick={()=>begin()}>{record.merchantAddress?'住所を編集':'住所を追加'}</button>)}
  </dd></>;
}
