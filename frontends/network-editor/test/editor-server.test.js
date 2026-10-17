import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import {startEditorServer} from '../../../adapters/harness/framework/editor-server.js';
const product=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
test('loopback editor requires credentials, checks origin and dispatches only explicit host operations',async()=>{
 const root=path.join(product,'build/editor-http-tests');await fs.mkdir(root,{recursive:true});const directory=await fs.mkdtemp(path.join(root,'run-'));
 const server=await startEditorServer({web:path.join(product,'extensions/editor/capabilities/network_editor/web'),directory,
  request:async(operation,params)=>({operation,params}),chat:async()=>({chat:true}),recover:async()=>({recovered:true})});
 try{
  const base='http://'+server.authority,token=new URLSearchParams(new URL(server.url).hash.slice(1)).get('token');
  assert.equal((await fetch(base)).status,200);
  const headers={'Content-Type':'application/json','X-Nexarbor-Token':token};
  const send=(headers_)=>fetch(base+'/api',{method:'POST',headers:headers_,body:JSON.stringify({operation:'state',params:{}})});
  assert.equal((await send({'Content-Type':'application/json'})).status,401);
  assert.equal((await send({...headers,Origin:'https://untrusted.example'})).status,403);
  assert.deepEqual(await (await send(headers)).json(),{value:{operation:'state',params:{}}});
  const body=Buffer.from(JSON.stringify({operation:'draft',params:{name:'小树林'}}));
  const split=body.indexOf(Buffer.from('小'))+1;
  const chunked=await new Promise((resolve,reject)=>{
   const request=http.request(base+'/api',{method:'POST',headers},response=>{
    const chunks=[];response.on('data',chunk=>chunks.push(chunk));response.on('end',()=>resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))));
   });request.on('error',reject);request.write(body.subarray(0,split));setTimeout(()=>request.end(body.subarray(split)),5);
  });
  assert.equal(chunked.value.params.name,'小树林');
  assert.equal((await fetch(base+'/api')).status,405);
 }finally{
  await server.close();const relative=path.relative(root,directory);assert.ok(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative));await fs.rm(directory,{recursive:true});
 }
});
