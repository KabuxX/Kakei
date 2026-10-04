import {test} from 'node:test';
import assert from 'node:assert/strict';
import {HOST,publicLookup} from './fixtures.mjs';

async function create(opts){
 const module=await import('../fetch.mjs').catch(()=>null);
 assert.ok(module,'bounded dataset fetcher is missing');
 return module.createDatasetFetcher({lookup:publicLookup,...opts});
}
test('range_response_must_match_requested_bytes',async()=>{
 const f=await create({fetchImpl:async()=>new Response('abc',{status:206,headers:{'Content-Range':'bytes 10-12/100'}})});
 assert.equal(await (await f.request(new URL(HOST+'/api/ja/a.txt'),{offset:10,length:3})).text(),'abc');
 for(const response of [new Response('abc'),new Response('abc',{status:206,headers:{'Content-Range':'bytes 9-11/100'}})]){
  const bad=await create({fetchImpl:async()=>response});
  await assert.rejects(()=>bad.request(new URL(HOST+'/api/ja/a.txt'),{offset:10,length:3}),{code:'geolonia_invalid_range'});
 }
});
test('caps_streamed_bytes_and_blocks_unsafe_targets',async()=>{
 const f=await create({fetchImpl:async()=>new Response('x'.repeat(8*1024*1024+1))});
 await assert.rejects(()=>f.request(new URL(HOST+'/api/ja.json')),{code:'geolonia_size_limit'});
 await assert.rejects(()=>f.request(new URL('https://evil.example/api/ja.json')),{code:'geolonia_unsafe_url'});
 const bad=await create({lookup:async()=>[{address:'::ffff:127.0.0.1',family:6}],fetchImpl:async()=>new Response('{}')});
 await assert.rejects(()=>bad.request(new URL(HOST+'/api/ja.json')),{code:'geolonia_unsafe_address'});
 const redirect=await create({fetchImpl:async()=>new Response('',{status:302,headers:{Location:'https://evil.example/'}})});
 await assert.rejects(()=>redirect.request(new URL(HOST+'/api/ja.json')),{code:'geolonia_unsafe_url'});
});
test('retries_only_transient_errors_three_times_and_memoizes_failure',async()=>{
 let calls=0;const f=await create({fetchImpl:async()=>{calls++;return new Response('',{status:503});},sleep:async()=>{}});
 await assert.rejects(()=>f.request(new URL(HOST+'/api/ja.json')),{code:'geolonia_network'});
 await assert.rejects(()=>f.request(new URL(HOST+'/api/ja.json')),{code:'geolonia_network'});
 assert.equal(calls,3);
});
test('aggregate_budget_counts_all_downloaded_bytes',async()=>{
 const f=await create({fetchImpl:async()=>new Response('['+' '.repeat(8*1024*1024-2)+']')});
 for(let i=0;i<4;i++)await f.request(new URL(HOST+`/api/ja/a${i}.json`));
 await assert.rejects(()=>f.request(new URL(HOST+'/api/ja/a4.json')),{code:'geolonia_size_limit'});
});
