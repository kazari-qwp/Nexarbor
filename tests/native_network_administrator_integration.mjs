// Real Root tool discovery/executor -> Administrator -> MakerManager -> native DSH -> scoped commit.
// Only model responses use a local HTTP fixture; no paid API.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {startStudio} from '../adapt/harness/studio/host.mjs';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';
const root=process.cwd(),directory=path.resolve(process.argv[2]);await fs.mkdir(directory,{recursive:true});
const project=path.join(directory,'project');await fs.mkdir(path.join(project,'modules'),{recursive:true});await fs.cp(path.join(root,'projects/discussion_collaboration/modules/network_administrator'),path.join(project,'modules/network_administrator'),{recursive:true});
await fs.writeFile(path.join(project,'nexarbor.json'),JSON.stringify({format:'nexarbor-project/v2',name:'原生局部管理员验证',resources:{modules:{'network.administrator':{folder:'modules/network_administrator'}},tools:{},presets:{}},networks:{}}));
const calls=[],receipts=[];let step=0,studio;
const plan=[['skill',{name:'nexarbor-basics'}],['skill',{name:'inspect-network'}],['skill',{name:'make-network'}],['read_file',{path:'network.json'}],['edit_network',{commands:[{op:'node.create',id:'made-board',kind:'node',name:'真实组装看板'},{op:'edge.add',source:'root',target:'made-board',channels:['admin']}]}],['inspect_nodes',{source:'candidate',nodes:['made-board'],section:'summary'}]];
const server=http.createServer(async(req,res)=>{
 try{
  let raw='';for await(const chunk of req)raw+=chunk;const body=JSON.parse(raw),op=plan[step++],names=(body.tools??[]).map(tool=>tool.function.name);
  for(const forbidden of ['validate','test_environment','copy_current_network','request_component'])assert.ok(!names.includes(forbidden),forbidden+' exposed in runtime management');
  if(op)assert.ok(names.includes(op[0]),'Missing native tool '+op[0]);assert.ok(step<12,'native fixture stalled');calls.push({operation:op?.[0]??'answer',tools:names});
  const delta=op?{role:'assistant',tool_calls:[{index:0,id:'admin-'+step,type:'function',function:{name:op[0],arguments:JSON.stringify(op[1])}}]}:{role:'assistant',content:'ADMIN_NATIVE_ASSEMBLED'};
  const base={id:'admin-'+step,object:'chat.completion.chunk',created:1,model:'deepseek-flash'};res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta,finish_reason:null}]})+'\n\n');res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta:{},finish_reason:op?'tool_calls':'stop'}],usage:{prompt_tokens:12,completion_tokens:12,total_tokens:24}})+'\n\n');res.end('data: [DONE]\n\n');
 }catch(error){res.writeHead(500);res.end(error.stack);}
});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const profile={kind:'api-key',protocol:'openai-completions',base_url:'http://127.0.0.1:'+server.address().port+'/v1',api_key:'local-fixture',signature:'admin-local',model:{model:'deepseek-flash',maxTokens:16000,contextWindow:600000,compat:{supportsDeveloperRole:false,maxTokensField:'max_tokens'}}};
try{
 studio=await startStudio({directory:path.join(directory,'runtime'),projectDirectory:project,modelDirectory:path.join(directory,'models'),makerRunnerFactory:async(p,callback)=>new NativeRunner(path.join(directory,'runtime'),async(method,args)=>{const result=await callback(method,args);receipts.push({tool:args.tool,result});return result;},{noCredentials:true,modelResolver:async()=>profile,script:fileURLToPath(new URL('../adapt/harness/studio/makers/worker.cjs',import.meta.url))})});
 let state=await studio.request('state',{}),document=await studio.request('template',{kind:'network_admin',options:{id:'admin',name:'局部管理员'},document:state.live.document});
 const actor=document.network.nodes.find(node=>node.node_id==='root');actor.tables.modules.push({module_id:'tool_discovery',channels:['admin'],strength:2,channel_mode:'allow'});
 document=await studio.request('connect',{document,connection:{source:'root',target:'admin',channels:['admin'],threshold:0,multiplier:1}});
 await studio.request('apply',{document,base_commit:state.live.commit});
 const view=await studio.rpc('executor_prepare',{actor:'root'});const tool=id=>view.tools.find(item=>item.description.includes(' · '+id+' · ')).name;
 const build=await studio.rpc('executor_invoke',{actor:'root',name:tool('委托制作局部网络'),arguments:{requirement:'ADMIN_BRIDGE_NATIVE 建立看板并接线',key:'native'}});
 const deadline=Date.now()+120000;let status;
 do{status=await studio.rpc('executor_invoke',{actor:'root',name:tool('查看局部网络制作进度'),arguments:{task:build.task,wait_seconds:1}});if(status.status!=='running')break;assert.ok(Date.now()<deadline,'native maker timed out');}while(true);
 assert.equal(status.status,'completed',JSON.stringify(status));
 const applied=await studio.rpc('executor_invoke',{actor:'root',name:tool('提交局部网络变更'),arguments:{task:build.task}});assert.equal(applied.created.length,1);
 state=await studio.request('state',{});assert.equal(state.live.document.network.nodes.length,3);assert.ok(state.live.document.network.nodes.some(node=>node.name==='真实组装看板'));
 assert.ok(receipts.some(item=>item.tool==='inspect_nodes'));const work=await studio.rpc('studio_read',{id:build.workspace});assert.ok(!Object.keys(work.files).some(name=>name.startsWith('tests/')));
 const job=await studio.request('studio.agent.read',{task:build.task});assert.equal(job.runtime_management,true);assert.equal(job.validation,undefined);assert.deepEqual(job.structure_check,{valid:true});
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({status:'passed',real_native_dsh:true,actual_python_backend:true,root_executor_tools:true,local_model_requests:calls.length,paid_api_requests:0,nodes:3,workspace:build.workspace,task:build.task,tools:calls,receipts,job},null,2));console.log(JSON.stringify({status:'passed',local_requests:calls.length,nodes:3,paid_requests:0,directory}));
}finally{await studio?.close();await new Promise(resolve=>server.close(resolve));}
