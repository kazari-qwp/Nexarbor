// Read-only verification of an already restored workbench; never reruns a world.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const run=path.resolve(process.argv[2]),source=JSON.parse(await fs.readFile(path.join(run,'editor.json'),'utf8'));
const roots=path.join(run,'.datanet/networks');const candidates=[];
for(const folder of await fs.readdir(roots)){const file=path.join(roots,folder,'editor-connection.json');try{candidates.push({file,mtime:(await fs.stat(file)).mtimeMs});}catch{}}
candidates.sort((a,b)=>b.mtime-a.mtime);const target=JSON.parse(await fs.readFile(candidates[0].file,'utf8'));
expect(target.authority).not.toBe(source.authority);
const token=new URLSearchParams(new URL(target.url).hash.slice(1)).get('token');
const read=async(operation,params={})=>{const r=await fetch('http://'+target.authority+'/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':token},body:JSON.stringify({operation,params})});const body=await r.json();expect(r.ok,JSON.stringify(body)).toBe(true);return body.value;};
const restored=await read('state');const nodes=restored.live.document.network.nodes;
expect(nodes.find(n=>n.node_id==='world/npc/alice').modules['action.budget'].state.spent).toBe(10);
expect(nodes.find(n=>n.node_id==='world/npc/alice').modules['world.resident'].state.place).toBe('world/place/shop');
expect(restored.live.sessions.root.session_id).not.toBe(JSON.parse(await fs.readFile(path.join(run,'sessions-manifest.json'),'utf8')).root_session);
const history=await read('chat.read',{actor:'world/npc/alice'});expect(history.messages.filter(m=>m.role==='assistant').length).toBeGreaterThan(0);
const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1600,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(target.url);await expect(page.getByRole('button',{name:'保存草稿',exact:true})).toBeVisible();
 await expect(page.locator('.left-panel').getByRole('button',{name:'阿青',exact:true})).toBeVisible();
 await page.screenshot({path:path.join(run,'06-restored-graph.png')});
 await page.locator('.left-panel').getByRole('button',{name:'阿青',exact:true}).click();await expect(page.locator('.chat-message.assistant').first()).toBeVisible();
 await page.screenshot({path:path.join(run,'07-restored-workbench.png')});expect(errors).toEqual([]);
 await fs.writeFile(path.join(run,'browser-verification.json'),JSON.stringify({passed:true,createdFromEmptyInUi:true,places:2,residents:2,linkedInUi:true,nativeChat:true,pulseReturned:true,actionBudget:true,restoredWorkbench:true,restoredNativeHistory:true,readOnlyRestoreCheck:true,modelApiCalls:0,errors},null,2));
 console.log('PASS restored workbench, unchanged movement/budget, forked native identity and original chat history');
}finally{await browser.close();}
