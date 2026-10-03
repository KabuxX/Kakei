import React, {useEffect,useRef} from 'react';
import {Icon} from './AppShell.jsx';
import TransactionForm from './TransactionForm.jsx';
export default function TransactionDialog({open,busy,onClose,onSubmit}) {
 const dialog=useRef(null);
 useEffect(()=>{
  const element=dialog.current;
  if(open && !element.open) {
   if(element.showModal)element.showModal();else element.setAttribute('open','');
   element.querySelector('[name="title"]')?.focus();
  }else if(!open && element.open){if(element.close)element.close();else element.removeAttribute('open');}
 },[open]);
 const close=()=>{if(!busy && !dialog.current?.querySelector('button[type="submit"]')?.disabled)onClose();};
 return <dialog ref={dialog} id="transaction-dialog" className="transaction-dialog" aria-labelledby="dialog-title" onClick={e=>{if(e.target===e.currentTarget)close();}} onCancel={e=>{e.preventDefault();close();}}>
  <div className="dialog-head"><h2 id="dialog-title">取引を追加</h2><button type="button" className="icon-button close-dialog" aria-label="閉じる" onClick={close} disabled={busy}><Icon name="close"/></button></div>
  {open && <TransactionForm busy={busy} onCancel={onClose} onSubmit={onSubmit} onSaved={onClose}/>}
 </dialog>;
}
