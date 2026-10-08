import React,{useEffect,useId,useRef} from 'react';
import {normalizeLocationInput} from './useReceiptLocation.js';
import GooglePlaceResults from '../places/GooglePlaceResults.jsx';
const messages={needs_input:'店舗名・支店名・地域を補って検索するか、原本やご自身で確認した住所を入力してください。',needs_selection:'候補を確認し、このレシートの店舗を選んでください。',not_found:'店舗が見つかりませんでした。支店名・地域を補って再検索してください。',unavailable:'店舗を確認できませんでした。再検索するか、本人確認済みの住所を入力してください。',searching:'店舗を検索しています…',resolved:'店舗・住所を確認しました。'};
export default function ReceiptLocation({location,input,onInputChange,inheritedPlace,readOnly=false}){
 const id=useId(),summary=useRef(null);
 const {resolution,pending,error,resolved,search,select,confirmAddress,reload}=location;
 useEffect(()=>{if(error)summary.current?.focus();},[error]);
 if(readOnly)return <section className="receipt-location" aria-label="店舗・住所"><h3>店舗・住所</h3><p>{input.merchant}</p><p>{input.merchantAddress||'保存済みの店舗参照を使用しています。'}</p></section>;
 const currentCandidates=JSON.stringify(normalizeLocationInput(resolution?.input))===JSON.stringify(normalizeLocationInput(input));
 const field=error?.field?.split('.').at(-1);
 return <section className="receipt-location" aria-label="店舗・住所"><h3>店舗・住所</h3>
 {error&&<div role="alert" tabIndex="-1" ref={summary} className="agent-error"><p>{error.message||'店舗を確認できませんでした。'}</p>{['merchant','branch','locality','merchantAddress'].includes(field)&&<a href={`#${id}-${field}`}>入力欄を確認</a>}<button type="button" className="secondary-button" disabled={pending} onClick={reload}>確認状態を再読み込み</button></div>}
 <div className="agent-fields">{[['merchant','店舗名',200],['branch','支店名',200],['locality','地域',200],['merchantAddress','原本・本人確認済みの住所',500]].map(([key,label,max])=><React.Fragment key={key}><label htmlFor={`${id}-${key}`}>{label}<input id={`${id}-${key}`} value={input[key]||''} maxLength={max} onChange={e=>onInputChange({...input,[key]:e.target.value||null})} aria-invalid={field===key} aria-describedby={field===key?`${id}-${key}-error`:key==='merchantAddress'?`${id}-address-help`:undefined}/></label>{field===key&&<span id={`${id}-${key}-error`}>{error.message}</span>}</React.Fragment>)}</div>
 <p id={`${id}-address-help`}>住所欄には原本やご自身で確認した住所を入力してください。検索候補の住所は店舗参照として使用します。</p>
 <p role="status" aria-live="polite">{pending?'店舗を確認しています…':resolved?messages.resolved:messages[resolution?.status==='resolved'?'needs_input':resolution?.status]||messages.needs_input}</p>
 <div className="agent-actions">{inheritedPlace&&<button type="button" className="secondary-button" disabled={pending} onClick={async()=>{const next=await search(true);if(next)onInputChange({...input,merchantAddress:next.input.merchantAddress});}}>保存先の店舗参照を確認</button>}<button type="button" className="secondary-button" disabled={pending||!input.merchant?.trim()} onClick={()=>search()}>店舗を再検索</button><button type="button" className="secondary-button" disabled={pending||!input.merchant?.trim()||!input.merchantAddress?.trim()} onClick={confirmAddress}>この住所を確認した</button></div>
 {currentCandidates&&!!resolution?.placeIds?.length&&<GooglePlaceResults placeIds={resolution.placeIds} selectedPlaceId={resolved?resolution.selectedPlaceId:null} disabled={pending||resolution.status!=='needs_selection'} onSelect={select} onRetry={reload}/>}
 {!resolved&&<p className="agent-notice">店舗・住所の確認が完了すると、変更案を確認できます。</p>}
 </section>;
}
