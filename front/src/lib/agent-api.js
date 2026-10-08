import {apiFetch} from '@kakei/runtime';
import { request } from './api.js';
const base='/api/agent';
const id=encodeURIComponent;
export const status=()=>request('GET',`${base}/status`);
export const listThreads=async()=>(await request('GET',`${base}/threads`)).threads;
export const createThread=async()=>(await request('POST',`${base}/threads`,{})).thread;
export const getThread=async(thread)=>(await request('GET',`${base}/threads/${id(thread)}`)).thread;
export const deleteThread=(thread)=>request('DELETE',`${base}/threads/${id(thread)}`);
export const sendMessage=(thread,body)=>request('POST',`${base}/threads/${id(thread)}/messages`,body);
export const revise=async(proposal,revision,commands)=>(await request('PUT',`${base}/proposals/${id(proposal)}`,{revision,commands})).proposal;
export const approve=async(proposal,revision)=>(await request('POST',`${base}/proposals/${id(proposal)}/approve`,{revision})).result;
export const reject=async(proposal,revision)=>(await request('POST',`${base}/proposals/${id(proposal)}/reject`,{revision})).proposal;
export async function uploadReceipt(thread,file){
 const form=new FormData();form.append('file',file);
 const response=await apiFetch(`${base}/threads/${id(thread)}/receipts`,{method:'POST',body:form});
 const result=await response.json();if(!response.ok)throw new Error(result?.error?.message||'添付できませんでした。');return result;
}
export const listTransactionReceipts=async(transaction)=>(await request('GET',`/api/transactions/${id(transaction)}/receipts`)).receipts;
export const proposeReceipt=async(thread,body)=>(await request('POST',`${base}/threads/${id(thread)}/receipt-proposals`,body)).proposal;
export const selectPlaceCandidate=async(proposal,revision,candidateId,confirmed)=>(await request('POST',`${base}/proposals/${id(proposal)}/places/selection`,{revision,candidateId,...(confirmed===undefined?{}:{confirmed})})).proposal;
export const specifyPlace=async(proposal,revision,placeId,place)=>(await request('POST',`${base}/proposals/${id(proposal)}/places/manual`,{revision,placeId,place})).proposal;
export const confirmOrder=async(proposal,revision)=>(await request('POST',`${base}/proposals/${id(proposal)}/order/confirmation`,{revision})).proposal;
export const getProposal=async(proposal)=>(await request('GET',`${base}/proposals/${id(proposal)}`)).proposal;
// Location calls accept a signal separately so it never becomes request data.
const locationPath=(thread,receipt)=>`${base}/threads/${id(thread)}/receipts/${id(receipt)}/location`;
const locationRequest=async(method,path,body,signal)=>(await request(method,path,body,(url,options)=>apiFetch(url,{...options,signal}))).locationResolution;
export const getReceiptLocation=(thread,receipt,signal)=>locationRequest('GET',locationPath(thread,receipt),undefined,signal);
export const searchReceiptLocation=(thread,receipt,body,signal)=>locationRequest('POST',locationPath(thread,receipt)+'/search',body,signal);
export const selectReceiptLocation=(thread,receipt,body,signal)=>locationRequest('POST',locationPath(thread,receipt)+'/selection',body,signal);
export const confirmReceiptAddress=(thread,receipt,body,signal)=>locationRequest('POST',locationPath(thread,receipt)+'/address',body,signal);
export const reconfirmReceiptProposal=async(proposal,body)=>(await request('POST',`${base}/proposals/${id(proposal)}/receipt-location`,body)).proposal;
