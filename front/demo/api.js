import {validateDemoSnapshot} from './validate.js';
export function createDemoFetch(input){
 const s=structuredClone(input);validateDemoSnapshot(s);
 const respond=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
 const missing=()=>respond({error:{code:'not_found',message:'DEMOの記録が見つかりません。'}},404);
 const addresses=s.addresses||s.transactions.map(t=>({transactionId:t.id,places:[]}));
 return async (input,init={})=>{
  if(init.signal?.aborted)throw new DOMException('Aborted','AbortError');
  if((init.method||'GET').toUpperCase()!=='GET')return respond({error:{code:'demo_read_only',message:'DEMOは閲覧専用です。'}},403);
  let path;try{path=decodeURIComponent(new URL(input,'https://demo.invalid').pathname);}catch{return missing();}
  if(path==='/api/status')return respond({initialized:true});
  if(path==='/api/transactions')return respond({transactions:s.transactions});
  if(path==='/api/budget')return respond({categories:s.categories});
  if(path==='/api/trajectory')return respond({dates:s.timeline.days.map(d=>d.date)});
  if(path==='/api/transaction-addresses')return respond({addresses});
  if(path==='/api/agent/status')return respond({available:false,reason:'DEMOは保存済みの会話を閲覧できます。'});
  if(path==='/api/agent/threads')return respond({threads:s.threads.map(({id,title,createdAt})=>({id,title,createdAt}))});
  let match=path.match(/^\/api\/trajectory\/([^/]+)$/);
  if(match){const day=s.timeline.days.find(d=>d.date===match[1]);return day?respond({places:s.timeline.places,days:[day]}):missing();}
  match=path.match(/^\/api\/transactions\/([^/]+)(\/receipts)?$/);
  if(match){const t=s.transactions.find(t=>t.id===match[1]);return t?respond(match[2]?{receipts:Object.values(s.receipts).filter(r=>r.transactionId===t.id)}:{transaction:t}):missing();}
  match=path.match(/^\/api\/transaction-addresses\/([^/]+)$/);if(match){const address=addresses.find(a=>a.transactionId===match[1])||(s.transactions.some(t=>t.id===match[1])?{transactionId:match[1],places:[]}:null);return address?respond({address}):missing();}
  match=path.match(/^\/api\/agent\/threads\/([^/]+)$/);if(match){const thread=s.threads.find(t=>t.id===match[1]);return thread?respond({thread}):missing();}
  match=path.match(/^\/api\/agent\/proposals\/([^/]+)$/);if(match){const proposal=s.threads.flatMap(t=>t.proposals).find(p=>p.id===match[1]);return proposal?respond({proposal}):missing();}
  return missing();
 };
}
