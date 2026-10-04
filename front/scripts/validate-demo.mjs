import {readFileSync, readdirSync, lstatSync, existsSync} from 'node:fs';
import {resolve, relative, dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {validateDemoSnapshot} from '../demo/validate.js';
const frontRoot=fileURLToPath(new URL('../',import.meta.url));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const json=path=>JSON.parse(readFileSync(path,'utf8'));
const fail=message=>{throw new Error(message);};
function safePath(root,path){
 if(typeof path!=='string'||path.startsWith('/')||path.includes('\\')||path.split('/').includes('..'))fail(`Unsafe reference: ${path}`);
 return join(root,path);
}
function files(root){
 if(!existsSync(root))fail(`Missing directory: ${root}`);
 return readdirSync(root,{withFileTypes:true}).flatMap(entry=>{const path=join(root,entry.name);if(lstatSync(path).isSymbolicLink())fail(`Private/symlink artifact: ${path}`);return entry.isDirectory()?files(path):[path];});
}
const privateField=/^(?:processing_?lease|lease_?owner|lease_?expires_?at|internal_?logs?|raw|raw_?(?:google|response)|google_?raw|google_place_coordinates|coordinate_?cache|baselines|sourceVersion|authorizedPlaces|placeCandidates|searchIds|geocoding|coordinateEvidence|token|api_?key|access_?token|authorization|credentials?|password|secret)$/i;
function checkFields(value){
 if(!value||typeof value!=='object')return;
 for(const [key,item] of Object.entries(value)){if(privateField.test(key))fail(`Private snapshot field: ${key}`);checkFields(item);}
}
function scan(root){
 for(const path of files(root)){
  if(/(?:^|\/)(?:\.env(?:\..*)?|[^/]*\.(?:sqlite(?:3)?|db|pem|key)|[^/]*(?:-wal|-shm))$/i.test(path))fail(`Private artifact: ${path}`);
  if(/\.(?:js|json|html|css|txt|md|svg)$/i.test(path)){
   const text=readFileSync(path,'utf8');
   if(/(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)/.test(text))fail(`Secret in artifact: ${path}`);
   if(path.endsWith('.json'))checkFields(JSON.parse(text));
  }
 }
}
function verifyFile(path,expectedHash,expectedBytes){
 if(!existsSync(path))fail(`Missing reference: ${path}`);
 const bytes=readFileSync(path);
 if(expectedBytes!==undefined&&bytes.length!==expectedBytes)fail(`Wrong bytes: ${path}`);
 if(sha(bytes)!==expectedHash)fail(`Wrong hash: ${path}`);
}
function metadata(root){return {snapshot:json(join(root,'demo/data/snapshot.json')),manifest:json(join(root,'demo/data/manifest.json')),map:json(join(root,'demo/maps/manifest.json'))};}
function resources(root,output){
 const {snapshot,manifest,map}=metadata(root);
 checkFields(snapshot);
 if(map.tileMinZoom!==0||map.tileMaxZoom!==14||map.displayMaxZoom!==16||map.bytes>50*1024*1024||JSON.stringify(map.bounds)!=='[138.9,35.45,139.95,35.95]')fail('Invalid map bounds/zoom/size contract');
 if(!map.resources?.some(resource=>/^fonts\//.test(resource.path)))fail('Missing local font resource');
 verifyFile(join(output,'maps/tokyo.pmtiles'),map.sha256,map.bytes);
 for(const resource of map.resources??[])verifyFile(safePath(join(output,'maps'),resource.path),resource.sha256,resource.bytes);
 if(Object.keys(snapshot.receipts??{}).length!==Object.keys(manifest.receiptHashes??{}).length)fail('Receipt manifest count mismatch');
 for(const [id,receipt] of Object.entries(snapshot.receipts??{})){
  if(receipt.sha256!==manifest.receiptHashes[id])fail(`Receipt manifest hash mismatch: ${id}`);
  verifyFile(safePath(output,receipt.path),receipt.sha256);
 }
}
export function validateDemoSource(root=frontRoot){
 scan(join(root,'demo'));
 const {snapshot,manifest,map}=metadata(root);
 checkFields(snapshot);
 validateDemoSnapshot(snapshot,manifest);
 const counts={transactions:snapshot.transactions.length,days:snapshot.timeline.days.length,events:snapshot.timeline.days.reduce((n,d)=>n+d.events.length,0),places:Object.keys(snapshot.timeline.places).length,threads:snapshot.threads.length,messages:snapshot.threads.reduce((n,t)=>n+t.messages.length,0),receipts:Object.keys(snapshot.receipts).length,categories:Object.keys(snapshot.categories).length};
 if(Object.entries(counts).some(([key,value])=>manifest.counts?.[key]!==value))fail("Snapshot counts mismatch");
 for(const day of snapshot.timeline.days){
  const ids=[...day.events.map(event=>event.placeId),...(day.legs??[]).flatMap(leg=>leg.viaPlaceIds??[])];
  for(const id of ids){const coordinates=snapshot.timeline.places[id]?.coordinates;
   if(!snapshot.timeline.places[id])fail(`Missing map place reference: ${id}`);
   if(coordinates&&(coordinates[0]<map.bounds[0]||coordinates[0]>map.bounds[2]||coordinates[1]<map.bounds[1]||coordinates[1]>map.bounds[3]))fail(`Map place outside bounds: ${id}`);
  }
 }
 const latest=snapshot.transactions.map(t=>t.date.slice(0,7)).sort().at(-1);
 if(latest!==manifest.latestMonth)fail("Snapshot latest month mismatch");
 verifyFile(join(root,'demo/data/snapshot.json'),manifest.snapshotSha256);
 resources(root,join(root,'demo/public'));
 return true;
}
export function validateDemoBuild(root=frontRoot){
 validateDemoSource(root);
 const output=join(root,'dist-demo');scan(output);resources(root,output);
 const html=readFileSync(join(output,'index.html'),'utf8');
 if(!html.includes('/Kakei/assets/'))fail('Missing /Kakei/ HTML base');
 for(const path of files(output).filter(path=>/\.(?:html|js|css)$/.test(path))){
  const text=readFileSync(path,'utf8');
  // Check asset references, not inert third-party documentation strings.
  const pattern=path.endsWith('.html')
   ? /<(?:script|link|img|source|iframe)\b[^>]*?(?:src|href)\s*=\s*["']([^"']+)["']/g
   : path.endsWith('.css') ? /url\(\s*["']?([^\s"')]+)/g
   : /\bimport\s*\(\s*["']([^"']+)["']|\bfrom\s+["']([^"']+)["']|["']((?:\.?\.?\/|\/)?assets\/[^"']+\.(?:js|css|png|svg|woff2?))["']/g;
  const refs=[...text.matchAll(pattern)];
  for(const match of refs){const ref=match.slice(1).find(Boolean);if(!ref||/^(?:data:|blob:|#)/.test(ref))continue;
   if(/^https?:/.test(ref))fail(`External asset reference: ${ref}`);
   if(ref.startsWith('/')&&!ref.startsWith('/Kakei/'))fail(`Wrong asset base: ${ref}`);
   const clean=ref.split(/[?#]/)[0];const target=clean.startsWith('/Kakei/')?safePath(output,clean.slice(7)):clean.startsWith('assets/')?safePath(output,clean):resolve(dirname(path),clean);
   if(relative(output,target).startsWith('..')||!existsSync(target))fail(`Missing/unsafe built reference: ${ref} in ${path}`);
  }
 }
 return true;
}
export function validateNormalBuild(root=frontRoot){
 const output=join(root,'dist');scan(output);
 const {snapshot}=metadata(root);
 const identifiers=Object.keys(snapshot.receipts??{});
 for(const path of files(output)){
  if(/\/(?:demo-data|maps)\//.test(path))fail(`DEMO artifact in normal output: ${path}`);
  if(/\.(?:js|json|html|css)$/.test(path)&&identifiers.some(id=>readFileSync(path,'utf8').includes(id)))fail(`DEMO receipt identifier in normal output: ${path}`);
 }
 return true;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const mode=process.argv[2]??'source';
 try{if(mode==='source')validateDemoSource();else if(mode==='build')validateDemoBuild();else if(mode==='normal')validateNormalBuild();else fail(`Unknown mode: ${mode}`);console.log(`Validated ${mode} artifacts`);}catch(error){console.error(error.message);process.exitCode=1;}
}
