import {createServer} from 'node:http';
import {createReadStream, statSync} from 'node:fs';
import {resolve, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.png':'image/png','.svg':'image/svg+xml','.ttf':'font/ttf','.pmtiles':'application/octet-stream','.txt':'text/plain; charset=utf-8'};
const csp="default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-src 'self' blob:; form-action 'none'";
export function createDemoCheckServer({root=fileURLToPath(new URL('../dist-demo/',import.meta.url)),ranges=true,log=console.log}={}) {
 root=resolve(root);
 return createServer((request,response)=>{
 response.setHeader('Content-Security-Policy',csp);
 response.setHeader('X-Content-Type-Options','nosniff');
 response.on('finish',()=>log(JSON.stringify({method:request.method,path:request.url,status:response.statusCode,range:request.headers.range??null,contentRange:response.getHeader('Content-Range')??null,api:/(?:^|\/)api(?:\/|$)/.test(request.url)})));
 let pathname;try{pathname=decodeURIComponent(new URL(request.url,'http://localhost').pathname);}catch{response.writeHead(400);response.end('Bad URL');return;}
 if(/(?:^|\/)api(?:\/|$)/.test(pathname)){response.writeHead(502);response.end('API forbidden in static demo');return;}
 if(!['GET','HEAD'].includes(request.method)){response.writeHead(405);response.end();return;}
 if(pathname==='/Kakei'){response.writeHead(308,{Location:'/Kakei/'});response.end();return;}
 if(!pathname.startsWith('/Kakei/')){response.writeHead(404);response.end();return;}
 const path=resolve(root,pathname.slice(7)||'index.html');
 if(!path.startsWith(root+'/')){response.writeHead(403);response.end();return;}
 let stat;try{stat=statSync(path);if(!stat.isFile())throw Error();}catch{response.writeHead(404);response.end('Not found');return;}
 response.setHeader('Content-Type',types[extname(path)]??'application/octet-stream');
 response.setHeader('Accept-Ranges',ranges?'bytes':'none');
 response.setHeader('Cache-Control','no-store');
 let start=0,end=stat.size-1;
 if(ranges&&request.headers.range){
  const match=/^bytes=(\d*)-(\d*)$/.exec(request.headers.range);
  if(!match||(!match[1]&&!match[2])){response.writeHead(416,{'Content-Range':`bytes */${stat.size}`});response.end();return;}
  if(!match[1])start=Math.max(0,stat.size-Number(match[2]));else{start=Number(match[1]);if(match[2])end=Math.min(end,Number(match[2]));}
  if(start>end||start>=stat.size){response.writeHead(416,{'Content-Range':`bytes */${stat.size}`});response.end();return;}
  response.statusCode=206;response.setHeader('Content-Range',`bytes ${start}-${end}/${stat.size}`);
 }
 response.setHeader('Content-Length',Math.max(0,end-start+1));
 if(request.method==='HEAD'){response.end();return;}
 createReadStream(path,{start,end}).on('error',()=>response.destroy()).pipe(response);
});
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=process.argv.slice(2), portIndex=args.indexOf('--port');
 const port=portIndex<0?8770:Number(args[portIndex+1]);
 if(!Number.isInteger(port)||port<1||port>65535)throw Error('Invalid --port');
 const ranges=!args.includes('--no-range');
 createDemoCheckServer({ranges}).listen(port,'127.0.0.1',()=>console.log(`Local-only demo check: http://127.0.0.1:${port}/Kakei/ (Range ${ranges?'enabled':'disabled'}; CSP enforced; API forbidden)`));
}
