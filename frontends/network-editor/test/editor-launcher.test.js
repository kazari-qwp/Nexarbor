import test from 'node:test';
import assert from 'node:assert/strict';
import {registerEditorLauncher} from '../../../adapters/harness/framework/editor-launcher.js';
test('native launcher resolves only bound sessions and rejects non-loopback launch addresses',async()=>{
 let route,opened=0;const scope={effect:fn=>fn(),connection:{fetch:{register:value=>{route=value;return()=>{};}}}};
 registerEditorLauncher({inject:(_names,fn)=>fn(scope)},async id=>{
  if(id==='other')throw new Error('not bound');
  return {url:id==='unsafe'?'https://untrusted.example/':'http://127.0.0.1:12345/#token=example'};
 },async()=>{opened++;return {opened:true,kind:'desktop'};});
 assert.equal(route.path,'/api/nexarbor/editor');assert.deepEqual(route.methods,['POST']);
 const send=(session_id,open=false)=>route.fetch(new Request('http://localhost'+route.path,{method:'POST',body:JSON.stringify({session_id,open})}));
 assert.equal((await send('bound')).status,200);
 assert.equal((await send('other')).status,400);
 assert.equal((await send('unsafe')).status,400);
 assert.equal((await send('')).status,400);
 assert.equal(opened,0);assert.deepEqual(await (await send('bound',true)).json(),{opened:true,kind:'desktop'});assert.equal(opened,1);
});
