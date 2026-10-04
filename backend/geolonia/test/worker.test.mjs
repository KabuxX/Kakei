import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';

test('worker_emits_bounded_json_and_classified_errors',async()=>{
 const child=spawn(process.execPath,[new URL('../worker.mjs',import.meta.url).pathname]);
 let output='',error='';child.stdout.on('data',c=>output+=c);child.stderr.on('data',c=>error+=c);
 child.stdin.end('broken\n'+JSON.stringify({id:'x',address:'x'.repeat(501),timeoutMs:10,bytesRemaining:100})+'\n');
 const exit=await new Promise(resolve=>child.on('close',resolve));
 assert.equal(exit,0,error);
 const rows=output.trim().split('\n').map(s=>JSON.parse(s));
 assert.equal(rows.length,2);assert.equal(rows[0].errorCode,'geolonia_invalid_request');
 assert.equal(rows[1].id,'x');assert.equal(rows[1].errorCode,'geolonia_invalid_request');
 assert.equal(error,'');
});
