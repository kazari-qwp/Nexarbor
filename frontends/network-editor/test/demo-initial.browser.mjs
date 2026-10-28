// Cold-open the three delivered initial projects through the real desktop; never run agents or ticks.
import {_electron,expect} from '@playwright/test';import assert from 'node:assert/strict';
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {createEditorClient} from '../../shared/editor-client.js';
const root=fileURLToPath(new URL('../../../',import.meta.url)),base=await fs.mkdtemp(path.join(root,'build/demo-initial-client-')),results=[];
for(const [name,nodes,agents] of [['应用1-讨论协作-初始',2,1],['应用2-资料库-初始',4,1],['应用3-NPC小镇-初始',52,7]]){
 const folder=path.join(base,name),errors=[],apiErrors=[];await fs.cp(path.join(root,'项目演示',name),folder,{recursive:true,filter:file=>!file.split(path.sep).some(part=>['.git','runs','cache'].includes(part))});let client,page;
 const env={...process.env,NEXARBOR_ROOT:root,NEXARBOR_MODEL_DIRECTORY:path.join(base,'models')};delete env.ELECTRON_RUN_AS_NODE;
 const launch=async()=>{client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--project',folder,'--user-data-dir',path.join(base,'client-'+nodes)],env,timeout:60000});page=await client.firstWindow();page.on('pageerror',e=>errors.push(e.message));page.on('response',async response=>{if(response.status()>=400&&response.url().endsWith('/api'))apiErrors.push({operation:response.request().postDataJSON().operation,error:(await response.json()).error});});await expect(page.locator('.react-flow__node:not(:has(.module-view))')).toHaveCount(nodes,{timeout:60000});};
 const api=async(operation,params={})=>createEditorClient({endpoint:new URL('/api',page.url()).href,token:await page.evaluate(()=>sessionStorage.getItem('nexarbor-token'))})(operation,params);
 try{
  await launch();const state=await api('state',{resume:false}),actors=state.live.document.network.nodes.filter(node=>node.type==='agent');assert.equal(actors.length,agents);assert.ok(Object.values(state.live.sessions).every(binding=>!binding.session_id));const pulse=state.live.document.network.nodes.find(node=>node.type==='pulse');if(pulse)assert.equal(pulse.parameters.state.sequence,0);
  const history=await api('chat.read',{actor:actors[0].node_id});assert.equal(history.messages.length,0);await page.screenshot({path:path.join(base,name+'.png')});await client.close();client=null;await launch();const cold=await api('state',{resume:false});assert.equal(cold.live.document.network.nodes.length,nodes);assert.equal((await api('chat.read',{actor:actors[0].node_id})).messages.length,0);assert.deepEqual(errors,[]);assert.deepEqual(apiErrors,[]);results.push({name,nodes,agents,coldRestart:true,initialHistoryEmpty:true,...(pulse?{tick:0}:{}),errors,apiErrors});
 }catch(error){await page?.screenshot({path:path.join(base,name+'-failure.png')}).catch(()=>{});throw error;}finally{await client?.close();}
}
await fs.writeFile(path.join(base,'verification.json'),JSON.stringify({passed:true,paidCalls:0,ticksAdvanced:0,results},null,2));console.log('PASS '+base);
