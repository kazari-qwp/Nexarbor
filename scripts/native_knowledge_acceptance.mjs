// Original knowledge tasks against the actual project host; model calls require --live.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {startStudio} from '../adapt/harness/studio/host.mjs';
import {Project} from '../adapt/harness/studio/project.mjs';
import {ModelConnections} from '../adapt/harness/studio/model-connections.mjs';
import {nativeUsage} from './native_usage.mjs';
const root=process.cwd(),folder=path.resolve(process.argv[2]),live=process.argv.includes('--live'),resuming=process.argv.includes('--resume');
assert.ok(folder.startsWith(path.join(root,'build')+path.sep));
const spec=JSON.parse(await fs.readFile(path.join(folder,'spec.json'),'utf8'));
const baseline=JSON.parse(await fs.readFile(spec.baseline,'utf8'));
const previous=resuming?JSON.parse(await fs.readFile(path.join(folder,'knowledge-evidence.json'),'utf8')):null;
const report=previous??{model:spec.model,reasoning_effort:'high',max_tokens:50000,request_limit:10000,real_api:live,started:Date.now(),phases:[],errors:[],feedback_messages:0,restarted:false};
const completed=new Set(report.phases.filter(p=>p.status==='completed').map(p=>p.phase));
const resumePhase=[1,2,3,4,5,6,7,8].find(n=>!completed.has(n));
let priorPartial=report.partial_phase_stats??null;
if(resuming){
 if(report.errors?.length)(report.resume_failures??=[]).push({at:Date.now(),status:report.status,errors:report.errors,responses:report.usage?.responses});
 report.resume_started=Date.now();report.errors=[];report.status='resuming';delete report.partial_phase;
 if(report.anomaly){
  const current=report.anomaly.current;
  if(current.tokens)priorPartial={phase:current.phase,elapsed_seconds:current.elapsed_seconds,responses:current.responses,tokens:current.tokens};
  else {const audit=JSON.parse(await fs.readFile(path.join(folder,'phase3-model-latency-audit.json'),'utf8'));priorPartial={phase:audit.phase,elapsed_seconds:audit.elapsed_seconds,responses:audit.model_responses,tokens:Object.fromEntries(['inputTokens','outputTokens','cacheReadTokens','cacheWriteTokens','totalTokens'].map(k=>[k,audit.model_rows.reduce((sum,row)=>sum+(row.usage[k]??0),0)]))};}
  report.partial_phase_stats=priorPartial;
  (report.reviewed_anomalies??=[]).push({...report.anomaly,decision:'用户确认全量回归后从断点继续',decision_at:Date.now()});delete report.anomaly;
 }
 if(!priorPartial&&report.reviewed_anomalies?.at(-1)?.current.phase===resumePhase){const audit=JSON.parse(await fs.readFile(path.join(folder,'phase3-model-latency-audit.json'),'utf8'));priorPartial={phase:audit.phase,elapsed_seconds:audit.elapsed_seconds,responses:audit.model_responses,tokens:Object.fromEntries(['inputTokens','outputTokens','cacheReadTokens','cacheWriteTokens','totalTokens'].map(k=>[k,audit.model_rows.reduce((sum,row)=>sum+(row.usage[k]??0),0)]))};report.partial_phase_stats=priorPartial;}
}
const save=(name,value)=>fs.writeFile(path.join(folder,name),JSON.stringify(value,null,2));
const persist=()=>save('knowledge-evidence.json',report);
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const hash=v=>createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');
let host,timer,busy=false,phaseStarted,phaseNumber,usageBefore={responses:0,usage:{}},stopReason;
const project=new Project(spec.project,spec.runtime);await project.initialize();
if(live&&!resuming){
 assert.ok(process.env.DEEPSEEK_API_KEY,'Missing authorized DeepSeek API credential');
 const models=new ModelConnections({project,configDirectory:path.join(folder,'model-config')});
 const connection=await models.save({name:'DeepSeek资料库验收',provider:'DeepSeek',protocol:'openai-completions',base_url:process.env.DEEPSEEK_BASE_URL??'https://api.deepseek.com',models:[spec.model],api_key:process.env.DEEPSEEK_API_KEY});
 for(const scope of ['project','network','component'])await models.choose(scope,{connection:connection.id,model:spec.model,reasoning_effort:'high',max_tokens:50000,context_window:600000});
}
async function start(){
 await fs.mkdir(spec.runtime,{recursive:true});
 await fs.writeFile(path.join(spec.runtime,'native-model.json'),JSON.stringify({max_requests:10000,max_seconds:86400,official_timeout_seconds:86400}));
 return startStudio({directory:spec.runtime,projectDirectory:spec.project,modelDirectory:path.join(folder,'model-config'),onModelSelection:row=>fs.appendFile(path.join(folder,'models.jsonl'),JSON.stringify({at:new Date().toISOString(),...row})+'\n')});
}
function knowledgeImage(state){
 const doc=state.live.document,nodes=doc.network.nodes.filter(n=>['knowledge_collection','knowledge_catalog'].includes(n.type));
 const roots=nodes.map(n=>n.data.path.replaceAll('\\','/').replace(/\/$/,''));
 return {nodes,files:Object.fromEntries(Object.entries(doc.files).filter(([file])=>roots.some(base=>file===base||file.startsWith(base+'/'))))};
}
async function progress(){
 if(busy||!host||!phaseStarted)return;busy=true;
 try{
  const pause=await fs.readFile(path.join(folder,'pause-request.txt'),'utf8').catch(e=>{if(e.code==='ENOENT')return null;throw e;});
  if(pause){stopReason=pause;report.status='paused';report.pause_reason=pause;await persist();await host.close();host=null;return;}
  const usage=await nativeUsage(spec.runtime),elapsed=(Date.now()-phaseStarted)/1000;
  const tokens=usage.usage.totalTokens-(usageBefore.usage.totalTokens??0);
  const old=baseline.phases.find(p=>p.phase===phaseNumber);
  const row={at:Date.now(),phase:phaseNumber,elapsed_seconds:elapsed,responses:usage.responses-usageBefore.responses,phase_total_tokens:tokens,tokens:Object.fromEntries(Object.keys(usage.usage).map(k=>[k,usage.usage[k]-(usageBefore.usage[k]??0)])),usage:usage.usage};
  await save('progress.json',row);await fs.appendFile(path.join(folder,'progress.jsonl'),JSON.stringify(row)+'\n');console.log(JSON.stringify({progress:row}));
  if(old&&(elapsed>old.wall_seconds*2||tokens>old.tokens.totalTokens*2)){
   stopReason='资料库本阶段时间或token超过相同旧任务基线两倍，停止付费调用并保留断点';report.anomaly={reason:stopReason,current:row,baseline:old};report.status='paused-for-performance-review';await persist();await host.close();host=null;
  }
 }catch(error){report.monitor_error=error.message;}finally{busy=false;}
}
async function phase(number,{readonly=false}={}){
 phaseNumber=number;phaseStarted=Date.now();report.active_phase=number;usageBefore=await nativeUsage(spec.runtime);
 const before=await host.request('state',{resume:false});await save('phase-'+number+(resuming&&number===resumePhase?'-resume-before':'-before')+'.json',before.live);
 const continued=resuming&&number===resumePhase;
 const text=continued?'继续本阶段中断的任务。沿用已完成的入库、来源更新和核对，只补齐尚未完成的收尾与交付，不重复导入已经完成的批次。':await fs.readFile(path.join(folder,'tasks','phase-'+number+'.txt'),'utf8');
 let result;
 try{result=await host.rpc('executor_run',{actor:'root',text:(number<=6?'本次工作区：'+path.join(spec.runtime,'workspace')+'。以下路径均相对这个工作区。\n\n':'')+text});}
 catch(error){await save('phase-'+number+'-error.json',{message:error.message,stack:error.stack});throw error;}
 const finished=Date.now(),started=phaseStarted,elapsed=(finished-started)/1000;phaseStarted=null;
 const after=await host.request('state',{resume:false}),transcript=await host.rpc('executor_read',{actor:'root'}),usage=await nativeUsage(spec.runtime);
 await save('phase-'+number+'-after.json',after.live);await save('phase-'+number+'-transcript.json',transcript);
 await fs.writeFile(path.join(folder,'phase-'+number+'-response.md'),result.output??'');
 const row={phase:number,started,finished,status:result.status,elapsed_seconds:elapsed,steps:result.steps,requests:result.requests,readonly,knowledge_image_changed:readonly?hash(knowledgeImage(before))!==hash(knowledgeImage(after)):null,responses:usage.responses-usageBefore.responses,tokens:Object.fromEntries(Object.keys(usage.usage).map(k=>[k,usage.usage[k]-(usageBefore.usage[k]??0)]))};
 if(priorPartial?.phase===number){row.continuation_seconds=elapsed;row.elapsed_seconds+=priorPartial.elapsed_seconds;row.responses+=priorPartial.responses;for(const k in row.tokens)row.tokens[k]+=priorPartial.tokens[k];row.prior_interrupted_attempt=priorPartial;priorPartial=null;delete report.partial_phase_stats;}
 completed.add(number);report.active_phase=null;report.phases.push(row);if(number>6)report.feedback_messages++;await persist();console.log(JSON.stringify({phase:row}));
 assert.equal(result.status,'completed');if(readonly)assert.equal(row.knowledge_image_changed,false,'Read-only phase modified knowledge');
}
try{
 host=await start();await host.request('catalog',{official:true});
 const initial=await host.request('state',{resume:false});if(!resuming)assert.equal(initial.live.document.network.nodes.length,4);assert.deepEqual(initial.moduleProblems,{});
 const prepared=await host.rpc('executor_prepare',{actor:'root'});assert.ok(prepared.tools.some(t=>t.description.includes('kb_ingest')));assert.ok(prepared.tools.some(t=>t.name==='memory_query'));assert.ok(prepared.system_prompt);
 if(!resuming)await save('initial-state.json',initial.live);else await save('resume-state.json',initial.live);report.preflight={passed:true,nodes:initial.live.document.network.nodes.length,tools:prepared.tools.length};await persist();
 if(!live)report.status='preflight-passed';
 else{
  timer=setInterval(()=>void progress(),20000);
  if(!completed.has(1))await phase(1);
  if(!completed.has(2))await phase(2,{readonly:true});
  if(!completed.has(3)){await fs.cp(path.join(folder,'held-out-updates'),path.join(spec.runtime,'workspace/imports/updates'),{recursive:true});await phase(3);}
  if(!completed.has(4))await phase(4,{readonly:true});
  if(!report.restarted){
   await host.rpc('save',{full:true});const before=await host.request('state',{resume:false});await save('before-restart.json',before.live);
   await host.close();host=null;host=await start();await host.request('catalog',{official:true});
   const after=await host.request('state',{resume:false});await save('after-restart.json',after.live);
   report.restarted=true;report.checkpoint_knowledge_image_equal=hash(knowledgeImage(before))===hash(knowledgeImage(after));
   report.session_before=before.live.sessions.root?.session_id;report.session_after=after.live.sessions.root?.session_id;
   assert.equal(report.checkpoint_knowledge_image_equal,true);assert.equal(report.session_before,report.session_after);
  }
  if(!completed.has(5))await phase(5,{readonly:true});
  if(!completed.has(6))await phase(6,{readonly:true});
  if(!completed.has(7))await phase(7);
  if(!completed.has(8))await phase(8);
  if(process.argv.includes('--repair-closeout')&&!completed.has(9))await phase(9);
  if(process.argv.includes('--finalize-sources')&&!completed.has(10))await phase(10);
  await host.request('workspace.commit',{message:'保存资料库原六阶段和两次收尾实测成果'});report.status='awaiting-independent-acceptance';
 }
}catch(error){if(!stopReason)report.status='failed';report.errors.push(error.stack);process.exitCode=1;}
finally{clearInterval(timer);report.finished=Date.now();report.usage=await nativeUsage(spec.runtime);await persist();await host?.close();}
