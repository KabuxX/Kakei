export const HOST='https://japanese-addresses-v2.geoloniamaps.com';
export const publicLookup=async()=>[{address:'1.1.1.1',family:4}];
export function datasetFixture(){
 const csv1='# synthetic\nblk_num,rsdt_num,rsdt_num2,lng,lat\n2,3,,139.7,35.7';
 const csv2='# synthetic\nblk_num,rsdt_num,rsdt_num2,lng,lat\n2,3,,,';
 const csv3='# synthetic\nprc_num1,prc_num2,prc_num3,lng,lat\n2,3,,139.8,35.8';
 const city={code:13105,city:'文京区',point:[139.75,35.75]};
 const pref={code:13,pref:'東京都',point:[139.7,35.7],cities:[city]};
 const towns=[{machiaza_id:'1',oaza_cho:'本郷',chome:'一丁目',chome_n:1,rsdt:true,point:[139.6,35.6],csv_ranges:{住居表示:{start:0,length:Buffer.byteLength(csv1)}}},
  {machiaza_id:'2',oaza_cho:'本郷',chome:'二丁目',chome_n:2,rsdt:true,point:[139.6,35.6],csv_ranges:{住居表示:{start:1000,length:Buffer.byteLength(csv2)}}},
  {machiaza_id:'3',oaza_cho:'湯島',point:[139.6,35.6],csv_ranges:{地番:{start:0,length:Buffer.byteLength(csv3)}}}];
 const calls=[];
 const fetchImpl=async(url,opts)=>{
  calls.push({url:String(url),...opts});const decoded=decodeURI(String(url));
  if(decoded.endsWith('/ja.json'))return new Response(JSON.stringify({meta:{updated:1234},data:[pref]}));
  if(decoded.includes('文京区.json'))return new Response(JSON.stringify({meta:{updated:1234},data:towns}));
  const offset=Number(opts.headers.Range.match(/bytes=(\d+)/)[1]);
  const csv=decoded.includes('地番')?csv3:offset===0?csv1:csv2;
  return new Response(csv,{status:206,headers:{'Content-Range':`bytes ${offset}-${offset+Buffer.byteLength(csv)-1}/10000`}});
 };
 return {fetchImpl,calls};
}
