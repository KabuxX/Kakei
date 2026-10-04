/** Manual acquisition tools; never invoked by runtime or builds. */
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { gunzipSync, gzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { bytesToHeader, SharedPromiseCache } from '../../front/node_modules/pmtiles/dist/esm/index.js';
const root = fileURLToPath(new URL('../../front/demo/public/maps/', import.meta.url));
const manifestPath = new URL('../../front/demo/maps/manifest.json', import.meta.url);
export const sha256 = b => createHash('sha256').update(b).digest('hex');
function fields(bytes) {
  let p = 0; const result = [];
  function varint() { let n = 0, shift = 0; while (p < bytes.length) { const b = bytes[p++]; n += (b & 127) * 2 ** shift; if (b < 128) return n; shift += 7; if (shift > 49) throw Error('Invalid protobuf'); } throw Error('Truncated protobuf'); }
  while (p < bytes.length) {
    const start = p, tag = varint(), wire = tag & 7; let data;
    if (wire === 2) { const size = varint(); data = bytes.subarray(p,p + size); p += size; }
    else if (wire === 0) varint(); else if (wire === 1) p += 8; else if (wire === 5) p += 4; else throw Error('Invalid protobuf wire');
    if (p > bytes.length) throw Error('Truncated protobuf');
    result.push({ number: tag >> 3, data, raw: bytes.subarray(start,p) });
  }
  return result;
}
/** Retained MVT layers are copied as opaque bytes, including all geometry. */
export function filterTileLayers(bytes) {
  return Buffer.concat(fields(bytes).filter(field => {
    if (field.number !== 3) return true;
    const name = fields(field.data).find(f => f.number === 1)?.data?.toString();
    return !['buildings','pois'].includes(name);
  }).map(f=>f.raw));
}
function varint(n) { const b=[]; do { const low=n%128; n=Math.floor(n/128); b.push(low+(n?128:0)); } while(n); return Buffer.from(b); }
export async function repackMap(input, output) {
  const file = await readFile(input);
  const source = { getKey:()=>input, getBytes:async(o,n)=>({data:Uint8Array.from(file.subarray(o,o+n)).buffer}) };
  const header = bytesToHeader((await source.getBytes(0,127)).data), cache = new SharedPromiseCache();
  if (header.internalCompression !== 2 || header.tileCompression !== 2) throw Error('Expected gzip PMTiles');
  const entries = [], tiles = []; let offset = 0;
  async function walk(o,n) { for (const e of await cache.getDirectory(source,o,n,header)) {
    if (!e.runLength) { await walk(header.leafDirectoryOffset+e.offset,e.length); continue; }
    const tile = gzipSync(filterTileLayers(gunzipSync(file.subarray(header.tileDataOffset+e.offset,header.tileDataOffset+e.offset+e.length))),{level:9,mtime:0});
    entries.push({...e,offset,length:tile.length});tiles.push(tile);offset += tile.length;
  }}
  await walk(header.rootDirectoryOffset,header.rootDirectoryLength);
  const parts = [varint(entries.length)]; let previous = 0;
  for (const e of entries) { parts.push(varint(e.tileId-previous));previous=e.tileId; }
  for (const e of entries) parts.push(varint(e.runLength));
  for (const e of entries) parts.push(varint(e.length));
  for (let i=0;i<entries.length;i++) parts.push(varint(i?0:1));
  const directory=gzipSync(Buffer.concat(parts),{level:9});
  const metadata=JSON.parse(gunzipSync(file.subarray(header.jsonMetadataOffset,header.jsonMetadataOffset+header.jsonMetadataLength)));
  metadata.vector_layers=metadata.vector_layers.filter(l=>!['buildings','pois'].includes(l.id));
  const meta=gzipSync(JSON.stringify(metadata),{level:9});const newHeader=Buffer.from(file.subarray(0,127));
  const values=[127,directory.length,127+directory.length,meta.length,127+directory.length+meta.length,0,127+directory.length+meta.length,offset,header.numAddressedTiles,entries.length,entries.length];
  values.forEach((v,i)=>newHeader.writeBigUInt64LE(BigInt(v),8+i*8));
  await writeFile(output,Buffer.concat([newHeader,directory,meta,...tiles]));
  return { originalBytes:file.length, bytes:127+directory.length+meta.length+offset, entries:entries.length };
}
export function checkSnapshotContainment(snapshot,bounds) {
  const [west,south,east,north]=bounds;
  const places=snapshot.timeline.places, referenced=new Set();
  for (const day of Object.values(snapshot.timeline.days)) {
    for (const event of day.events) referenced.add(event.placeId);
    for (const leg of day.legs) for (const id of leg.viaPlaceIds || []) referenced.add(id);
  }
  const outside=coordinates=>Array.isArray(coordinates)&&coordinates.every(Number.isFinite)&&(coordinates[0]<west||coordinates[0]>east||coordinates[1]<south||coordinates[1]>north);
  const missing=[];
  for (const id of referenced) {
    if (!places[id]) throw Error(`Missing map place ${id}`);
    if (outside(places[id].coordinates)) throw Error(`Referenced place outside map bounds: ${id}`);
    if (!Array.isArray(places[id].coordinates)||!places[id].coordinates.every(Number.isFinite)) missing.push(id);
  }
  return {referencedPlaces:referenced.size,allReferencedCoordinatesWithinBounds:true,unconfirmedPlaces:missing,unusedOutsidePlaces:Object.entries(places).filter(([id,p])=>!referenced.has(id)&&outside(p.coordinates)).map(([id])=>id)};
}
export async function validateMapAssets({ read=readFile }={}) {
  const manifest=JSON.parse(await readFile(manifestPath));
  if (manifest.bytes>50*1024*1024) throw Error('Map exceeds 50 MiB');
  for (const resource of [{path:'tokyo.pmtiles',bytes:manifest.bytes,sha256:manifest.sha256},...manifest.resources]) {
    const data=await read(root+resource.path);
    if (data.length!==resource.bytes || sha256(data)!==resource.sha256) throw Error(`Invalid map resource ${resource.path}`);
  }
  const snapshot=JSON.parse(await readFile(new URL('../../front/demo/data/snapshot.json',import.meta.url)));
  checkSnapshotContainment(snapshot,manifest.bounds);
  const data=await read(root+'tokyo.pmtiles');
  if (data.subarray(0,8).toString('hex')!=='504d54696c657303') throw Error('Invalid PMTiles header');
  return true;
}
if (process.argv[1]===fileURLToPath(import.meta.url)) {
  if (process.argv[2]==='repack') console.log(await repackMap(process.argv[3],process.argv[4]));
  else if (process.argv[2]==='validate') console.log(await validateMapAssets());
  else throw Error('Usage: node tools/demo/prepare-map.mjs repack INPUT OUTPUT | validate');
}
