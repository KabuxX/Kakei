import {normalize,requestHandlers,config,version} from '@geolonia/normalize-japanese-addresses';
import {failure} from './fetch.mjs';

export function createNormalizer({fetcher}){
 config.japaneseAddressesApi='https://japanese-addresses-v2.geoloniamaps.com/api/ja';
 requestHandlers.http=fetcher.request;
 return {async normalize(address){
  const result=await normalize(address);
  const {pref='',city='',town='',addr='',other='',level,point=null,metadata}=result;
  const raw=metadata?.rsdt||metadata?.chiban;
  const record=raw?{kind:metadata.rsdt?'rsdt':'chiban',fields:Object.fromEntries(Object.entries(raw).filter(([,v])=>v!==undefined&&v!==''))}:null;
  const match={pref,city,town,addr,other,level,point,record};
  const chosen=metadata?.machiAza?.machiaza_id;
  const kind=record?.kind==='rsdt'?'住居表示':'地番';
  const cityPath=`/api/ja/${pref}/${city}`;
  let range=null;
  const fetches=fetcher.proofFor(({proof,data})=>{
   const path=decodeURI(new URL(proof.url).pathname);
   if(path==='/api/ja.json')return true;
   if(path===cityPath+'.json'){
    const row=data?.data?.find(r=>r.machiaza_id===chosen)?.csv_ranges?.[kind];
    if(row)range={offset:row.start,length:row.length};
    return true;
   }
   return record&&path===cityPath+'-'+kind+'.txt';
  });
  // Tie CSV provenance to the range for this exact town, including cache hits.
  const selected=fetches.filter(p=>!p.range||range&&p.range.offset===range.offset&&p.range.length===range.length);
  const csv=selected.find(p=>p.range);
  if(point?.level===8&&(!csv||!record))throw failure('geolonia_missing_proof');
  const observation=point?.level===8?{sourceId:csv.sourceId,kind:'geolonia_address',excerpt:JSON.stringify({components:{pref,city,town,addr},record}),coordinates:[point.lng,point.lat]}:null;
  return {match,proof:{fetches:selected,observation},libraryVersion:version};
 }};
}
