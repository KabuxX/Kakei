// @vitest-environment node
import {afterEach, describe, expect, it} from 'vitest';
import {mkdtempSync, mkdirSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {createDemoCheckServer} from '../../scripts/serve-demo-check.mjs';
import {validateDemoSource, validateDemoBuild, validateNormalBuild} from '../../scripts/validate-demo.mjs';
const roots=[];
const hash=text=>createHash('sha256').update(text).digest('hex');
function fixture(){
 const root=mkdtempSync(join(tmpdir(),'kakei-build-')); roots.push(root);
 const put=(path,value)=>{mkdirSync(join(root,path,'..'),{recursive:true});writeFileSync(join(root,path),typeof value==='string'?value:JSON.stringify(value));};
 const snapshot={schemaVersion:1,exportedAt:'2026-10-04',transactions:[{id:'transaction-demo',date:'2026-10-02'}],categories:{'食費':1,'住まい':1,'日用品':1,'交通':1,'娯楽':1,'その他':1},timeline:{days:[],places:{}},threads:[{id:'thread-demo',messages:[]}],placeLookup:{},receipts:{'receipt-demo':{id:'receipt-demo',threadId:'thread-demo',path:'demo-data/receipts/receipt-demo.png',sha256:hash('receipt')}}};
 put('demo/data/snapshot.json',snapshot);
 put('demo/data/manifest.json',{schemaVersion:1,exportedAt:snapshot.exportedAt,latestMonth:'2026-10',counts:{transactions:1,days:0,events:0,places:0,threads:1,messages:0,receipts:1,categories:6},snapshotSha256:hash(JSON.stringify(snapshot)),receiptHashes:{'receipt-demo':hash('receipt')}});
 put('demo/maps/manifest.json',{sha256:hash('tiles'),bytes:5,bounds:[138.9,35.45,139.95,35.95],tileMinZoom:0,tileMaxZoom:14,displayMaxZoom:16,resources:[{path:'fonts/font.ttf',bytes:4,sha256:hash('font')}]});
 for(const dir of ['demo/public','dist-demo']){put(`${dir}/demo-data/receipts/receipt-demo.png`,'receipt');put(`${dir}/maps/tokyo.pmtiles`,'tiles');put(`${dir}/maps/fonts/font.ttf`,'font');}
 put('dist-demo/index.html','<script type="module" src="/Kakei/assets/main.js"></script>');
 put('dist-demo/assets/main.js','import("./map.js"); const receipt="receipt-demo";');
 put('dist-demo/assets/map.js','export const map=true;');
 put('dist/index.html','<script src="/assets/main.js"></script>');put('dist/assets/main.js','normal');
 return {root,put};
}
afterEach(()=>roots.splice(0).forEach(root=>rmSync(root,{recursive:true,force:true})));
describe('demo publication validation',()=>{
 it('accepts valid source, /Kakei/ build, lazy chunks and isolated normal output',()=>{const {root}=fixture();expect(()=>validateDemoSource(root)).not.toThrow();expect(()=>validateDemoBuild(root)).not.toThrow();expect(()=>validateNormalBuild(root)).not.toThrow();});
 it.each(['demo/public','dist-demo'])('rejects missing receipt in %s',dir=>{const {root}=fixture();rmSync(join(root,dir,'demo-data/receipts/receipt-demo.png'));expect(()=>dir==='dist-demo'?validateDemoBuild(root):validateDemoSource(root)).toThrow(/receipt/);});
 it('rejects root absolute asset',()=>{const {root,put}=fixture();put('dist-demo/index.html','<script src="/assets/main.js"></script>');expect(()=>validateDemoBuild(root)).toThrow(/base/);});
 it('rejects external executable assets',()=>{const {root,put}=fixture();put('dist-demo/index.html','<script src="/Kakei/assets/main.js"></script><script src="https://example.org/script"></script>');expect(()=>validateDemoBuild(root)).toThrow(/External asset/);});
 it('rejects missing lazy chunk',()=>{const {root}=fixture();rmSync(join(root,'dist-demo/assets/map.js'));expect(()=>validateDemoBuild(root)).toThrow(/map.js/);});
 it.each(['import{x}from"./missing-static.js";console.log(x);','import"./missing-static.js";'])('rejects missing static chunks: %s',code=>{const {root,put}=fixture();put('dist-demo/assets/main.js',code);expect(()=>validateDemoBuild(root)).toThrow(/missing-static.js/);});
 it.each(['import{x}from"https://example.org/chunk.js";console.log(x);','import"https://example.org/chunk.js";'])('rejects external static imports: %s',code=>{const {root,put}=fixture();put('dist-demo/assets/main.js',code);expect(()=>validateDemoBuild(root)).toThrow(/External asset/);});
 it.each(['import{x}from"./map.js";console.log(x);','import"./map.js";'])('accepts existing static chunks: %s',code=>{const {root,put}=fixture();put('dist-demo/assets/main.js',code);expect(()=>validateDemoBuild(root)).not.toThrow();});
 it('rejects corrupted map and font hashes',()=>{const {root,put}=fixture();put('dist-demo/maps/tokyo.pmtiles','bad');expect(()=>validateDemoBuild(root)).toThrow(/hash|bytes/);put('dist-demo/maps/tokyo.pmtiles','tiles');put('dist-demo/maps/fonts/font.ttf','fake');expect(()=>validateDemoBuild(root)).toThrow(/hash/);});
 it.each(['.env','private.sqlite','key.pem'])('rejects private file %s',file=>{const {root,put}=fixture();put(`dist-demo/${file}`,'private');expect(()=>validateDemoBuild(root)).toThrow(/private/i);});
 it('rejects authentication keys and internal snapshot fields',()=>{const {root,put}=fixture();put('dist-demo/assets/main.js','const key="sk-proj-abcdefghijklmnopqrstuvwxyz"');expect(()=>validateDemoBuild(root)).toThrow(/secret/i);put('demo/data/snapshot.json',{processingLease:'internal'});expect(()=>validateDemoSource(root)).toThrow(/private/i);});
 it('rejects demo originals and identifiers in normal output',()=>{const {root,put}=fixture();put('dist/assets/main.js','receipt-demo');expect(()=>validateNormalBuild(root)).toThrow(/DEMO/);});
 it('does not mistake inert dependency URL strings for requests',()=>{const {root,put}=fixture();put('dist-demo/assets/map.js','const documentation="https://example.org/library-docs";');expect(()=>validateDemoBuild(root)).not.toThrow();});
});

describe('static demo check server',()=>{
 it.each([true,false])('enforces local CSP and API rejection with Range %s',async ranges=>{
  const {root}=fixture(), logs=[];
  const server=createDemoCheckServer({root:join(root,'dist-demo'),ranges,log:value=>logs.push(JSON.parse(value))});
  await new Promise((ok,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',ok);});
  try{
   const base=`http://127.0.0.1:${server.address().port}`;
   const response=await fetch(`${base}/Kakei/maps/tokyo.pmtiles`,{headers:{Range:'bytes=1-2'}});
   expect(response.status).toBe(ranges?206:200);
   expect(await response.text()).toBe(ranges?'il':'tiles');
   expect(response.headers.get('content-range')).toBe(ranges?'bytes 1-2/5':null);
   expect(response.headers.get('content-security-policy')).toContain("connect-src 'self'");
   expect(response.headers.get('content-security-policy')).toContain("worker-src 'self' blob:");
   expect((await fetch(`${base}/Kakei/api/transactions`)).status).toBe(502);
   expect((await fetch(`${base}/api/transactions`)).status).toBe(502);
   expect((await fetch(`${base}/Kakei/missing`)).status).toBe(404);
   expect(logs.filter(entry=>entry.api)).toHaveLength(2);
   expect(logs[0].range).toBe('bytes=1-2');
  }finally{server.closeAllConnections();await new Promise(ok=>server.close(ok));}
 });
});
