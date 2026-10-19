import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {startEditorServer} from '../../../communication/editor-server.js';import {createEditorClient} from '../../../communication/editor-client.js';
const root=fileURLToPath(new URL('../../../',import.meta.url));
test('transport works with an injected handler and browser client, without graph or Harness services',async()=>{
 const directory=await fs.mkdtemp(path.join(root,'build/communication-')),server=await startEditorServer({directory,web:path.join(root,'extensions/editor/capabilities/network_editor/web'),request:async(op,p)=>{if(op==='fail')throw Error('明确错误');return {operation:op,params:p};}});
 try{const token=new URLSearchParams(new URL(server.url).hash.slice(1)).get('token'),request=createEditorClient({token,endpoint:'http://'+server.authority+'/api'});assert.deepEqual(await request('independent',{text:'中文'}),{operation:'independent',params:{text:'中文'}});await assert.rejects(request('fail'),/明确错误/);await assert.rejects(createEditorClient({endpoint:'http://'+server.authority+'/api'})('state'),/启动地址/);}finally{await server.close();}
});
