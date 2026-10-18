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

test('module pages have a scoped capability URL, injected bridge and opaque sandbox',async()=>{
 const root=path.join(product,'build/editor-http-tests');await fs.mkdir(root,{recursive:true});
 const directory=await fs.mkdtemp(path.join(root,'frontend-'));
 let page={module:'example.counter',title:'计数配置',height:320,html:'<!doctype html><html><head></head><body>组件页面</body></html>'};
 const server=await startEditorServer({web:path.join(product,'extensions/editor/capabilities/network_editor/web'),directory,
  request:async()=>page,chat:async()=>{},recover:async()=>{}});
 try{
  const base='http://'+server.authority,token=new URLSearchParams(new URL(server.url).hash.slice(1)).get('token');
  const request=()=>fetch(base+'/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':token},body:JSON.stringify({operation:'module.frontend',params:{module:'example.counter'}})});
  const result=await (await request()).json();
  assert.match(result.value.src,/^\/module-frontend\/[a-f0-9]{48}$/);
  assert.equal(result.value.html,undefined);assert.ok(!JSON.stringify(result).includes(token));
  const response=await fetch(base+result.value.src),html=await response.text();
  assert.equal(response.status,200);assert.match(html,/window.NexarborModule/);
  assert.ok(html.indexOf('nexarbor-module-frontend/v1')<html.indexOf('</head>'));
  assert.match(response.headers.get('content-security-policy'),/sandbox allow-scripts/);
  assert.match(response.headers.get('content-security-policy'),/connect-src 'none'/);
  assert.ok(!response.headers.get('content-security-policy').includes('allow-same-origin'));
  assert.equal((await fetch(base+'/module-frontend/unknown')).status,404);
  assert.equal((await fetch(base+result.value.src,{method:'POST'})).status,405);
  assert.equal((await (await request()).json()).value.src,result.value.src);
  page=null;assert.equal((await (await request()).json()).value,null);
  page={html:'x'.repeat(1024*1024+1)};assert.equal((await request()).status,400);
 }finally{
  await server.close();const relative=path.relative(root,directory);assert.ok(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative));await fs.rm(directory,{recursive:true});
 }
});
