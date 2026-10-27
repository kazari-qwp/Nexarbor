// Actual project, Python RPC and Harness concludeTurn; local HTTP model fixture only.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Bridge} from '../adapt/harness/framework/bridge.js';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';

const root=fileURLToPath(new URL('../',import.meta.url)),directory=path.resolve(process.argv[2]);
let bridge,native,reserved=false;
const requests=[],controls=[],finished=new Set();
const local=(operation,args={})=>bridge.call('cooperative_'+operation,args,90000);
const server=http.createServer(async(req,res)=>{
 try{
  let raw='';for await(const part of req)raw+=part;const body=JSON.parse(raw);
  const text=(body.messages??[]).flatMap(m=>typeof m.content==='string'?[m.content]:(m.content??[]).map(b=>b.text??'')).join('\n');
  const encoded=text.match(/"branch"\s*:\s*"worker-([a-f0-9]+)"/);
  assert.ok(encoded,'Expected real personal workspace in prepared context');
  const actor=Buffer.from(encoded[1],'hex').toString('utf8');
  assert.ok(requests.length<24,'Fixture request cap');
  const group=await local('status');
  const specs=body.tools.map(t=>t.function??t);
  const name=specs.find(t=>t.description.includes('datanet_team_finish')).name;
  let args,tool=name;
  if(finished.has(actor)){assert.equal(group.phase,'completed','Approved member must not poll while waiting for peers');tool=null;}
  if(tool===null){args={};}
  else if(group.phase==='running'&&!reserved){reserved=true;args={action:'propose',content:'NATIVE_CONCLUDE_DELIVERY',evidence:'local integration fixture'};}
  else if(group.phase==='review'){args={action:'approve',candidate_id:group.candidate.id,evidence:'reviewed fixed candidate'};}
  else{tool=specs.find(t=>t.description.includes('datanet_team_status')).name;args={section:'candidate'};}
  if(tool===name)finished.add(actor);
  requests.push({actor,tool,action:tool===null?'final_ack':args.action??'status'});
  const delta=tool?{role:'assistant',tool_calls:[{index:0,id:'control-'+requests.length,type:'function',function:{name:tool,arguments:JSON.stringify(args)}}]}:{role:'assistant',content:'协作已结束。'};
  const base={id:'local-'+requests.length,object:'chat.completion.chunk',created:1,model:'deepseek-flash'};
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta,finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta:{},finish_reason:tool?'tool_calls':'stop'}],usage:{prompt_tokens:8,completion_tokens:8,total_tokens:16}})+'\n\n');
  res.end('data: [DONE]\n\n');
 }catch(error){console.error(String(error));res.writeHead(500);res.end(String(error));}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const profile={kind:'api-key',protocol:'openai-completions',base_url:'http://127.0.0.1:'+server.address().port+'/v1',api_key:'local-fixture',signature:'cooperative-conclude-fixture',model:{model:'deepseek-flash',maxTokens:512,contextWindow:32000}};
try{
 native=new NativeRunner(directory,async(method,p)=>{const result=await bridge.call(method,p,90000);if(method==='executor_invoke'&&result?.format==='nexarbor-tool-control/v1'){const value={actor:p.actor,conclude:result.conclude,phase:result.data?.phase};controls.push(value);console.log(JSON.stringify(value));}return result;},{noCredentials:true,modelResolver:async()=>profile});
 bridge=new Bridge(path.join(root,'.venv-runtime/Scripts/python.exe'),directory,['-B','-X','utf8',path.join(root,'tests/cooperative_rpc_fixture.py')],{PYTHONPATH:root,NEXARBOR_APPLICATION:'discussion_collaboration'},(method,p)=>native.request(method,p));
 assert.equal((await bridge.call('state')).network.nodes.length,17);
 await local('start',{task:'原生 conclude 集成测试；验收固定候选后结束本轮。'});
 const signals=await bridge.call('signals_wait',{},90000);
 assert.ok(Object.values(signals).every(s=>s==='completed'),JSON.stringify(signals));
 const group=await local('status');assert.equal(group.phase,'completed');
 assert.equal(Object.keys(group.candidate.approvals).length,4);assert.equal(finished.size,4);
 const state=await bridge.call('state');assert.equal(state.files['data/collab/output.md'],'NATIVE_CONCLUDE_DELIVERY');
 const sessions=Object.fromEntries(Object.entries(state.agents).map(([actor,value])=>[actor,value.session_id]));
 for(const actor of finished){const chat=await bridge.call('executor_read',{actor});assert.ok(chat.messages.some(m=>m.role==='tool'));}
 await bridge.call('save',{full:true});
 const evidence={passed:true,paid_api_calls:0,http_fixture_requests:requests.length,requests,controls,actual_project_nodes:17,actual_harness_sdk:true,propose_approve_conclude:true,all_members_approved:true,output_delivered:true,sessions,signals};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
}finally{
 await native?.close();await bridge?.close();await new Promise(resolve=>server.close(resolve));
}
