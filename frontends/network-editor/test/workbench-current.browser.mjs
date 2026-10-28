import readAgentDefaults from '../../../adapt/harness/framework/agent-defaults.cjs';
// The original desktop main entry, real Electron renderer and real Python backend.
import { _electron as electron } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {Project} from '../../../adapt/harness/studio/project.mjs';
import {ModelConnections} from '../../../adapt/harness/studio/model-connections.mjs';
const root=path.resolve('../../'),directory=path.resolve(process.argv[2]);await fs.mkdir(directory,{recursive:true});
const folder=path.join(directory,'project');await fs.cp(path.join(root,'resources/examples/npc-town'),folder,{recursive:true});
const live=process.argv.includes('--live');
if(live){
 assert.ok(process.env.DEEPSEEK_API_KEY,'Missing configured DeepSeek API key');
 const project=new Project(folder,path.join(directory,'setup'));await project.initialize();
 const models=new ModelConnections({project,configDirectory:path.join(directory,'models')});
 const connection=await models.save({name:'DeepSeek 验收',provider:'DeepSeek',protocol:'openai-completions',base_url:process.env.DEEPSEEK_BASE_URL??'https://api.deepseek.com',models:[process.env.DEEPSEEK_MODEL??'deepseek-flash'],api_key:process.env.DEEPSEEK_API_KEY});
 await models.choose('network',{connection:connection.id,model:process.env.DEEPSEEK_MODEL??'deepseek-flash',reasoning_effort:readAgentDefaults(root).reasoning_effort,max_tokens:readAgentDefaults(root).max_tokens,context_window:readAgentDefaults(root).context_window});
}
let app;const errors=[],consoleErrors=[],apiErrors=[];let record;
const started=Date.now();
try{
 app=await electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--project',folder,'--user-data-dir',path.join(directory,'client')],env:{...process.env,NEXARBOR_ROOT:root,NEXARBOR_MODEL_DIRECTORY:path.join(directory,'models')},timeout:60000});
 const page=await app.firstWindow();page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text());});
 page.on('response',async response=>{if(response.status()<400||!response.url().endsWith('/api'))return;try{const request=response.request().postDataJSON();apiErrors.push({operation:request.operation,status:response.status(),error:(await response.json()).error});}catch{}});
 const api=(operation,params={})=>page.evaluate(async({operation,params})=>{const token=sessionStorage.getItem('nexarbor-token'),response=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':token},body:JSON.stringify({operation,params})});const body=await response.json();if(!response.ok||body.error)throw Error(body.error);return body.value;},{operation,params});
 await page.locator('.react-flow__node').first().waitFor({timeout:60000});await page.waitForTimeout(1500);
 const count=await page.locator('.react-flow__node').count();assert.equal(count,52);
 await page.screenshot({path:path.join(directory,'town-main.png')});
 const name=page.locator('.react-flow__node').filter({has:page.locator('.node-name',{hasText:'小砾'})}).first();await name.click({force:true});
 await page.getByLabel('节点名称',{exact:true}).waitFor();assert.equal(await page.getByLabel('节点名称',{exact:true}).inputValue(),'小砾');
 await page.screenshot({path:path.join(directory,'town-inspector.png')});
 await name.click({button:'right',force:true});await page.getByRole('menuitem',{name:'咨询 Agent',exact:true}).waitFor();
 await page.getByRole('menuitem',{name:'咨询 Agent',exact:true}).click();
 await page.locator('.advisor-window,.advisor-popout,[aria-label*="咨询"]').first().waitFor({timeout:10000});
 await page.screenshot({path:path.join(directory,'town-consultation.png')});
 await page.getByRole('combobox',{name:'对话历史',exact:true}).locator('option:checked').filter({hasText:'轮'}).waitFor({state:'attached',timeout:30000});
 if(live){
  const input=page.getByRole('textbox',{name:'询问 Agent',exact:true});await input.fill('请介绍一下这个小镇网络：主要节点、模块和它们如何协作。请先使用工具查看实际网络，再根据实际内容介绍。');
  await page.getByRole('button',{name:'发送',exact:true}).click();
  const id=await page.getByRole('combobox',{name:'对话历史',exact:true}).inputValue();
  const deadline=Date.now()+15*60000;
  do{await page.waitForTimeout(3000);record=await api('advice.read',{id});await fs.writeFile(path.join(directory,'advice-progress.json'),JSON.stringify(record,null,2));if(record.job&&record.job.status!=='running')break;}while(Date.now()<deadline);
  await fs.writeFile(path.join(directory,'advice-result.json'),JSON.stringify(record,null,2));
  assert.equal(record.job?.status,'completed',record.job?.error??'Consultation not completed');
  assert.ok(record.job.tool_events.some(event=>['inspect_network','view_network','inspect_nodes','inspect_modules','read_network_text'].includes(event.tool)),'No network observation tool called');
  await page.waitForTimeout(1500);await page.getByRole('button',{name:'展开咨询页面',exact:true}).click();await page.waitForTimeout(500);
  await page.locator('.conversation-message.assistant').last().evaluate(element=>element.scrollIntoView({block:'start'}));await page.screenshot({path:path.join(directory,'town-introduction.png')});
 }
 assert.deepEqual(errors,[]);
 const result={status:'passed',actual_desktop_main:true,actual_python_backend:true,nodes:count,screenshots:['town-main.png','town-inspector.png','town-consultation.png'],errors,consoleErrors,apiErrors,elapsed_seconds:(Date.now()-started)/1000,paid_responses:live?record.job.events.length:0,...(live?{agent_requests:record.job.requests,host_requests:record.job.host_requests}:{} ),...(live?{session_id:record.session_id,tools:record.job.tool_events,usage_events:record.job.events,screenshots:['town-main.png','town-inspector.png','town-consultation.png','town-introduction.png']}:{} )};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}catch(error){
 await fs.writeFile(path.join(directory,'failure.json'),JSON.stringify({error:error.stack,errors,consoleErrors,apiErrors},null,2));
 if(app)await (await app.firstWindow()).screenshot({path:path.join(directory,'failure.png')}).catch(()=>{});throw error;
}finally{await app?.close();}
