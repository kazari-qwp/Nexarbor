// 独立验收真实口语制作结果，直接使用发布的配置；不调用模型。
import fs from 'node:fs/promises';import path from 'node:path';import assert from 'node:assert/strict';
import {startStudio} from '../adapters/harness/studio/host.mjs';
const directory=path.resolve(process.argv[2]??'build/makers-wish-lab'),host=await startStudio({directory});
try{
 const before=(await host.rpc('studio_state')).live.document,library=await host.request('catalog',{});assert.ok(library.modules['messages.box']);
 const entries=(await fs.readdir(directory)).filter(f=>f.startsWith('suite-')).sort(),suite=JSON.parse(await fs.readFile(path.join(directory,entries.at(-1)),'utf8'));
 const env=(id,p)=>host.rpc('studio_environment',{id,...p}),results=[];
 for(const r of suite.results){
  assert.equal(r.status,'completed');assert.equal(r.release.kind,'component-presets');const preset=r.release.presets[0];assert.equal(preset.module,'messages.box');
  await env(r.workspace,{action:'reset'});const privateBox=preset.config.read_policy==='self',target=privateBox?'bob':'square';
  assert.equal((await env(r.workspace,{action:'mount',node:target,module:preset.module,config:preset.config,access:{strength:2,channels:['chat','records']}})).ok,true);
  const call=(actor,node,operation,args={})=>env(r.workspace,{action:'call',actor,node,module:preset.module,operation,arguments:args,strength:2,channels:['chat']});
  let value=await call('alice',target,'send',{text:'独立验收消息',key:'same'});assert.equal(value.result.status,'ok');value=await call('alice',target,'send',{text:'独立验收消息',key:'same'});assert.equal(value.result.data.duplicate,true);
  value=await env(r.workspace,{action:'call',actor:'alice',node:'alice',module:'records.store',operation:'read',arguments:{},strength:0,channels:['records']});assert.equal(value.result.data.values.ap,privateBox?2:3);
  value=await call('bob',target,'read');assert.equal(value.result.data.messages.length,1);
  if(privateBox){value=await call('alice',target,'read');assert.equal(value.result.status,'error');value=await call('cara',target,'send',{text:'跨房间'});assert.equal(value.ok,false);assert.equal(value.error_type,'PermissionError');}
  else {value=await call('alice',target,'read');assert.equal(value.result.status,'ok');assert.equal(preset.config.max_messages,50);}
  results.push({name:r.name,workspace:r.workspace,preset:preset.name,passed:true,requests:r.requests,source_session:r.source_session,environment_attempts:r.environment_attempts});
 }
 assert.deepEqual((await host.rpc('studio_state')).live.document,before);assert.equal(suite.results[1].source_session,suite.results[0].session_id);
 const evidence={passed:true,model_calls_in_verification:0,formal_network_unchanged:true,second_input_forked_from_seed:true,results};await fs.writeFile(path.join(directory,'independent-verification.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
}finally{await host.close();}
