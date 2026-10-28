// Real desktop display acceptance of the already completed town; never runs agents or advances time.
import {_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../../',import.meta.url)),out=await fs.mkdtemp(path.join(root,'build/module-subnode-desktop-')),folder=path.join(out,'project');
const source=path.join(root,'项目演示/应用3-NPC小镇-最终');
await fs.cp(source,folder,{recursive:true,filter:file=>{const rel=path.relative(source,file).replaceAll('\\','/');return !rel.split('/').includes('.git')&&!rel.startsWith('.nexarbor/runs')&&!rel.startsWith('.nexarbor/cache');}});
const declaration=JSON.parse(await fs.readFile(path.join(root,'modules/context_assembler/module.json'),'utf8'));
const moduleFile=path.join(folder,'modules/context_assembler/module.json'),module=JSON.parse(await fs.readFile(moduleFile,'utf8'));module.frontend=declaration.frontend;await fs.writeFile(moduleFile,JSON.stringify(module,null,2));
let client,page;const errors=[],apiErrors=[];
const env={...process.env,NEXARBOR_ROOT:root,NEXARBOR_MODEL_DIRECTORY:path.join(out,'models')};delete env.ELECTRON_RUN_AS_NODE;
const api=(operation,params={})=>page.evaluate(async({operation,params})=>{const r=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':sessionStorage.getItem('nexarbor-token')},body:JSON.stringify({operation,params})}),v=await r.json();if(!r.ok||v.error)throw Error(v.error);return v.value;},{operation,params});
async function launch(){
 client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--project',folder,'--user-data-dir',path.join(out,'client')],env,timeout:60000});
 page=await client.firstWindow();page.on('pageerror',e=>errors.push(e.message));page.on('response',async r=>{if(r.status()>=400&&r.url().endsWith('/api'))apiErrors.push({operation:r.request().postDataJSON()?.operation,status:r.status()});});
 await expect(page.locator('.module-view').first()).toBeVisible({timeout:60000});
}
try{
 await launch();let state=await api('state',{resume:false}),nodes=state.live.document.network.nodes;
 const expected=nodes.filter(n=>n.tables.modules.some(m=>m.module_id==='context.assembler')).length;
 await expect(page.locator('.module-view')).toHaveCount(expected);expect(nodes).toHaveLength(52);
 expect(nodes.some(n=>['subnode','module_view'].includes(n.type))).toBe(false);
 expect(nodes.find(n=>n.type==='pulse').parameters.state.sequence).toBe(25);
 await page.screenshot({path:path.join(out,'town-module-overview.png')});
 const card=page.locator('.module-view').filter({hasText:'小砾'}).first();await card.click({force:true});
 const mounted=page.locator('[data-mounted-id="context.assembler"]');await expect(mounted).toHaveAttribute('open','');
 await expect(card).toContainText('系统提示');await expect(card).toContainText('参考资料');await expect(card).toContainText('输入事件');await expect(card).toContainText('尾部快照');
 const frame=mounted.frameLocator('iframe');await frame.locator('#preview').click();await expect(frame.locator('#result')).toContainText('system_prompt',{timeout:15000});
 await page.screenshot({path:path.join(out,'town-context-module.png')});
 const view=await api('view',{actor:'小砾',strength:2});expect(Object.keys(view.reachable).length).toBeGreaterThan(0);expect(view.paths).toBeUndefined();
 await page.getByRole('button',{name:'Commit',exact:true}).click();await expect(page.getByRole('button',{name:'Commit',exact:true})).toBeEnabled({timeout:30000});
 await client.close();client=null;await launch();await expect(page.locator('.module-view')).toHaveCount(expected);
 state=await api('state',{resume:false});expect(state.live.document.network.nodes).toHaveLength(52);expect(state.live.document.network.nodes.find(n=>n.type==='pulse').parameters.state.sequence).toBe(25);
 expect(errors).toEqual([]);expect(apiErrors).toEqual([]);
 const result={passed:true,paid_api_calls:0,town_agent_runs:0,town_ticks_advanced:0,actualDesktop:true,real_nodes:52,module_cards:expected,config_and_actual_preview:true,access_view:true,commit_cold_reopen:true,errors,apiErrors,screenshots:['town-module-overview.png','town-context-module.png']};
 await fs.writeFile(path.join(out,'verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({directory:out,...result}));
}catch(error){await fs.writeFile(path.join(out,'failure.json'),JSON.stringify({error:error.stack,errors,apiErrors},null,2));await page?.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});console.log('FAILED '+out);throw error;}finally{await client?.close();}
