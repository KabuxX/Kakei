import {useEffect,useRef,useState} from 'react';
import * as api from '../../lib/agent-api.js';
export const normalizeLocationInput=value=>({merchant:(value?.merchant||'').trim(),branch:value?.branch?.trim()||null,locality:value?.locality?.trim()||null,merchantAddress:value?.merchantAddress?.trim()||null});
const fingerprint=value=>JSON.stringify(normalizeLocationInput(value));
export default function useReceiptLocation({threadId,receiptId,initialResolution,input,target,readOnly=false}){
 const targetId=typeof target==='object'?target?.id:target;
 const owner=`${threadId}:${receiptId}`;
 const [state,setState]=useState({owner,resolution:initialResolution||null,pending:false,error:null});
 const current=useRef(null),request=useRef(null);
 const key=`${owner}:${targetId}:${fingerprint(input)}`;
 current.current={key,owner,input:normalizeLocationInput(input),target:targetId,targetRecord:typeof target==='object'?target:null};
 const resolution=state.owner===owner?state.resolution:initialResolution||null;
 const matches=resolution?.receiptId===receiptId&&fingerprint(resolution.input)===fingerprint(input)&&(!resolution.sourceTransactionId||resolution.sourceTransactionId===targetId);
 const resolved=!!(matches&&resolution.status==='resolved'&&resolution.expiresAt>Date.now()/1000&&!state.pending);
 useEffect(()=>{request.current?.controller.abort();request.current=null;setState(old=>({...old,pending:false,error:null}));return()=>{request.current?.controller.abort();request.current=null;};},[key]);
 useEffect(()=>{setState({owner,resolution:initialResolution||null,pending:false,error:null});},[owner,initialResolution]);
 const run=async(operation)=>{
  if(readOnly||request.current)return;
  const captured=current.current,controller=new AbortController(),token={controller,key:captured.key};request.current=token;
  setState(old=>({...old,pending:true,error:null}));
  try{
   const value=await operation(controller.signal,captured);
   if(request.current===token&&current.current.key===captured.key&&!controller.signal.aborted&&(!value||value.receiptId===receiptId)&&(!value||value.revision>=(resolution?.revision??0))){setState({owner,resolution:value,pending:false,error:null});return value;}
  }catch(error){if(request.current===token&&!controller.signal.aborted)setState(old=>({...old,pending:false,error}));}
  finally{if(request.current===token){request.current=null;setState(old=>({...old,pending:false}));}}
 };
 const payload=captured=>({revision:resolution?.revision??0,input:captured.input});
 const reload=()=>run(signal=>api.getReceiptLocation(threadId,receiptId,signal));
 useEffect(()=>{if(!readOnly&&!initialResolution)reload();},[owner,readOnly]);
 return {resolution,pending:state.pending,error:state.error,resolved,search:inherit=>run((signal,c)=>api.searchReceiptLocation(threadId,receiptId,{...payload(c),...(inherit===true&&c.targetRecord?.merchantPlace?{sourceTransactionId:c.target}:{} )},signal)),select:placeId=>matches&&run(signal=>api.selectReceiptLocation(threadId,receiptId,{resolutionId:resolution.id,revision:resolution.revision,placeId},signal)),confirmAddress:()=>run((signal,c)=>api.confirmReceiptAddress(threadId,receiptId,{...payload(c),...(c.targetRecord?.merchantAddress===c.input.merchantAddress?{sourceTransactionId:c.target}:{})},signal)),reload};
}
