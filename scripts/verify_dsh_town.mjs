// Actual Electron + installed DSH. --live explicitly enables paid NPC turns.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {_electron,expect} from '../frontends/network-editor/node_modules/@playwright/test/index.mjs';
import {nativeUsage} from './native_usage.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const options=process.argv.slice(2),live=options.includes('--live');
const productFlag=options.indexOf('--product');
const product=productFlag<0?root:path.resolve(options[productFlag+1]);
const packaged=product!==root;
const base=await fs.mkdtemp(path.join(root,'build/dsh022-town-'));
const directory=path.join(base,'project'),profile=path.join(base,'desktop');
const source=path.join(product,'项目演示/应用3-NPC小镇-最终');
await fs.cp(source,directory,{recursive:true,filter:file=>!path.relative(source,file).split(path.sep).some(part=>['.git','runs','cache','__pycache__','desktop-session.json'].includes(part))});
const localEnv={};
for(const line of (await fs.readFile(path.join(root,'.env'),'utf8')).split(/\r?\n/)){
 const match=line.match(/^\s*(DEEPSEEK_API_KEY|DEEPSEEK_MODEL|DEEPSEEK_BASE_URL)\s*=\s*(.*?)\s*$/);
 if(match)localEnv[match[1]]=match[2].replace(/^(['"])(.*)\1$/,'$2');
}
const key=process.env.DEEPSEEK_API_KEY??localEnv.DEEPSEEK_API_KEY;
assert.ok(key,'A configured DeepSeek API key is required');
const env={...process.env,NEXARBOR_HARNESS_CONFIG:path.join(base,'harness.json'),NEXARBOR_MODEL_DIRECTORY:path.join(base,'models')};
for(const name of ['ELECTRON_RUN_AS_NODE','NEXARBOR_ROOT','NEXARBOR_WORKSPACE','DATANET_PYTHON','DATANET_PRODUCT_ROOT','DATANET_PROJECT_DIRECTORY','NEXARBOR_PROJECT_DIRECTORY','PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX'])delete env[name];
await fs.writeFile(env.NEXARBOR_HARNESS_CONFIG,JSON.stringify({executable:process.env.DATANET_HARNESS_EXE??'E:/dsh/Harness/DeepSeek Harness.exe'}));
const {createEditorClient}=await import(pathToFileURL(path.join(product,'frontends/shared/editor-client.js')).href);
let app,page,api;const errors=[],apiErrors=[],times={};
const activity=node=>node.tables.modules.find(m=>m.module_id==='agents.activity')?.state;
async function launch(){
 app=await _electron.launch({executablePath:packaged?path.join(product,'Nexarbor.exe'):path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[...packaged?[]:[path.join(root,'frontends/desktop')],'--project',directory,'--user-data-dir',profile],cwd:product,env,timeout:90000});
 page=await app.firstWindow();await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1640,1000));
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',r=>{if(r.status()>=400&&r.url().endsWith('/api'))apiErrors.push({operation:r.request().postDataJSON()?.operation,status:r.status()});});
 await expect(page.locator('.react-flow__node:not(:has(.module-view))')).toHaveCount(45,{timeout:120000});
 api=createEditorClient({endpoint:new URL('/api',page.url()).href,token:await page.evaluate(()=>sessionStorage.getItem('nexarbor-token'))});
}
async function close(){if(!app)return;await page.evaluate(()=>window.nexarborWorkspace?.flush()).catch(()=>{});await app.close();app=null;}
async function runtimeUsage(){
 const stored=JSON.parse(await fs.readFile(path.join(directory,'desktop-session.json'),'utf8'));
 return nativeUsage(stored.last.directory);
}
function subtractUsage(before,after){return {responses:after.responses-before.responses,usage:Object.fromEntries(Object.keys(after.usage).map(k=>[k,after.usage[k]-before.usage[k]]))};}
try{
 console.log(JSON.stringify({stage:'launch',base,product,live}));
 await launch();
 const connection=await api('models.connection.save',{name:'DSH compatibility verification',provider:'DeepSeek',protocol:'openai-completions',base_url:localEnv.DEEPSEEK_BASE_URL??'https://api.deepseek.com',api_key:key,models:[localEnv.DEEPSEEK_MODEL??'deepseek-flash']});
 await api('models.selection.save',{scope:'project',selection:{connection:connection.id,model:localEnv.DEEPSEEK_MODEL??'deepseek-flash'}});
 const initial=await api('state',{resume:false}),nodes=initial.live.document.network.nodes;
 const actors=nodes.filter(n=>n.type==='agent');assert.equal(actors.length,7);
 const pulse=nodes.find(n=>n.type==='pulse');assert.equal(pulse.parameters.state.sequence,30);
 const sessions=[];
 for(const actor of actors){const chat=await api('chat.read',{actor:actor.node_id});assert.equal(chat.status,'idle');sessions.push({actor:actor.node_id,name:actor.name,session:chat.session_id,messages:chat.messages.length});}
 const actor=actors.find(n=>n.name==='阿森')??actors[0];
 await page.locator('.react-flow__node[data-id="'+actor.node_id+'"]').dblclick({force:true});
 const dialog=page.locator('.chat-dialog');await expect(dialog).toBeVisible();await expect(dialog.locator('small')).toContainText('idle',{timeout:30000});await expect(dialog.locator('.notice')).toHaveCount(0);
 await page.screenshot({path:path.join(base,'npc-open.png')});
 const before=await api('chat.read',{actor:actor.node_id}),usageBefore=await runtimeUsage();
 console.log(JSON.stringify({stage:'npc-open',actor:actor.name,sessions}));
 let after=before,finished=initial;
 if(live){
  const started=Date.now();
  await dialog.getByLabel('对话输入').fill('请使用记忆查询工具查看你的记忆，然后用两三句话介绍你的身份和现在的计划。不修改记忆，不推进小镇时间。');
  await dialog.locator('.chat-composer button').click();
  await expect(dialog.getByLabel('对话输入')).toHaveValue('',{timeout:600000});
  after=await api('chat.read',{actor:actor.node_id});assert.equal(after.status,'idle');assert.ok(after.messages.length>before.messages.length);assert.ok(after.messages.slice(before.messages.length).some(m=>m.role==='assistant'&&m.content?.some(b=>b.type==='text'&&b.text.length)));assert.ok(after.messages.slice(before.messages.length).some(m=>m.role==='tool'),'NPC uses an actual memory tool');
  times.dialogue_ms=Date.now()-started;await page.screenshot({path:path.join(base,'npc-reply.png')});
  console.log(JSON.stringify({stage:'npc-replied',elapsed_ms:times.dialogue_ms}));
 }
 await dialog.locator('.modal-header button').click();
 if(live){
  const started=Date.now();
  await page.getByLabel('执行脉冲').selectOption(pulse.node_id);
  await page.getByRole('button',{name:'单步',exact:true}).click();
  await expect.poll(async()=>{const state=await api('state',{resume:false});return state.live.document.network.nodes.find(n=>n.type==='pulse').parameters.state.sequence;},{timeout:1800000,intervals:[2000]}).toBe(31);
  await expect(page.getByRole('button',{name:'运行',exact:true})).toBeEnabled({timeout:1800000});
  finished=await api('state',{resume:false});
  for(const node of finished.live.document.network.nodes.filter(n=>n.type==='agent')){
   const earlier=activity(actors.find(a=>a.node_id===node.node_id)),current=activity(node);
   assert.equal(current.completed_total,earlier.completed_total+1,'One normal activity completes for '+node.name);
   assert.ok(current.activities.every(e=>e.status==='completed'),'No failed or running activities for '+node.name);
  }
  times.tick_ms=Date.now()-started;await page.screenshot({path:path.join(base,'town-tick31.png')});
  console.log(JSON.stringify({stage:'tick-completed',tick:31,elapsed_ms:times.tick_ms}));
 }
 const retained=await api('chat.read',{actor:actor.node_id});
 const usageAfter=await runtimeUsage();
 await close();await launch();
 const reopened=await api('chat.read',{actor:actor.node_id});assert.equal(reopened.session_id,retained.session_id);assert.deepEqual(reopened.messages,retained.messages);
 const reopenedState=await api('state',{resume:false});assert.equal(reopenedState.live.document.network.nodes.find(n=>n.type==='pulse').parameters.state.sequence,live?31:30);
 await page.locator('.react-flow__node[data-id="'+actor.node_id+'"]').dblclick({force:true});await expect(page.locator('.chat-dialog small')).toContainText('idle',{timeout:30000});await expect(page.locator('.chat-dialog .notice')).toHaveCount(0);
 await page.screenshot({path:path.join(base,'npc-reopened.png')});
 assert.deepEqual(errors,[]);assert.deepEqual(apiErrors,[]);
 const report={passed:true,base,product,packaged,live,actualElectron:true,actualDSH:true,actors:sessions.length,npc:actor.name,coldReopenPreservesMessages:true,tickBefore:30,tickAfter:live?31:30,...times,usage:subtractUsage(usageBefore,usageAfter),errors,apiErrors};
 await fs.writeFile(path.join(base,'verification.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}catch(error){await page?.screenshot({path:path.join(base,'failure.png')}).catch(()=>{});const report={passed:false,base,error:String(error.stack??error).split(key).join('[redacted]'),errors,apiErrors};await fs.writeFile(path.join(base,'failure.json'),JSON.stringify(report,null,2));console.error(JSON.stringify(report));process.exitCode=1;
}finally{await close();}
