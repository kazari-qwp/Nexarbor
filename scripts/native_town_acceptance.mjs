// Original town graph and business modules, real Harness SDK, real DeepSeek API.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {Bridge} from '../adapt/harness/framework/bridge.js';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';

const root=fileURLToPath(new URL('../',import.meta.url)),directory=path.resolve(process.argv[2]);
const key=process.env.DEEPSEEK_API_KEY,base=(process.env.DEEPSEEK_BASE_URL??'https://api.deepseek.com').replace(/\/$/,''),model=process.env.DEEPSEEK_MODEL??'deepseek-flash';
if(!key)throw Error('Missing configured DeepSeek API key');
const redact=value=>String(value?.stack??value).split(key).join('[已隐藏密钥]');
let requests=0;const calls=[];
const gateway=http.createServer(async(req,res)=>{
 let upstream;
 try{
  let raw='';for await(const part of req)raw+=part;
  const id=++requests;
  if(id>360){res.writeHead(429,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'Acceptance API request budget exceeded'}}));return;}
  const start=Date.now(),url=base+req.url.replace(/^\/v1/,'');
  console.log(JSON.stringify({stage:'api_start',request:id}));
  upstream=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+key},body:raw,signal:AbortSignal.timeout(180000),redirect:'error'});
  const entry={request:id,status:upstream.status};calls.push(entry);
  res.writeHead(upstream.status,{'Content-Type':upstream.headers.get('content-type')??'application/json'});
  if(upstream.ok){for await(const chunk of upstream.body)res.write(chunk);}
  else res.write(redact(await upstream.text()));
  res.end();entry.elapsed_ms=Date.now()-start;
  console.log(JSON.stringify({stage:'api_end',...entry}));
 }catch(error){if(!res.headersSent)res.writeHead(502,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:redact(error)}}));}
});
await new Promise(resolve=>gateway.listen(0,'127.0.0.1',resolve));
const signature=crypto.createHash('sha256').update('newcore-town:'+base+':'+model).digest('hex');
const profile={kind:'api-key',protocol:'openai-completions',base_url:'http://127.0.0.1:'+gateway.address().port+'/v1',api_key:'acceptance-proxy',signature,
 model:{model,maxTokens:10000,contextWindow:128000}};
let bridge,native;
const evidence={mode:'town',directory,started:new Date().toISOString(),cycles:[],model,source:'converted original npc-town project',real_api:true,api_calls:calls};
const save=async()=>fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));
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
 const pulse=initial.network.nodes.find(node=>node.type==='pulse');assert.ok(pulse);
 const clock=moduleState(initial,'clock.counter')[0];assert.ok(clock);const startTick=clock.module.state.tick??0;
 const actors=initial.network.nodes.filter(node=>node.type==='agent').map(node=>node.node_id);assert.equal(actors.length,7);evidence.actors=actors;evidence.initial_nodes=initial.network.nodes.length;
 for(let cycle=1;cycle<=5;cycle++){
  console.log(JSON.stringify({stage:'cycle_start',cycle}));
  const report=await bridge.call('pulse_run',{node_id:pulse.node_id,cycles:1,timeout_seconds:86400},86460000);
  evidence.cycles.push({cycle,report});await save();
  console.log(JSON.stringify({stage:'cycle_end',cycle,status:report.status,deliveries:report.reports?.[0]?.deliveries.map(d=>({node:d.node_id,status:d.status,error:d.error}))}));
  assert.equal(report.status,'completed',JSON.stringify(report));
 }
 let state=await bridge.call('state');const finalClock=moduleState(state,'clock.counter')[0].module.state;
 assert.equal(finalClock.tick,startTick+5);evidence.final_tick=finalClock.tick;evidence.completed_cycles=5;
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
 evidence.reopened=true;evidence.same_sessions=true;evidence.passed=true;evidence.requests=requests;evidence.finished=new Date().toISOString();await save();
 console.log(JSON.stringify({passed:true,directory,completed_cycles:5,final_tick:finalClock.tick,requests,reopened:true}));
}catch(error){evidence.passed=false;evidence.requests=requests;evidence.error=redact(error);await save();console.error(evidence.error);process.exitCode=1;}
finally{await stop();await new Promise(resolve=>gateway.close(resolve));}
