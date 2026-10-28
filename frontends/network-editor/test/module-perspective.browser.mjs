// Actual desktop interaction with a copy of the completed town; no model or tick execution.
import {_electron,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {moduleViewId} from '../src/module-projection.js';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const base=await fs.mkdtemp(path.join(root,'build/module-perspective-client-')),folder=path.join(base,'project');
await fs.cp(path.join(root,'项目演示/应用3-NPC小镇-最终'),folder,{recursive:true,filter:file=>!file.split(path.sep).some(part=>['.git','runs','cache','__pycache__'].includes(part))});
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
let client,page;
const errors=[],apiErrors=[];
const api=(operation,params={})=>page.evaluate(async({operation,params})=>{
 const response=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':sessionStorage.getItem('nexarbor-token')},body:JSON.stringify({operation,params})});
 const result=await response.json();if(!response.ok||result.error)throw Error(result.error);return result.value;
},{operation,params});
async function launch(){
 client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--project',folder,'--user-data-dir',path.join(base,'client')],env,timeout:90000});
 page=await client.firstWindow();page.on('pageerror',error=>errors.push(error.message));
 page.on('response',response=>{if(response.status()>=400&&response.url().endsWith('/api'))apiErrors.push({operation:response.request().postDataJSON()?.operation,status:response.status()});});
 await expect(page.getByRole('button',{name:'全局网络',exact:true})).toBeVisible({timeout:60000});
}
const visibleIds=()=>page.locator('.react-flow__node').evaluateAll(nodes=>nodes.map(node=>node.dataset.id).sort());
try{
 await launch();await expect(page.locator('.module-view')).toHaveCount(7);
 const before=(await api('state',{resume:false})).live.document,owner=before.network.nodes.find(node=>node.node_id==='小砾');
 assert.equal(before.network.nodes.length,45);
 const module=owner.tables.modules.find(item=>item.module_id==='context.assembler'),channels=new Set(Object.values(module.config).flat());
 const links=owner.links.map((edge,index)=>({...edge,id:owner.node_id+'|'+index})).filter(edge=>edge.channels.some(channel=>channels.has(channel)));
 const id=moduleViewId(owner.node_id,module.module_id),expected=[...new Set([owner.node_id,id,...links.map(link=>link.target_id)])].sort();
 const card=page.locator('.react-flow__node').filter({has:page.locator('.module-view')}).filter({has:page.locator('.network-node[title*="小砾"]')});
 await expect(card).toHaveCount(1);await card.click({force:true});
 await expect.poll(visibleIds).toEqual(expected);await expect(page.locator('.module-view')).toHaveCount(1);
 await expect(page.locator('.view-tabs button.active')).toHaveText('局部视角');
 await expect(page.locator('[data-mounted-id="context.assembler"]')).toHaveAttribute('open','');
 assert.deepEqual((await page.locator('.react-flow__edge:not(.react-flow__edge-ownership)').evaluateAll(edges=>edges.map(edge=>edge.dataset.id))).sort(),links.map(edge=>edge.id).sort());
 await page.screenshot({path:path.join(base,'module-local.png')});
 await page.getByRole('button',{name:'全局网络',exact:true}).click();
 await expect(page.locator('.module-view')).toHaveCount(7);
 await expect(page.locator('.react-flow__node:not(:has(.module-view))')).toHaveCount(45);
 await page.getByRole('button',{name:'亚节点',exact:true}).click();
 await expect(page.locator('.module-view')).toHaveCount(0);await expect(page.locator('.react-flow__edge-ownership')).toHaveCount(0);
 assert.ok((await page.locator('.react-flow__edge').evaluateAll(edges=>edges.map(edge=>edge.getAttribute('aria-label')))).every(label=>!label?.includes('module-view:')));
 await page.getByRole('button',{name:'亚节点',exact:true}).click();await expect(card).toHaveCount(1);
 await card.click({force:true});await expect.poll(visibleIds).toEqual(expected);
 await page.evaluate(()=>window.nexarborWorkspace.flush());
 const saved=(await api('state',{resume:true})).workspace;
 assert.deepEqual(saved.view.moduleFocus,{owner:owner.node_id,module:module.module_id});assert.equal(saved.dirty,false);
 await client.close();client=null;await launch();await expect.poll(visibleIds).toEqual(expected);
 await page.screenshot({path:path.join(base,'module-local-restored.png')});
 const after=(await api('state',{resume:false})).live.document;
 assert.deepEqual(after,before);assert.equal(after.network.nodes.find(node=>node.type==='pulse').parameters.state.sequence,30);
 const chat=await api('chat.read',{actor:owner.node_id});assert.ok(chat.messages.length>5);
 assert.deepEqual(errors,[]);assert.deepEqual(apiErrors,[]);
 const report={passed:true,actualDesktop:true,nodes:45,localNodes:expected,localLinks:links.length,existingSubnodeFilter:true,globalReturn:true,coldViewRestore:true,documentUnchanged:true,historyMessages:chat.messages.length,tick:30,modelCalls:0,errors,apiErrors,base};
 await fs.writeFile(path.join(base,'verification.json'),JSON.stringify(report,null,2));
 await fs.writeFile(path.join(root,'build/module-perspective-verification.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}catch(error){if(page&&!page.isClosed())await page.screenshot({path:path.join(base,'failure.png')});throw error;}
finally{await client?.close();}
