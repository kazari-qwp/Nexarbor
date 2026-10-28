import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';
import defaults from '../adapt/harness/framework/agent-defaults.cjs';

const directory=path.resolve(process.argv[2]);await fs.mkdir(path.join(directory,'temp'),{recursive:true});
const calls=[],bindings={},requestEvents=[];let native,latest,generation=1;
const server=http.createServer(async(req,res)=>{
 let raw='';for await(const part of req)raw+=part;const body=JSON.parse(raw);calls.push(body);
 assert.equal(body.reasoning_effort,'high');
 const last=body.messages.at(-1);const seed=calls.length===1;
 const delta={role:'assistant',reasoning_content:seed?'Original private reasoning must retain its field.':'Continue with the same reasoning representation.',...(seed?{tool_calls:[{index:0,id:'fixture-call',type:'function',function:{name:'echo',arguments:'{"value":"fixture"}'}}]}:{content:'DONE'})};
 const base={id:'fixture-'+calls.length,object:'chat.completion.chunk',created:1,model:'deepseek-flash'};
 res.writeHead(200,{'Content-Type':'text/event-stream'});
 res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta,finish_reason:null}]})+'\n\n');
 res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta:{},finish_reason:seed?'tool_calls':'stop'}],usage:{prompt_tokens:100,completion_tokens:10,total_tokens:110}})+'\n\n');res.end('data: [DONE]\n\n');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const profile=()=>({kind:'api-key',id:'resume-fixture',protocol:'openai-completions',base_url:'http://127.0.0.1:'+server.address().port+'/v1',api_key:'fake',signature:'generation-'+generation,model:{model:'deepseek-flash',reasoningEfforts:{off:'none',low:'low',high:'high',max:'max'},compat:{supportsDeveloperRole:false,thinkingFormat:'deepseek',supportsReasoningEffort:true,requiresReasoningContentOnAssistantMessages:true,maxTokensField:'max_tokens'},reasoningEffort:defaults().reasoning_effort,maxTokens:generation===1?16000:20000,contextWindow:600000}});
async function callback(method,p){
 if(method==='executor_prepare')return {tools:[{name:'echo',description:'Fixture',parameters:{type:'object',additionalProperties:false,required:['value'],properties:{value:{type:'string'}}}}],retained_tools:[],context:[],inputs:[],tail:[]};
 if(method==='executor_request'){requestEvents.push({...p});return {ok:true};}
 if(method==='executor_invoke')return p.arguments;
 if(method==='executor_bind'){bindings[p.actor]={...p};return {ok:true};}
 if(method==='executor_prune')return [];
 if(method==='persistence_info')return {commit_id:0,bindings:Object.fromEntries(Object.entries(bindings).map(([a,b])=>[a,b.session_id])),pending:[]};
 if(method==='persistence_latest_point')return latest;
 if(method==='persistence_checkpoint')return latest={...p,id:'fixture-point'};
 throw Error('Unexpected callback '+method);
}
const start=()=>native=new NativeRunner(directory,callback,{noCredentials:true,modelResolver:async()=>profile()});
async function run(message){const r=await native.request('agent-run',{...bindings.actor,actor:'actor',name:'Fixture',message});assert.equal(r.status,'completed',r.error);return r;}
function assertPreserved(before,after){
 assert.deepEqual(after.messages.slice(0,before.messages.length),before.messages,'Earlier input remains an exact prefix');
 const original=after.messages.find(m=>m.role==='assistant'&&m.tool_calls?.some(c=>c.function.name==='echo'));
 assert.equal(original.reasoning_content,'Original private reasoning must retain its field.');assert.ok(!original.content?.includes('Original private reasoning'));
 assert.deepEqual(after.tools,before.tools);
}
try{
 start();await run('SEED');const stale=(await native.request('agent-context-capture',{bindings:{actor:bindings.actor.session_id}})).actor;await run('BEFORE_REOPEN');bindings.actor.context_cursor=stale;const before=calls.at(-1),id=bindings.actor.session_id;
 await native.close();start();await run('AFTER_REOPEN');assert.equal(bindings.actor.session_id,id);assertPreserved(before,calls.at(-1));
 const reopened=calls.at(-1);generation=2;await run('AFTER_PARAMETER_CHANGE');assertPreserved(reopened,calls.at(-1));assert.equal(calls.at(-1).max_tokens,20000);
 assert.equal(requestEvents.length,calls.length);assert.ok(requestEvents.every(e=>e.executor_session_id&&e.request_index>=1));
 const report={passed:true,paid_api_calls:0,actual_harness_sdk:true,default_reasoning_effort:defaults().reasoning_effort,request_limit:defaults().max_requests,model_requests:calls.length,request_events:requestEvents.length,cold_reopen_preserves_prefix:true,stale_saved_cursor_preserves_later_native_progress:true,generation_change_preserves_reasoning:true};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await fs.writeFile(path.join(directory,'requests.json'),JSON.stringify(calls,null,2));await native?.close();await new Promise(resolve=>server.close(resolve));}
