// Original town graph and business modules, real Harness SDK, real DeepSeek API.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {Bridge} from '../adapt/harness/framework/bridge.js';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';
import readAgentDefaults from '../adapt/harness/framework/agent-defaults.cjs';

const root=fileURLToPath(new URL('../',import.meta.url)),directory=path.resolve(process.argv[2]);
const days=Number(process.argv[3]??5),ticks=days*5;assert.ok(Number.isInteger(days)&&days>=1&&days<=5);
let currentCycle=0;
const key=process.env.DEEPSEEK_API_KEY,base=(process.env.DEEPSEEK_BASE_URL??'https://api.deepseek.com').replace(/\/$/,''),model=process.env.DEEPSEEK_MODEL??'deepseek-flash';
if(!key)throw Error('Missing configured DeepSeek API key');
const redact=value=>String(value?.stack??value).split(key).join('[已隐藏密钥]');
let requests=0;const calls=[];
const gateway=http.createServer(async(req,res)=>{
 const upstreamAbort=new AbortController();res.once('close',()=>upstreamAbort.abort());
 let upstream;
 try{
  let raw='';for await(const part of req)raw+=part;
  const id=++requests;
  if(id>1000*days+20){res.writeHead(429,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'Acceptance API request budget exceeded'}}));return;}
  const start=Date.now(),url=base+req.url.replace(/^\/v1/,'');
  console.log(JSON.stringify({stage:'api_start',request:id}));
  upstream=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+key},body:raw,signal:upstreamAbort.signal,redirect:'error'});
  const entry={request:id,cycle:currentCycle,status:upstream.status};calls.push(entry);
  res.writeHead(upstream.status,{'Content-Type':upstream.headers.get('content-type')??'application/json'});
  if(upstream.ok){
   const decoder=new TextDecoder();let pending='';
   for await(const chunk of upstream.body){
    res.write(chunk);pending+=decoder.decode(chunk,{stream:true});
    let newline;while((newline=pending.indexOf('\n'))>=0){
     const line=pending.slice(0,newline).trim();pending=pending.slice(newline+1);
     if(!line.startsWith('data:')||line.slice(5).trim()==='[DONE]')continue;
     try{const value=JSON.parse(line.slice(5));if(value.usage){const u=value.usage;entry.usage={input:u.prompt_tokens??0,output:u.completion_tokens??0,total:u.total_tokens??0,cached:u.prompt_cache_hit_tokens??u.prompt_tokens_details?.cached_tokens??0};}}catch{}
    }
   }
  }
  else res.write(redact(await upstream.text()));
  res.end();entry.elapsed_ms=Date.now()-start;
  console.log(JSON.stringify({stage:'api_end',...entry}));
 }catch(error){if(!res.headersSent)res.writeHead(502,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:redact(error)}}));}
});
await new Promise(resolve=>gateway.listen(0,'127.0.0.1',resolve));
const signature=crypto.createHash('sha256').update('newcore-town:'+base+':'+model+':'+JSON.stringify({...readAgentDefaults(root),max_tokens:16000,reasoning_effort:'low'})).digest('hex');
const profile={kind:'api-key',protocol:'openai-completions',base_url:'http://127.0.0.1:'+gateway.address().port+'/v1',api_key:'acceptance-proxy',signature,
 model:{model,reasoningEfforts:{off:'none',low:'low',high:'high',max:'max'},compat:{thinkingFormat:'deepseek',supportsReasoningEffort:true,requiresReasoningContentOnAssistantMessages:true,maxTokensField:'max_tokens'},reasoningEffort:'low',maxTokens:16000,contextWindow:readAgentDefaults(root).context_window}};
let bridge,native;
const evidence={mode:'town',directory,started:new Date().toISOString(),cycles:[],days:[],requested_days:days,requested_ticks:ticks,model,model_config:profile.model,source:'converted original npc-town project',real_api:true,api_calls:calls};
let resume=null,priorCalls=[],previousCalls=[];
try{resume=JSON.parse(await fs.readFile(path.join(directory,'resume-source.json'),'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
if(resume){
 const previous=JSON.parse(await fs.readFile(path.join(resume.directory,'verification.json'),'utf8'));
 evidence.cycles=previous.cycles.filter(c=>c.cycle<=resume.completed_tick&&c.report.status==='completed');
 assert.equal(evidence.cycles.length,resume.completed_tick);evidence.days=previous.days.filter(d=>d.day*5<=resume.completed_tick);
 previousCalls=previous.api_calls;priorCalls=previousCalls.filter(c=>c.cycle<=resume.completed_tick);
 evidence.resume=resume;evidence.previous_attempt={requests:previous.requests,error:previous.error,completed_tick:resume.completed_tick,abandoned_usage:null};
 evidence.prior_api_calls=priorCalls;
}
const save=async()=>fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));
const usage=rows=>rows.reduce((sum,row)=>{for(const key of ['input','output','total','cached'])sum[key]+=row.usage?.[key]??0;return sum;},{input:0,output:0,total:0,cached:0});
async function start(){
 native=new NativeRunner(directory,(method,p)=>bridge.call(method,p,86460000),{noCredentials:true,modelResolver:async()=>profile});
 bridge=new Bridge(path.join(root,'.venv-runtime/Scripts/python.exe'),directory,['-B','-X','utf8','-m','adapt.harness.backend.server'],
  {PYTHONPATH:root,NEXARBOR_APPLICATION:'npc_town'},(method,p)=>native.request(method,p));
 bridge.notifications.add(()=>native.notify());
}
async function stop(){await native?.close();await bridge?.close();native=null;bridge=null;}
const moduleState=(state,id)=>state.network.nodes.map(node=>({node,module:node.tables.modules.find(module=>module.module_id===id)})).filter(item=>item.module);
try{
 await start();const initial=await bridge.call('state');
 await fs.writeFile(path.join(directory,resume?'continuation-initial-state.json':'initial-state.json'),JSON.stringify(initial,null,2));
 const pulse=initial.network.nodes.find(node=>node.type==='pulse');assert.ok(pulse);
 const clock=moduleState(initial,'clock.counter')[0];assert.ok(clock);const startTick=clock.module.state.tick??0;
 const actors=initial.network.nodes.filter(node=>node.type==='agent').map(node=>node.node_id);assert.equal(actors.length,7);evidence.actors=actors;evidence.initial_nodes=initial.network.nodes.length;
 assert.equal(startTick,resume?.completed_tick??0);assert.ok(startTick<ticks);
 if(resume)evidence.previous_attempt.abandoned_usage=usage(previousCalls.filter(c=>c.cycle>startTick));
 for(let cycle=startTick+1;cycle<=ticks;cycle++){
  currentCycle=cycle;const cycleStarted=Date.now(),firstRequest=calls.length;
  console.log(JSON.stringify({stage:'cycle_start',cycle}));
  const report=await bridge.call('pulse_run',{node_id:pulse.node_id,cycles:1,timeout_seconds:86400},86460000);
  const selected=calls.slice(firstRequest);
  evidence.cycles.push({cycle,report,elapsed_ms:Date.now()-cycleStarted,requests:selected.length,usage:usage(selected)});
  if(cycle%5===0){const selectedCycles=evidence.cycles.slice(-5),result={day:cycle/5,elapsed_ms:selectedCycles.reduce((n,c)=>n+c.elapsed_ms,0),requests:selectedCycles.reduce((n,c)=>n+c.requests,0),usage:usage([...priorCalls,...calls].filter(c=>c.cycle>cycle-5&&c.cycle<=cycle))};evidence.days.push(result);console.log(JSON.stringify({stage:'day_end',...result}));}
  await save();
  console.log(JSON.stringify({stage:'cycle_end',cycle,status:report.status,deliveries:report.reports?.[0]?.deliveries.map(d=>({node:d.node_id,status:d.status,error:d.error}))}));
  assert.equal(report.status,'completed',JSON.stringify(report));
  const info=await bridge.call('persistence_info');
  const contexts=await native.request('agent-context-capture',{bindings:info.bindings,requireIdle:true});
  const point=await bridge.call('persistence_checkpoint',{contexts,bindings:info.bindings,expected_commit:info.commit_id,kind:'full'});
  evidence.cycles.at(-1).checkpoint=point.id;await save();
 }
 let state=await bridge.call('state');const finalClock=moduleState(state,'clock.counter')[0].module.state;
 assert.equal(finalClock.tick,ticks);evidence.final_tick=finalClock.tick;evidence.completed_cycles=ticks;
 evidence.final_actors=state.network.nodes.filter(node=>node.type==='agent').map(node=>node.node_id);
 currentCycle=ticks+1;
 const actor=actors[0],marker='迁移验收记忆：今天的行动以真实账户记录为准。';
 await bridge.call('module_call',{node_id:actor,module_id:'agents.memory',operation:'remember',arguments:{text:marker,key:'native-acceptance'}});
 await bridge.call('save',{full:true});const before=await bridge.call('state');evidence.sessions_before=Object.fromEntries(Object.entries(before.agents).map(([id,value])=>[id,value.session_id]));
 await stop();await start();const after=await bridge.call('state');
 for(const [id,value]of Object.entries(evidence.sessions_before))assert.equal(after.agents[id]?.session_id,value);
 const memories=await bridge.call('module_call',{node_id:actor,module_id:'agents.memory',operation:'recall',arguments:{query:'迁移验收记忆'}});assert.equal(memories.count,1);
 const continued=await bridge.call('executor_run',{actor,text:'请回忆保存的“迁移验收记忆”，并结合当前现场，用一句话说明你的位置和记忆内容。本轮不要移动或交易。'},86460000);
 assert.equal(continued.status,'completed');assert.equal(continued.session_id,evidence.sessions_before[actor]);
 evidence.continued={actor,status:continued.status,session_id:continued.session_id,output:continued.output};
 for(const id of actors){const chat=await bridge.call('executor_read',{actor:id});await fs.writeFile(path.join(directory,'transcript-'+id+'.json'),JSON.stringify(chat,null,2));}
 await fs.writeFile(path.join(directory,'final-state.json'),JSON.stringify(await bridge.call('state'),null,2));
 evidence.observed_usage=usage([...priorCalls,...calls]);evidence.all_attempts_usage=usage([...previousCalls,...calls]);evidence.requests_with_usage=calls.filter(c=>c.usage).length;
 evidence.reopened=true;evidence.same_sessions=true;evidence.passed=true;evidence.requests=requests;evidence.requests_all_attempts=requests+(evidence.previous_attempt?.requests??0);evidence.finished=new Date().toISOString();await save();
 console.log(JSON.stringify({passed:true,directory,completed_cycles:ticks,final_tick:finalClock.tick,requests,reopened:true}));
}catch(error){evidence.passed=false;evidence.requests=requests;evidence.error=redact(error);await save();console.error(evidence.error);process.exitCode=1;}
finally{await stop();await new Promise(resolve=>gateway.close(resolve));}
