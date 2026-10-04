import {test} from 'node:test';
import assert from 'node:assert/strict';
import {datasetFixture,publicLookup} from './fixtures.mjs';

test('official_normalizer_returns_record_and_cached_proof',async()=>{
 const module=await import('../normalize.mjs').catch(()=>null);
 assert.ok(module,'official Geolonia normalizer adapter is missing');
 const {createDatasetFetcher}=await import('../fetch.mjs');
 const fixture=datasetFixture();
 const fetcher=createDatasetFetcher({fetchImpl:fixture.fetchImpl,lookup:publicLookup});
 const normalizer=module.createNormalizer({fetcher});
 const first=await normalizer.normalize('東京都文京区本郷1-2-3');
 const count=fixture.calls.length;
 const second=await normalizer.normalize('東京都文京区本郷一丁目2番3号');
 assert.equal(first.match.level,8);assert.equal(first.match.point.level,8);
 assert.deepEqual(first.match.record,{kind:'rsdt',fields:{blk_num:'2',rsdt_num:'3',point:[139.7,35.7]}});
 assert.deepEqual(second.proof.fetches,first.proof.fetches);assert.equal(fixture.calls.length,count);
 const coarse=await normalizer.normalize('東京都文京区本郷2-2-3');
 assert.equal(coarse.match.level,8);assert.equal(coarse.match.point.level,3);
 const land=await normalizer.normalize('東京都文京区湯島2-3');
 assert.equal(land.match.point.level,8);assert.equal(land.match.record.kind,'chiban');
});
