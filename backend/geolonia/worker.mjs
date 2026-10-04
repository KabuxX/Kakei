import readline from 'node:readline';
import {createDatasetFetcher} from './fetch.mjs';
import {createNormalizer} from './normalize.mjs';

const fetcher=createDatasetFetcher();const normalizer=createNormalizer({fetcher});
const input=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
for await(const line of input){
 let request;const before=fetcher.bytesRead;
 try{
  if(Buffer.byteLength(line)>4096)throw new Error('geolonia_invalid_request');
  request=JSON.parse(line);
  if(!request||typeof request.id!=='string'||request.id.length>100||typeof request.address!=='string'||!request.address.trim()||request.address.length>500||!Number.isFinite(request.timeoutMs)||request.timeoutMs<=0||request.timeoutMs>30000||!Number.isSafeInteger(request.bytesRemaining)||request.bytesRemaining<1||request.bytesRemaining>32*1024*1024)throw new Error('geolonia_invalid_request');
  const signal=AbortSignal.timeout(Math.ceil(request.timeoutMs));
  fetcher.configure({signal,bytesRemaining:request.bytesRemaining});
  const result=await normalizer.normalize(request.address);
  if(signal.aborted)throw new Error('geolonia_timeout');
  process.stdout.write(JSON.stringify({id:request.id,status:'ok',...result,bytesRead:fetcher.bytesRead-before})+'\n');
 }catch(error){
  const code=String(error.code||error.message);
  process.stdout.write(JSON.stringify({id:typeof request?.id==='string'?request.id:null,status:'error',errorCode:code.startsWith('geolonia_')?code:'geolonia_invalid_request',bytesRead:fetcher.bytesRead-before})+'\n');
 }
}
fetcher.close();
