import https from 'node:https';
import {lookup as dnsLookup} from 'node:dns/promises';
import {BlockList,isIP} from 'node:net';
import {createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

const HOST='japanese-addresses-v2.geoloniamaps.com';
const MAX_BODY=8*1024*1024,MAX_TOTAL=32*1024*1024;
const blocked=new BlockList(),global6=new BlockList();
for(const [base,bits] of [['0.0.0.0',8],['10.0.0.0',8],['100.64.0.0',10],['127.0.0.0',8],['169.254.0.0',16],['172.16.0.0',12],['192.0.0.0',24],['192.0.2.0',24],['192.88.99.0',24],['192.168.0.0',16],['198.18.0.0',15],['198.51.100.0',24],['203.0.113.0',24],['224.0.0.0',4],['240.0.0.0',4]])blocked.addSubnet(base,bits,'ipv4');
global6.addSubnet('2000::',3,'ipv6');
for(const [base,bits] of [['2001::',32],['2001:db8::',32],['2001:10::',28],['2001:20::',28],['2002::',16]])blocked.addSubnet(base,bits,'ipv6');
export function failure(code){return Object.assign(new Error(code),{code});}
function publicAddress(address){const family=isIP(address);return family===4?!blocked.check(address,'ipv4'):family===6&&global6.check(address,'ipv6')&&!blocked.check(address,'ipv6');}
function target(value){
 let u;try{u=new URL(value);}catch{throw failure('geolonia_unsafe_url');}
 if(u.protocol!=='https:'||u.hostname!==HOST||u.port||u.username||u.password||u.hash||!/^\/api\/ja(?:\.json|\/)/.test(u.pathname)||(u.search&&!/^\?v=\d+$/.test(u.search)))throw failure('geolonia_unsafe_url');
 return u;
}
function nativeFetch(url,{headers,signal,pinned}){
 return new Promise((resolve,reject)=>{
  const req=https.get(url,{headers,signal,lookup:(_host,options,callback)=>options.all?callback(null,[pinned]):callback(null,pinned.address,pinned.family)},res=>{
   resolve({status:res.statusCode,headers:{get:key=>res.headers[key.toLowerCase()]??null},body:res});
  });req.on('error',reject);
 });
}
function cancelBody(response){response.body?.cancel?.().catch(()=>{});response.body?.destroy?.();}

export function createDatasetFetcher({fetchImpl=nativeFetch,lookup=host=>dnsLookup(host,{all:true,verbatim:true}),clock=()=>Date.now()/1000,signal,sleep=ms=>delay(ms,undefined,{signal})}={}){
 const records=new Map(),failures=new Map();let bytesRead=0,remaining=MAX_TOTAL,currentSignal=signal;
 async function request(input,options={}){
  const u=target(input);const span=options.offset===undefined&&options.length===undefined?null:{offset:options.offset,length:options.length};
  if(span&&(!Number.isSafeInteger(span.offset)||span.offset<0||!Number.isSafeInteger(span.length)||span.length<1||span.length>MAX_BODY))throw failure('geolonia_invalid_range');
  const key=u.href+JSON.stringify(span);
  if(failures.has(key))throw failure(failures.get(key));
  for(let attempt=0;attempt<3;attempt++){
   try{
    currentSignal?.throwIfAborted();
    const ips=await lookup(HOST);
    if(!Array.isArray(ips)||!ips.length||ips.some(ip=>!publicAddress(ip.address)))throw failure('geolonia_unsafe_address');
    const headers={'User-Agent':'Kakei-Geolonia/1.0','Accept-Encoding':'identity'};
    if(span)headers.Range=`bytes=${span.offset}-${span.offset+span.length-1}`;
    const response=await fetchImpl(u.href,{headers,signal:currentSignal,redirect:'error',pinned:ips[0]});
    if(response.status>=300&&response.status<400){cancelBody(response);throw failure('geolonia_unsafe_url');}
    if([408,425,429].includes(response.status)||response.status>=500){cancelBody(response);throw failure('geolonia_network');}
    if(response.status!==(span?206:200)){cancelBody(response);throw failure(span?'geolonia_invalid_range':'geolonia_network_permanent');}
    if(span){
     const match=/^bytes (\d+)-(\d+)\/(\d+|\*)$/.exec(response.headers.get('content-range')||'');
     if(!match||Number(match[1])!==span.offset||Number(match[2])!==span.offset+span.length-1||(match[3]!=='*'&&Number(match[3])<=Number(match[2]))){cancelBody(response);throw failure('geolonia_invalid_range');}
    }
    if(!['','identity'].includes(response.headers.get('content-encoding')||'')){cancelBody(response);throw failure('geolonia_unsupported_content');}
    const contentLength=Number(response.headers.get('content-length')||0);
    if(contentLength>MAX_BODY||contentLength>remaining){cancelBody(response);throw failure('geolonia_size_limit');}
    const chunks=[];let size=0;
    for await(const chunk of response.body){
     const buffer=Buffer.from(chunk);size+=buffer.length;bytesRead+=buffer.length;remaining-=buffer.length;
     if(size>MAX_BODY||remaining<0){cancelBody(response);throw failure('geolonia_size_limit');}chunks.push(buffer);
    }
    if(span&&size!==span.length)throw failure('geolonia_invalid_range');
    const body=Buffer.concat(chunks).toString('utf8');
    const isJson=u.pathname.endsWith('.json');let data;
    if(isJson){try{data=JSON.parse(body);}catch{throw failure('geolonia_network');}}
    const proof={sourceId:'g'+(records.size+1),url:u.href,retrievedAt:clock(),range:span,sha256:createHash('sha256').update(Buffer.concat(chunks)).digest('hex'),updatedAt:isJson&&Number.isFinite(data?.meta?.updated)?data.meta.updated:null};
    records.set(key,{proof,data});
    return {ok:true,status:response.status,json:async()=>data,text:async()=>body};
   }catch(error){
    if(currentSignal?.aborted)throw failure('geolonia_timeout');
    const code=error.code?.startsWith?.('geolonia_')?error.code:'geolonia_network';
    if(code!=='geolonia_network'||attempt===2){failures.set(key,code);throw failure(code);}
    await sleep(100*2**attempt);
   }
  }
 }
 return {request,proofFor:predicate=>[...records.values()].filter(predicate).map(r=>structuredClone(r.proof)),
  configure:({signal,bytesRemaining})=>{currentSignal=signal;remaining=Math.min(remaining,bytesRemaining);},
  get bytesRead(){return bytesRead;},close(){}};
}
