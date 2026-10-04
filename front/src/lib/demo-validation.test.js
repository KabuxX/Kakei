import {expect,it} from 'vitest';
import snapshot from '../../demo/data/snapshot.json';
import {createDemoFetch} from '../../demo/api.js';
import {validateDemoSnapshot} from '../../demo/validate.js';

const thread=s=>s.threads.find(t=>t.proposals?.length);
const proposal=s=>thread(s).proposals[0];
const invalid=[
 ['thread review',s=>{thread(s).receiptReviews[0].receiptId='missing-original';},/receiptReviews\[0\].receiptId/],
 ['proposal review',s=>{proposal(s).metadata.receiptReview.receiptId='missing-original';},/metadata.receiptReview.receiptId/],
 ['proposal metadata',s=>{proposal(s).metadata.receiptId='missing-original';},/metadata.receiptId/],
 ['command attachment',s=>{proposal(s).commands[0].data.receiptIds=['missing-original'];},/commands\[0\].data.receiptIds\[0\]/],
 ['historical attachment',s=>{proposal(s).after[0].receiptIds=['missing-original'];},/after\[0\].receiptIds\[0\]/],
 ['saved result attachment',s=>{proposal(s).result.transactions[0].receiptIds=['missing-original'];},/result.transactions\[0\].receiptIds\[0\]/],
 ['current transaction attachment',s=>{s.transactions[0].receiptIds=['missing-original'];},/transactions\[0\].receiptIds\[0\]/],
 ['missing proposal thread',s=>{proposal(s).threadId='missing-thread';},/proposals\[0\].threadId/],
 ['wrong proposal thread',s=>{proposal(s).threadId=s.threads[0].id;},/proposals\[0\].threadId/],
 ['duplicate proposal lookup',s=>{s.threads[0].proposals=[structuredClone(proposal(s))];s.threads[0].proposals[0].threadId=s.threads[0].id;},/Duplicate.*proposal/i],
 ['duplicate message',s=>{s.threads[0].messages.push(structuredClone(s.threads[0].messages[0]));},/Duplicate.*message/i],
 ['duplicate review',s=>{thread(s).receiptReviews.push(structuredClone(thread(s).receiptReviews[0]));},/Duplicate.*receipt review/i],
 ['receipt table key',s=>{Object.values(s.receipts)[0].id='wrong-key';},/receipt/i],
 ['receipt containing thread',s=>{Object.values(s.receipts)[0].threadId='missing-thread';},/receipt/i],
 ['current transport',s=>{s.timeline.days.find(d=>d.legs.length).legs[0].transportTransactionId='missing-transaction';},/legs\[0\].transportTransactionId/],
];
it.each(invalid)('rejects broken display graph: %s',(_,mutate,path)=>{
 const s=structuredClone(snapshot);mutate(s);
 expect(()=>validateDemoSnapshot(s)).toThrow(path);
 expect(()=>createDemoFetch(s)).toThrow(path);
});
it.each(['pending','expired','applied'])('retains %s history with originals and deleted historical transaction targets',status=>{
 const s=structuredClone(snapshot),p=proposal(s);p.status=status;p.expiresAt=1;
 p.commands[0].identity={id:'deleted-historical-transaction'};
 p.before=[{id:'deleted-historical-transaction',receiptIds:[p.metadata.receiptId]}];p.after[0].id='deleted-historical-transaction';
 p.result={transactions:[{id:'deleted-historical-transaction'}]};
 expect(()=>validateDemoSnapshot(s)).not.toThrow();expect(()=>createDemoFetch(s)).not.toThrow();
});
