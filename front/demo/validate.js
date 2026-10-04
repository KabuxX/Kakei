import {isValidBudget} from '../src/lib/budget.js';
import {buildTrajectoryDays} from '../src/lib/trajectory-model.js';
export function validateDemoSnapshot(s,manifest){
 if(s?.schemaVersion!==1||!Array.isArray(s.transactions)||!isValidBudget(s.categories)||!Array.isArray(s.threads)||!s.receipts||!s.placeLookup)throw new Error('Invalid DEMO snapshot');
 const tx=new Set(s.transactions.map(t=>t.id));if(tx.size!==s.transactions.length)throw new Error('Duplicate transaction');
 const threads=new Set(s.threads.map(t=>t.id));if(threads.size!==s.threads.length)throw new Error('Duplicate thread');
 for(const d of s.timeline.days)for(const e of d.events)if(!e.id||!s.timeline.places[e.placeId]||(e.transactionId&&!tx.has(e.transactionId)))throw new Error('Missing event reference');
 buildTrajectoryDays(s.transactions,s.timeline);
 for(const [id,r] of Object.entries(s.receipts))if(id!==r.id||!/^demo-data\/receipts\/[A-Za-z0-9_-]+\.(png|jpg|pdf|webp)$/.test(r.path)||!threads.has(r.threadId)||(r.transactionId&&!tx.has(r.transactionId)))throw new Error('Invalid receipt reference');
 if(manifest && (manifest.schemaVersion!==1||manifest.exportedAt!==s.exportedAt||manifest.counts.transactions!==s.transactions.length||manifest.counts.days!==s.timeline.days.length||manifest.counts.receipts!==Object.keys(s.receipts).length))throw new Error('Invalid DEMO manifest');
}
