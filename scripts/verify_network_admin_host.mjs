// 同一验收可用真实制作模型或确定性制作器；正式网络始终是E盘独立测试网络。
import fs from 'node:fs/promises';import path from 'node:path';import assert from 'node:assert/strict';import {fileURLToPath} from 'node:url';
import {startStudio} from '../adapters/harness/studio/host.mjs';import {editorNode} from '../adapters/harness/framework/editor-nodes.js';
const root=fileURLToPath(new URL('../',import.meta.url)),live=process.argv.includes('--live'),creation=process.argv.includes('--creation'),directory=path.join(root,'build/network-admin-'+(live?'live-':'offline-')+Date.now());await fs.mkdir(directory,{recursive:true});
const nodes=[editorNode('agent','root','全网入口'),editorNode('network_admin','admin','项目管理员'),editorNode('node','one','工作区'),editorNode('node','two','二级资料'),editorNode('node','far','范围之外'),editorNode('node','secret','私有节点')];
const edge=(source,target,channels=['admin'])=>nodes.find(n=>n.node_id===source).connections.interfaces.push({target_node_id:target,metadata:{channels,threshold:0,multiplier:1,attributes:{}}});edge('root','admin');edge('admin','one');edge('one','two');edge('two','far');edge('one','secret',['private']);
nodes[0].management_parent_id=null;nodes[1].modules['network.administrator'].config.allow_component_creation=creation;
const document={network:{version:8,nodes,signals:{},delegations:[]},files:{'data/root.md':'全网入口已有资料，请保留。'}};const initial=path.join(directory,'initial.json');await fs.writeFile(initial,JSON.stringify(document));
let callback,host;const created=new Map();let serial=0;
const factory=async(p,cb)=>{callback=cb;return {start:async()=>({ready:true}),close:async()=>{},request:async(method,p)=>{
 if(method==='create'){const session_id='offline-'+(++serial);created.set(session_id,p);return {session_id,seed_cursor:{seed:true}};}
 if(method==='read')return {steps:1};if(method==='cancel')return {ok:true};
 if(method==='run'){
  const c=created.get(p.session_id),tool=(name,args={})=>callback('maker-tool',{task:c.task,tool:name,arguments:args});
  if(c.kind!=='network'){const env=await tool('test_environment',{action:'reset',source:'current'});assert.equal(env.nodes.length,3);await tool('write_file',{path:'tests/test_module.py',content:"import unittest\nfrom pathlib import Path\nfrom datanet.studio.testing import ModuleHarness\nclass CounterIsolation(unittest.IsolatedAsyncioTestCase):\n async def test_independent_instances(self):\n  h=ModuleHarness(Path(__file__).resolve().parents[1]);h.add_node('a');h.add_node('b');h.mount('a','example.counter');h.mount('b','example.counter');a=await h.call('a','increment',{'amount':3},strength=0,channels=['demo']);b=await h.call('b','increment',{},strength=0,channels=['demo']);self.assertEqual((a['data'],b['data']),(3,1))\n"});return {status:'completed',messages:[],requests:1,steps:1,events:[],cursor:{ready:true}};}
  if(creation){assert.ok(c.tools.some(t=>t.name==='request_component'));const child=await tool('request_component',{kind:'module',name:'测试子组件',requirement:'只验证子组件的测试环境仍是局部副本'});const state=await tool('component_status',{task:child.task,wait_seconds:30});assert.equal(state.status,'completed',JSON.stringify(state));}else{assert.ok(!c.tools.some(t=>t.name==='request_component'));await assert.rejects(tool('request_component',{kind:'module',name:'禁止',requirement:'禁止'}));}
  const copied=await tool('copy_current_network');assert.equal(copied.nodes,3);
  const result=await tool('read_file',{path:'network.json',line_count:400}),doc=JSON.parse(result.text);assert.deepEqual(doc.network.nodes.map(n=>n.name).sort(),['二级资料','工作区','项目管理员'].sort());
  const env=await tool('test_environment',{action:'reset',source:'current'});assert.equal(env.nodes.length,3);
  const newNode=editorNode('node','new-board','共享看板');newNode.modules={'records.store':{config:{initial:{status:'待处理'}},state:{},access:{strength:0,channels:['records']}}};doc.network.nodes[0].connections.interfaces.push({target_node_id:newNode.node_id,metadata:{channels:['admin','records'],threshold:0,multiplier:1,attributes:{}}});
  await tool('network_patch',{nodes:[doc.network.nodes[0],newNode]});return {status:'completed',messages:[],requests:1,steps:1,events:[],cursor:{ready:true}};
 }
 throw Error(method);
}};};
host=await startStudio({directory,initialNetwork:initial,...(!live?{makerRunnerFactory:factory}:{})});
const call=(operation,args={})=>host.request('module.call',{node:'admin',module:'network.administrator',operation,arguments:args}).then(v=>{if(v.status!=='ok')throw Error(v.error);return v.data;});
try{
 const scope=await call('inspect');assert.equal(scope.document.network.nodes.length,3);assert.ok(!JSON.stringify(scope).includes('私有节点'));assert.ok(!JSON.stringify(scope).includes('范围之外'));
 if(live)await host.rpc('studio_agent_connect',{runtime:{max_requests:90,max_seconds:900}});
 const requirement='请在当前局部网络中新增一个名为“共享看板”的普通节点，装配已有的 records.store 组件，初始记录包含 status="待处理"。从 root 锚点增加一条指向它的出边，频道为 admin、records。保留现有节点、边和状态；不要生成任何组件源码。先读 reference/局部网络说明.md，检查组件配置。用独立测试环境验证新看板能够读取初始记录后完成。';
 const job=await call('build',{requirement,key:'acceptance'});console.log(JSON.stringify({directory,job,live}));let status;
 for(let n=0;n<(live?90:240);n++){status=await call('status',{task:job.task});console.log(JSON.stringify({status:status.status,phase:status.phase,steps:status.steps}));if(status.status!=='running')break;await new Promise(r=>setTimeout(r,live?10000:250));}
 assert.equal(status.status,'completed',JSON.stringify(status));const result=await call('apply',{task:job.task});assert.equal(result.created.length,1);assert.equal((await call('apply',{task:job.task})).duplicate,true);
 const state=await host.rpc('studio_state'),graph=state.live.document.network;assert.ok(graph);assert.equal(graph.nodes.length,7);assert.equal(graph.nodes.find(n=>n.node_id==='secret').name,'私有节点');assert.equal(graph.nodes.find(n=>n.node_id==='two').connections.interfaces[0].target_node_id,'far');
 const board=graph.nodes.find(n=>result.created.includes(n.node_id));assert.equal(board.name,'共享看板');assert.ok(board.modules['records.store']);
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({passed:true,live,creation,initialVisible:3,hiddenNodesPreserved:true,boundaryEdgesPreserved:true,idempotent:true,result,job,status},null,2));console.log('PASS '+directory);
 if(process.argv.includes('--serve')){console.log('URL '+host.url);await new Promise(resolve=>{process.once('SIGINT',resolve);process.once('SIGTERM',resolve);});}
}finally{await host.close();}
