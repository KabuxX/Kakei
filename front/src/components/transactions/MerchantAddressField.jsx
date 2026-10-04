import React from 'react';
export default function MerchantAddressField({id,value,onChange,error='',disabled=false}) {
  return <div className="merchant-address-field"><label htmlFor={id}>住所（任意）</label>
    <textarea id={id} rows={3} value={value ?? ''} onChange={event=>onChange(event.target.value)} disabled={disabled} aria-invalid={!!error || undefined} aria-describedby={`${id}-hint ${id}-error`}/>
    <small id={`${id}-hint`}>郵便番号・番地・建物名など、500文字以内</small>
    <small id={`${id}-error`} className="field-error" hidden={!error}>{error}</small>
  </div>;
}
