import {isValidBudget} from '../src/lib/budget.js';
import {buildTrajectoryDays} from '../src/lib/trajectory-model.js';
function uniqueIds(records,path,label,key='id',seen=new Set()){
 for(const [index,record] of records.entries()){
  const id=record[key];
  if(typeof id!=='string'||!id||seen.has(id))throw new Error(`Duplicate or missing ${label}: ${path}[${index}].${key}`);
  seen.add(id);
 }
 return seen;
}
// These are original-asset references throughout the public display DTO,
// including retained before/after/results. Historical transaction IDs are
// content, not links requiring a currently present transaction.
function receiptReferences(value,path,receipts){
 if(!value||typeof value!=='object')return;
 if(Array.isArray(value)){value.forEach((item,index)=>receiptReferences(item,`${path}[${index}]`,receipts));return;}
 for(const [key,item] of Object.entries(value)){
  const location=`${path}.${key}`;
  if(key==='receiptId'){
   if(typeof item!=='string'||!Object.hasOwn(receipts,item))throw new Error(`Missing original reference: ${location}`);
  }else if(key==='receiptIds'){
   if(!Array.isArray(item))throw new Error(`Invalid original references: ${location}`);
   item.forEach((id,index)=>{if(typeof id!=='string'||!Object.hasOwn(receipts,id))throw new Error(`Missing original reference: ${location}[${index}]`);});
  }else receiptReferences(item,location,receipts);
 }
}
export function validateDemoSnapshot(s,manifest){
 if(s?.schemaVersion!==1||!Array.isArray(s.transactions)||!isValidBudget(s.categories)||!Array.isArray(s.threads)||!s.receipts||!s.placeLookup)throw new Error('Invalid DEMO snapshot');
 const tx=uniqueIds(s.transactions,'transactions','transaction');
 const threads=uniqueIds(s.threads,'threads','thread');
 const proposals=new Set(),messages=new Set();
 s.threads.forEach((thread,index)=>{
  const path=`threads[${index}]`;
  uniqueIds(thread.messages??[],`${path}.messages`,'message','id',messages);
  uniqueIds(thread.proposals??[],`${path}.proposals`,'proposal','id',proposals);
  uniqueIds(thread.receiptReviews??[],`${path}.receiptReviews`,'receipt review','receiptId');
  (thread.proposals??[]).forEach((proposal,index)=>{if(proposal.threadId!==thread.id)throw new Error(`Invalid containing thread: ${path}.proposals[${index}].threadId`);});
 });
 for(const [index,d] of s.timeline.days.entries()){
  for(const e of d.events)if(!e.id||!s.timeline.places[e.placeId]||(e.transactionId&&!tx.has(e.transactionId)))throw new Error('Missing event reference');
  for(const [legIndex,leg] of d.legs.entries()){
   if(leg.transportTransactionId&&!tx.has(leg.transportTransactionId))throw new Error(`Missing current transport reference: timeline.days[${index}].legs[${legIndex}].transportTransactionId`);
   if((leg.viaPlaceIds??[]).some(id=>!s.timeline.places[id]))throw new Error(`Missing current place reference: timeline.days[${index}].legs[${legIndex}].viaPlaceIds`);
  }
 }
 buildTrajectoryDays(s.transactions,s.timeline);
 for(const [id,r] of Object.entries(s.receipts)){
  if(id!==r.id||!/^demo-data\/receipts\/[A-Za-z0-9_-]+\.(png|jpg|pdf|webp|heic)$/.test(r.path)||!threads.has(r.threadId)||(r.transactionId&&!tx.has(r.transactionId)))throw new Error('Invalid receipt reference');
  if(r.previewPath!==undefined&&(!/^demo-data\/receipts\/[A-Za-z0-9_-]+\.jpg$/.test(r.previewPath)||!/^[a-f0-9]{64}$/.test(r.previewSha256??'')))throw new Error('Invalid receipt preview reference');
 }
 receiptReferences(s.transactions,'transactions',s.receipts);
 receiptReferences(s.threads,'threads',s.receipts);
 if(manifest && (manifest.schemaVersion!==1||manifest.exportedAt!==s.exportedAt||manifest.counts.transactions!==s.transactions.length||manifest.counts.days!==s.timeline.days.length||manifest.counts.receipts!==Object.keys(s.receipts).length))throw new Error('Invalid DEMO manifest');
}
