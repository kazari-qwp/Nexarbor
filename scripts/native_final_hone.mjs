import readAgentDefaults from '../adapt/harness/framework/agent-defaults.cjs';
// Original two-node bootstrap and preset task through the real project host.
import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
import {startStudio} from '../adapt/harness/studio/host.mjs';
import {Project} from '../adapt/harness/studio/project.mjs';
import {ModelConnections} from '../adapt/harness/studio/model-connections.mjs';
import {nativeUsage} from './native_usage.mjs';
const root=process.cwd(),folder=path.resolve(process.argv[2]),live=process.argv.includes('--live'),spec=JSON.parse(await fs.readFile(path.join(folder,'spec.json'),'utf8'));
assert.ok(folder.startsWith(path.join(root,'build')+path.sep));
const report={model:process.env.DEEPSEEK_MODEL??'deepseek-flash',real_api:live,initial_input_count:1,bootstrap_nodes:2,prebuilt_team:false,started:Date.now(),turns:[],notifications:[],errors:[]};
const save=()=>fs.writeFile(path.join(folder,'root-evidence.json'),JSON.stringify(report,null,2));
let host,timer,busy=false,stopReason;
const project=new Project(spec.project,spec.runtime);await project.initialize();
if(live){assert.ok(process.env.DEEPSEEK_API_KEY);const models=new ModelConnections({project,configDirectory:path.join(folder,'model-config')});const connection=await models.save({name:'DeepSeek应用验收',provider:'DeepSeek',protocol:'openai-completions',base_url:process.env.DEEPSEEK_BASE_URL??'https://api.deepseek.com',models:[report.model],api_key:process.env.DEEPSEEK_API_KEY});for(const scope of ['project','network','component'])await models.choose(scope,{connection:connection.id,model:report.model,reasoning_effort:readAgentDefaults(root).reasoning_effort,max_tokens:readAgentDefaults(root).max_tokens,context_window:readAgentDefaults(root).context_window});}
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const baseline=JSON.parse(await fs.readFile(path.join(root,'docs/migration/evidence/2026-10-28-hone-original-baseline.json'),'utf8'));
async function progress(){
 if(busy||!host)return;busy=true;try{
  const state=await host.rpc('studio_state'),usage=await nativeUsage(spec.runtime),makers=await host.rpc('studio_agent_status');
  const signals=Object.values(state.live.signals??{}),summary={elapsed_seconds:(Date.now()-report.started)/1000,nodes:state.live.document.network.nodes.length,active_signals:signals.filter(s=>['running','queued'].includes(s.status)).length,groups:state.live.document.network.nodes.flatMap(n=>n.tables.modules.filter(m=>['discussion.group','collaboration.group'].includes(m.module_id)).map(m=>({node:n.node_id,module:m.module_id,phase:m.state?.group?.phase??m.state?.session?.status}))),makers:makers.jobs.map(j=>({id:j.id,status:j.status,phase:j.phase,requests:j.requests,tool:j.tool_events?.at(-1)?.tool})),responses:usage.responses,usage:usage.usage};
  await fs.writeFile(path.join(folder,'progress.json'),JSON.stringify(summary,null,2));await fs.appendFile(path.join(folder,'progress.jsonl'),JSON.stringify(summary)+'\n');console.log(JSON.stringify({progress:summary}));
  if(live&&(usage.usage.totalTokens>baseline.usage.totalTokens*2||summary.elapsed_seconds>baseline.elapsed_seconds*2)){stopReason='明显超出原任务时间或token基线的两倍，停止付费测试并保留断点';report.anomaly={reason:stopReason,summary,baseline};await save();await host.close();}
 }catch(error){report.monitor_error=error.message;}finally{busy=false;}
}
async function run(text,kind){const result=await host.rpc('executor_run',{actor:'root',text});report.turns.push({kind,...result});await save();console.log(JSON.stringify({turn:kind,status:result.status,steps:result.steps,requests:result.requests}));assert.equal(result.status,'completed');}
try{
 host=await startStudio({directory:spec.runtime,projectDirectory:spec.project,modelDirectory:path.join(folder,'model-config'),onModelSelection:row=>fs.appendFile(path.join(folder,'models.jsonl'),JSON.stringify(row)+'\n')});
 await host.request('catalog',{official:true});const state=await host.rpc('studio_state');assert.equal(state.live.document.network.nodes.length,2);await fs.writeFile(path.join(folder,'initial-state.json'),JSON.stringify(state,null,2));
 const tools=await host.rpc('executor_prepare',{actor:'root'});assert.ok(tools.tools.some(t=>t.description.includes('委托制作局部网络')));assert.ok(tools.tools.some(t=>t.description.includes(' · datanet_discuss · ')));
 const presets=await host.request('catalog',{});assert.ok(presets.localResources.presets);report.preflight={passed:true,nodes:2,tools:tools.tools.length};await save();
 if(!live){report.status='preflight-passed';}
 else{
  timer=setInterval(()=>void progress(),20000);await run(spec.request,'original-user-request');
  const notified=new Set();
  for(let notice=0;notice<=2;notice++){
   let active=false,sawWork=false,stable=0,jobs=[];
   do{const current=await host.rpc('studio_state'),makers=await host.rpc('studio_agent_status');jobs=makers.jobs;active=jobs.some(j=>j.status==='running')||Object.values(current.live.signals??{}).some(s=>['queued','running'].includes(s.status));sawWork||=active;stable=active?0:stable+1;if(stable<2)await pause(15000);}while(stable<2&&!stopReason);
   if(stopReason)throw Error(stopReason);const finished=jobs.filter(j=>!notified.has(j.id));if(notice===2||!sawWork&&!finished.length)break;for(const job of jobs)notified.add(job.id);report.notifications.push({at:Date.now(),kind:'background-settled',jobs:jobs.map(j=>({id:j.id,status:j.status}))});await run('你发起的后台工作已有进展，当前已结束运行。请自行查看真实状态、成果与未完成事项，继续处理原请求。','original-driver-progress');
  }
  await host.rpc('signals_wait');await host.rpc('save',{full:true});const final=await host.rpc('studio_state');await fs.writeFile(path.join(folder,'final-state.json'),JSON.stringify(final,null,2));
  for(const node of final.live.document.network.nodes.filter(n=>n.type==='agent'))await fs.writeFile(path.join(folder,'transcript-'+Buffer.from(node.node_id).toString('hex')+'.json'),JSON.stringify(await host.rpc('executor_read',{actor:node.node_id}),null,2));
  const portable=await host.request('workspace.export',{});await fs.writeFile(path.join(folder,'final-network.json'),JSON.stringify(portable));await host.request('workspace.commit',{message:'应用一真实运行后的网络与原生会话'});
  report.status='recorded-awaiting-independent-artifact-and-protocol-acceptance';
 }
}catch(error){report.status=stopReason?'stopped-for-performance-review':'failed';report.errors.push(String(error.stack??error));process.exitCode=1;}
finally{clearInterval(timer);report.finished=Date.now();await host?.close();report.actual_usage=await nativeUsage(spec.runtime);report.elapsed_seconds=(report.finished-report.started)/1000;await save();console.log(JSON.stringify({status:report.status,elapsed_seconds:report.elapsed_seconds,responses:report.actual_usage.responses,usage:report.actual_usage.usage,directory:folder}));}
