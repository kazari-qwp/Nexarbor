// Actual Advisors and MakerManager → stdio Studio RPC → current core → native DSH.
// Only model responses are local fixtures; no paid API requests.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Bridge} from '../adapt/harness/framework/bridge.js';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';
import {MakerManager} from '../adapt/harness/studio/makers/manager.mjs';
import {Advisors} from '../adapt/harness/studio/makers/advisors.mjs';
import {Project} from '../adapt/harness/studio/project.mjs';
const root=process.cwd(),directory=path.resolve(process.argv[2]);await fs.mkdir(path.join(directory,'temp'),{recursive:true});
const projectDirectory=path.join(directory,'project');await fs.cp(path.join(root,'resources/examples/npc-town'),projectDirectory,{recursive:true});
const calls=[],counts=new Map(),receipts=[];let makers,advisors;
const testSource=`import unittest
from pathlib import Path
from app.studio.testing import ModuleHarness
class Example(unittest.IsolatedAsyncioTestCase):
    async def test_counter(self):
        h=ModuleHarness(Path(__file__).resolve().parents[1])
        try:
            h.add_node('counter');h.mount('counter')
            self.assertEqual((await h.call('counter','increment',{'amount':4}))['data'],4)
        finally:await h.close()
`;
const text=message=>typeof message?.content==='string'?message.content:(message?.content??[]).map(block=>block.text??'').join('');
const server=http.createServer(async(req,res)=>{
 try{
  let raw='';for await(const chunk of req)raw+=chunk;const body=JSON.parse(raw);
  const marker=text(body.messages.findLast(message=>message.role==='user'&&/ADVICE_(network|component|resume)/.test(text(message)))).match(/ADVICE_(network|component|resume)/)?.[1];assert.ok(marker);
  const step=counts.get(marker)??0;counts.set(marker,step+1);assert.ok(step<16);
  const sequence=marker==='network'?[['skill',{name:'nexarbor-basics'}],['skill',{name:'inspect-network'}],['view_network',{nodes:['小砾'],hops:1,image:false}],['inspect_nodes',{nodes:['小砾'],section:'modules'}],['read_network_text',{nodes:['世界时间']}]]:
   marker==='component'?[['skill',{name:'nexarbor-basics'}],['skill',{name:'inspect-network'}],['inspect_modules',{modules:['movement.here']}],['read_resource',{module:'movement.here',file:'module.py',line_count:20}],['skill',{name:'make-components'}],['list_files',{}],['write_file',{path:'README.md',content:'# 实际制作咨询副本\n\n保留真实计数器行为。\n'}],['write_file',{path:'tests/test_counter.py',content:testSource}],['validate',{}]]:
   [['read_network_text',{nodes:['世界时间']}]];
  const op=sequence[step],names=(body.tools??[]).map(tool=>tool.function.name);if(op)assert.ok(names.includes(op[0]),op[0]+' missing from native tools');
  calls.push({marker,step,tools:names,operation:op?.[0]});
  if(step&&['network','resume'].includes(marker))assert.ok(body.messages.some(m=>m.role==='tool'));
  const delta=op?{role:'assistant',tool_calls:[{index:0,id:'advice-'+calls.length,type:'function',function:{name:op[0],arguments:JSON.stringify(op[1])}}]}:{role:'assistant',content:'ADVICE_'+marker+'_OK'};
  const base={id:'advice-'+calls.length,object:'chat.completion.chunk',created:1,model:'deepseek-flash'};
  res.writeHead(200,{'Content-Type':'text/event-stream'});res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta,finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta:{},finish_reason:op?'tool_calls':'stop'}],usage:{prompt_tokens:12,completion_tokens:12,total_tokens:24}})+'\n\n');res.end('data: [DONE]\n\n');
 }catch(error){res.writeHead(500);res.end(error.stack);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const profile={kind:'api-key',protocol:'openai-completions',base_url:'http://127.0.0.1:'+server.address().port+'/v1',api_key:'local-fixture',signature:'advisors-local',model:{model:'deepseek-flash',maxTokens:16000,contextWindow:600000,compat:{supportsDeveloperRole:false,maxTokensField:'max_tokens'}}};
const bridge=new Bridge(path.join(root,'.venv-runtime/Scripts/python.exe'),directory,['-B','-X','utf8','-m','adapt.harness.backend.server'],{NEXARBOR_STUDIO:'1',NEXARBOR_APPLICATION:'npc_town',NEXARBOR_PROJECT_DIRECTORY:projectDirectory},()=>{throw Error('unexpected business model/tool execution')});
const rpc=(method,args={})=>bridge.call(method,args,86460000);
const project=new Project(projectDirectory,directory,rpc);await project.initialize();
const start=async()=>{
 makers=new MakerManager(directory,rpc,{runnerFactory:async(p,callback)=>new NativeRunner(directory,async(method,args)=>{const result=await callback(method,args);receipts.push({tool:args.tool,result});return result;},{noCredentials:true,modelResolver:async()=>profile,script:fileURLToPath(new URL('../adapt/harness/studio/makers/worker.cjs',import.meta.url))})});
 makers.project=project;await makers.initialize();advisors=new Advisors(directory,rpc,makers,async()=>({tools:[]}));makers.advisor=advisors;
};
async function finished(id){const until=Date.now()+180000;for(;;){const record=await advisors.read({id});if(record.job.status!=='running'){assert.equal(record.job.status,'completed',JSON.stringify(record.job));return record;}assert.ok(Date.now()<until,'local fixture stalled');await new Promise(resolve=>setTimeout(resolve,50));}}
try{
 const initial=await rpc('studio_state');await start();
 const resident=initial.live.document.network.nodes.find(node=>node.name==='小砾');
 const network=await advisors.open({role:'network',newConversation:true,selection:{nodes:[resident.node_id]}});assert.equal(network.snapshot.nodes,52);
 await advisors.send({id:network.id,text:'ADVICE_network'});const answered=await finished(network.id);
 assert.ok(JSON.stringify(answered.job.messages).includes('ADVICE_network_OK'));
 const nodeReceipt=receipts.find(item=>item.tool==='inspect_nodes');assert.ok(nodeReceipt.result.nodes[0].modules.some(item=>item.id==='tool_discovery'));
 assert.ok(receipts.find(item=>item.tool==='read_network_text').result.nodes[0].text.length>0);
 const component=await advisors.open({role:'component',newConversation:true});await advisors.send({id:component.id,text:'ADVICE_component'});const created=await finished(component.id);
 assert.ok(created.workspace);const work=await rpc('studio_read',{id:created.workspace});assert.match(work.files['README.md'],/实际制作咨询副本/);
 assert.equal(receipts.find(item=>item.tool==='validate').result.status,'passed');
 const session=answered.session_id;await makers.close();await start();
 const reopened=await advisors.open({id:network.id,role:'network'});assert.equal(reopened.session_id,session);
 await advisors.send({id:network.id,text:'ADVICE_resume'});const resumed=await finished(network.id);assert.equal(resumed.session_id,session);
 const actual=await rpc('studio_state');assert.equal(actual.live.document.network.nodes.length,52);
 const archived=(await project.conversations('advice',{id:network.id,prefix:true}))[0];assert.ok(archived.portablePrefix.events.length);assert.ok(JSON.stringify(archived.job.messages).includes('ADVICE_resume_OK'));
 assert.ok((await project.workFiles(created.work))['tests/test_counter.py']);
 const result={status:'passed',paid_requests:0,requests:calls.length,network_session:session,component_workspace:created.workspace,cold_resume:true,project_git:true,portable_native_history:true,roles:['network','component'],calls,tools:receipts.map(item=>item.tool)};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({...result,calls:undefined}));
}finally{await makers?.close();await bridge.close();server.close();}
