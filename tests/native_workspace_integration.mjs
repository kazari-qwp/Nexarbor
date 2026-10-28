// Production workspace export/import, actual DSH JSONL prefix and actual core memory.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import {Bridge} from '../adapt/harness/framework/bridge.js';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';
import {WorkspaceFiles} from '../adapt/harness/studio/workspace-files.mjs';
const root=process.cwd(),directory=path.resolve(process.argv[2]);await fs.mkdir(directory,{recursive:true});let count=0,continued=false;
const server=http.createServer(async(req,res)=>{
 try{let raw='';for await(const part of req)raw+=part;const body=JSON.parse(raw);count++;
  const messages=JSON.stringify(body.messages);if(count>=3)continued||=messages.includes('PORTABLE_APPEND');
  const operation=count===1?['memory_append',{content:'PORTABLE_APPEND'}]:count===3?['memory_query',{}]:null;
  const delta=operation?{role:'assistant',tool_calls:[{index:0,id:'portable-'+count,type:'function',function:{name:operation[0],arguments:JSON.stringify(operation[1])}}]}:{role:'assistant',content:'PORTABLE_NATIVE_COMPLETE'};
  const base={id:'portable-'+count,object:'chat.completion.chunk',created:1,model:'deepseek-flash'};
  res.writeHead(200,{'Content-Type':'text/event-stream'});res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta,finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta:{},finish_reason:operation?'tool_calls':'stop'}],usage:{prompt_tokens:12,completion_tokens:12,total_tokens:24}})+'\n\n');res.end('data: [DONE]\n\n');
 }catch(error){res.writeHead(500);res.end(error.stack);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const profile={kind:'api-key',protocol:'openai-completions',base_url:'http://127.0.0.1:'+server.address().port+'/v1',api_key:'local-fixture',signature:'workspace-local',model:{model:'deepseek-flash',reasoningEfforts:{off:'none',low:'low',high:'high',max:'max'},maxTokens:16000,contextWindow:600000,compat:{supportsDeveloperRole:false,maxTokensField:'max_tokens'}}};
const opened=[];
async function start(name){
 const folder=path.join(directory,name);await fs.mkdir(path.join(folder,'temp'),{recursive:true});
 let bridge;const native=new NativeRunner(folder,(method,p)=>bridge.call(method,p,86460000),{noCredentials:true,modelResolver:async()=>profile});
 bridge=new Bridge(path.join(root,'.venv-runtime/Scripts/python.exe'),folder,['-B','-X','utf8','-m','adapt.harness.backend.server'],{NEXARBOR_STUDIO:'1'},(method,p)=>native.request(method,p));bridge.notifications.add(()=>native.notify());
 const rpc=(method,p={})=>bridge.call(method,p,86460000),workspace=new WorkspaceFiles(folder,rpc,native);
 const host={folder,bridge,native,rpc,workspace,async close(){await workspace.close();await native.close();await bridge.close();}};opened.push(host);await rpc('studio_state');return host;
}
try{
 const first=await start('source');const run=await first.rpc('executor_run',{actor:'root',text:'Append memory in the original workspace.'});assert.equal(run.status,'completed');
 const before=await first.rpc('executor_read',{actor:'root'});assert.ok(before.messages.some(item=>item.role==='tool'));
 const bundle=await first.workspace.request('workspace.export',{dirty:false,layout:{root:{x:120,y:80}},view:{selected:'root'}});assert.ok(bundle.contexts.root.events.length);assert.ok(!Object.hasOwn(bundle.document.network.nodes[0],'context_cursor'));
 assert.equal(bundle.document.files['root-memory.md'],'PORTABLE_APPEND');await fs.writeFile(path.join(directory,'portable.json'),JSON.stringify(bundle));
 const second=await start('imported');const staged=await second.workspace.request('workspace.import',{bundle});assert.ok(staged.validation.valid,JSON.stringify(staged.validation));
 const applied=await second.workspace.request('workspace.apply',staged);assert.ok(applied.valid);assert.equal(applied.commit,(await second.rpc('studio_state')).live.commit);
 const restored=await second.rpc('executor_read',{actor:'root'});assert.ok(JSON.stringify(restored.messages).includes('PORTABLE_NATIVE_COMPLETE'));
 assert.deepEqual(restored.messages,before.messages);
 const result=await second.rpc('executor_run',{actor:'root',text:'Continue using the imported native history and file.'});assert.equal(result.status,'completed');assert.ok(continued);
 assert.equal((await second.rpc('studio_state')).live.document.files['root-memory.md'],'PORTABLE_APPEND');
 const info=await second.rpc('persistence_info');assert.deepEqual(info.pending,[]);assert.deepEqual(info.executor_restore_required,{});
 const evidence={status:'passed',requests:count,paid_requests:0,exported_events:bundle.contexts.root.events.length,source_messages:before.messages.length,imported_messages:restored.messages.length,core_and_native_restored:true,continued_history:true};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
}finally{for(const host of opened.reverse())await host.close();await new Promise(resolve=>server.close(resolve));}
