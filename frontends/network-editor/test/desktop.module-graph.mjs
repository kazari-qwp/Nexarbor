import {_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {startStudio} from '../../../adapters/harness/studio/host.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),directory=path.join(root,'build/module-graph-'+Date.now());
await fs.mkdir(directory,{recursive:true});const host=await startStudio({directory});let client;
try{
 const catalog=await host.rpc('studio_catalog');expect(catalog.library['modules.executor']).toBeTruthy();
 const initial=await host.rpc('studio_state'),document=structuredClone(initial.live.document),actor=document.network.nodes.find(n=>n.node_id==='root');
 const link=(target,channels)=>({target_node_id:target,metadata:{channels,threshold:0,multiplier:1,attributes:{}}});
 const node=(id,type,parameters={})=>({type,node_id:id,name:id,description:'',management_parent_id:'root',divergence:-1,data_kind:null,parameters,connections:{interfaces:[]},agent:null,modules:{},offered_tools:[],toolboxes:[],expose:[],execution:null,inputs:null});
 const tools=node('tools','node');tools.offered_tools=[{ref:'harness:read',channels:['tools']}];
 const pulse=node('clock','pulse',{channels:['workflow'],strength:2});pulse.connections.interfaces=[link('root',['workflow'])];
 actor.connections.interfaces=[link('tools',['tools']),link('clock',['workflow'])];
 actor.modules['tools.collector']={config:{},state:{},access:{strength:1,channels:['tools']}};
 const step=(id,operation,arguments_)=>({type:'call',id,operation,arguments:arguments_});
 actor.modules['modules.executor']={state:{},access:{strength:1,channels:['tools']},config:{
  operations:{catalog:{module:'tools.collector',operation:'collect'},read:{module:'tools.collector',operation:'invoke'}},
  graphs:{main:{type:'sequence',steps:[step('catalog','catalog',{}),{type:'branch',select:{$ref:'/results/catalog/value/status'},
   cases:{ok:step('read','read',{tool_id:{$ref:'/event/input/tool_id'},arguments:{file_path:'graph-probe.txt'}})},default:{type:'sequence',steps:[]}}]}},
  default_graph:'main',signal_channels:['workflow'],on_signal:[{graph:'main',kind:'pulse'}],timeout_seconds:30}};
 document.network.nodes.push(tools,pulse);document.files['graph-probe.txt']='LangGraph module workflow completed';
 await host.rpc('studio_apply',{document,base_commit:initial.live.commit,layout:{root:{x:0,y:0},tools:{x:230,y:0},clock:{x:0,y:180}}});
 const collected=await host.rpc('module_access',{node:'root',module:'tools.collector',operation:'collect'}),toolId=collected.data[0].id;
 const direct=await host.rpc('module_access',{node:'root',module:'modules.executor',operation:'run',arguments:{input:{tool_id:toolId}}});
 expect(direct.data.executions[0].results.read.value.data.isError).toBe(false);
 expect(JSON.stringify(direct)).toContain('LangGraph module workflow completed');
 const latest=await host.rpc('studio_state');latest.live.document.network.nodes.find(n=>n.node_id==='clock').parameters.content={tool_id:toolId};
 await host.rpc('studio_apply',{document:latest.live.document,base_commit:latest.live.commit,layout:{}});
 const wave=await host.rpc('studio_pulse',{pulse:'clock',cycles:1,timeout_seconds:30});
 expect(wave.report.status).toBe('completed');
 expect(JSON.stringify(wave.report)).toContain('LangGraph module workflow completed');
 const fork=await host.rpc('studio_fork',{module:'modules.executor'});
 let validation=await host.rpc('studio_validate',{id:fork.id});
 const deadline=Date.now()+20000;
 while(validation.status==='running'&&Date.now()<deadline){await new Promise(resolve=>setTimeout(resolve,200));validation=await host.rpc('studio_job',{job:validation.id});}
 expect(validation.status,validation.log).toBe('passed');
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
 client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--connection',path.join(directory,'editor-connection.json'),'--user-data-dir='+path.join(directory,'desktop-profile')],env});
 const page=await client.firstWindow(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await expect(page.getByRole('button',{name:'组件工作室',exact:true})).toBeVisible({timeout:20000});
 await page.locator('.react-flow__node[data-id="root"]').click();
 await page.getByRole('button',{name:'模块',exact:true}).click();
 const section=page.locator('.module-section').filter({has:page.locator('summary span small').filter({hasText:'modules.executor'})});
 await section.locator(':scope > summary').click();
 await section.locator('summary').filter({hasText:'可视化执行图'}).click();
 await expect(section.getByLabel('执行块类型').first()).toBeVisible();
 expect(errors).toEqual([]);await page.screenshot({path:path.join(directory,'module-graph.png')});
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({passed:true,backend:'langgraph',callEntry:true,signalEntry:true,pulseReturnsAfterGraph:true,realHarnessRead:true,desktopGraphEditor:true,validationWorker:true,modelCalls:0,errors},null,2));
 console.log('PASS module graph native tools + pulse + desktop:',directory);
}finally{if(client)await client.close();await host.close();}
