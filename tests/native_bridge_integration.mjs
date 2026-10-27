// Real production Python RPC + Harness SDK and JSONL; only HTTP model replies are local fixtures.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Bridge} from '../adapt/harness/framework/bridge.js';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';

const root=fileURLToPath(new URL('../',import.meta.url)),directory=path.resolve(process.argv[2]);
let count=0,querySeen=false,appendSeen=false,restoredSeen=false;
const server=http.createServer(async(req,res)=>{
 try{
  let raw='';for await(const part of req)raw+=part;const body=JSON.parse(raw);count++;
  const messages=JSON.stringify(body.messages??[]);
  querySeen||=messages.includes('RPC_ORIGINAL');appendSeen||=(body.messages??[]).some(m=>m.role==='tool'&&String(m.content).includes('"root":11'));
  if(count>=4)restoredSeen||=messages.includes('RPC_ORIGINAL RPC_APPEND');
  const name=count===1||count===4?'memory_query':count===2?'memory_append':null;
  const args=name==='memory_append'?{content:' RPC_APPEND'}:{};
  const delta=name?{role:'assistant',tool_calls:[{index:0,id:'rpc_'+count,type:'function',function:{name,arguments:JSON.stringify(args)}}]}:{role:'assistant',content:'RPC_NATIVE_COMPLETE'};
  const base={id:'local-'+count,object:'chat.completion.chunk',created:1,model:'deepseek-flash'};
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta,finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta:{},finish_reason:name?'tool_calls':'stop'}],usage:{prompt_tokens:8,completion_tokens:8,total_tokens:16}})+'\n\n');
  res.end('data: [DONE]\n\n');
 }catch(error){res.writeHead(500);res.end(String(error));}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const profile={kind:'api-key',protocol:'openai-completions',base_url:'http://127.0.0.1:'+server.address().port+'/v1',api_key:'local-fixture-only',signature:'native-bridge-integration',model:{model:'deepseek-flash',maxTokens:512,contextWindow:32000}};
let bridge,native;
async function start(){
 native=new NativeRunner(directory,(method,p)=>bridge.call(method,p,90000),{noCredentials:true,modelResolver:async()=>profile});
 bridge=new Bridge(path.join(root,'.venv-runtime/Scripts/python.exe'),directory,['-B','-X','utf8','-m','adapt.harness.backend.server'],{PYTHONPATH:root},(method,p)=>native.request(method,p));
 bridge.notifications.add(()=>native.notify());
 return bridge;
}
async function stop(){await native?.close();await bridge?.close();native=null;bridge=null;}
try{
 await start();
 const first=await bridge.call('executor_run',{actor:'root',text:'Run memory query, append, and return result.'},90000);
 assert.equal(first.status,'completed');assert.equal(first.output,'RPC_NATIVE_COMPLETE');
 let state=await bridge.call('state');assert.equal(state.files['root-memory.md'],'RPC_ORIGINAL RPC_APPEND');
 const points=await bridge.call('persistence_points');assert.ok(points.length);assert.ok(points.at(-1).contexts.root.prefix_hash);
 const before=await bridge.call('executor_read',{actor:'root'});
 assert.ok(before.messages.some(m=>m.role==='tool'));assert.ok(querySeen);assert.ok(appendSeen);
 await stop();await start();
 const second=await bridge.call('executor_run',{actor:'root',text:'Read the persisted memory again.'},90000);
 assert.equal(second.status,'completed');assert.equal(second.session_id,first.session_id);assert.ok(restoredSeen);
 state=await bridge.call('state');assert.equal(state.files['root-memory.md'],'RPC_ORIGINAL RPC_APPEND');
 const after=await bridge.call('executor_read',{actor:'root'});assert.ok(after.messages.length>before.messages.length);
 const info=await bridge.call('persistence_info');assert.deepEqual(info.pending,[]);
 assert.deepEqual(info.executor_restore_required,{});
 const evidence={passed:true,paid_api_calls:0,http_fixture_requests:count,session_reused:true,continued_turn:true,memory_file_updated:true,
   original_jsonrpc:true,original_native_runner:true,native_jsonl_cursors:true,recovery_points:(await bridge.call('persistence_points')).length};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
}finally{await stop();await new Promise(resolve=>server.close(resolve));}
