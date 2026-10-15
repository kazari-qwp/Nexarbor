const keepAlive=setInterval(()=>{},1000);setTimeout(()=>{console.error('Test deadline');process.exit(1)},60000).unref();
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL,fileURLToPath}=require('node:url');
const nativeRoot=process.env.DATANET_NATIVE_MODULES??path.join(process.env.LOCALAPPDATA,'Programs','DeepSeek Harness','resources','app.asar','dsh','node_modules');
const productRoot=path.resolve(__dirname,'..');
const testRoot=process.env.DATANET_TEST_TEMP??path.join(productRoot,'build','test-data');
require('node:fs').mkdirSync(testRoot,{recursive:true});
const native=name=>require(path.join(nativeRoot,'@deepseek-ai',name)),{Context}=native('cordis');
const base=productRoot;
(async()=>{
 const cache=new Map(),context=vm.createContext({process,console,Buffer,URL,AbortController,AbortSignal,structuredClone,setTimeout,clearTimeout,setInterval,clearInterval,Symbol});
 const synthetic=(ns,id)=>{const keys=[...new Set([...Object.keys(ns),'default'])];return new vm.SyntheticModule(keys,function(){for(const key of keys)this.setExport(key,key==='default'?(ns.default??ns):ns[key])},{context,identifier:id})};
 async function get(spec,parent){
  const file=spec.startsWith('file:')?fileURLToPath(spec):spec.startsWith('.')?path.resolve(path.dirname(fileURLToPath(parent)),spec):null,key=file??spec;if(cache.has(key))return cache.get(key);
  if(file?.replaceAll('\\','/').endsWith('framework/capabilities.js')){const mod=synthetic({applyCapabilities:async()=>({officialPreset:'standard'}),updateCapabilityTools:()=>({})},key);cache.set(key,mod);return mod;}
  if(!file){const ns=spec.startsWith('@deepseek-ai/')?native(spec.slice(13)):spec==='zod'?require(path.join(nativeRoot,'zod')):await import(spec);const mod=synthetic(ns,key);cache.set(key,mod);return mod;}
  const mod=new vm.SourceTextModule(await fs.readFile(file,'utf8'),{context,identifier:pathToFileURL(file).href,initializeImportMeta:m=>m.url=pathToFileURL(file).href,importModuleDynamically:async(spec,ref)=>{const m=await get(spec,ref.identifier);if(m.status==='unlinked')await m.link(link);if(m.status==='linked')await m.evaluate();return m}});cache.set(key,mod);return mod;
 }
 const link=(spec,ref)=>get(spec,ref.identifier),entry=await get(pathToFileURL(base+'/index.js').href);await entry.link(link);await entry.evaluate();
 const loop=await get(pathToFileURL(base+'/adapters/harness/runtime/agent-loop/lib/index.js').href);await loop.link(link);await loop.evaluate();
 const host=new Context(),temp=await fs.mkdtemp(path.join(testRoot,'creation-'));
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']]){await host.plugin(native(name)[service]??native(name).default);}
 host.provide('sessionTitle',{rename(){}});
 await host.plugin(native('dsh-session-persistence-jsonl').default,{root:path.join(temp,'session-logs'),compression:'none'});
 await host.plugin(loop.namespace.default,{agents:[]});
 const r=await entry.namespace.apply(host,{workspace:temp,storage:path.join(temp,'.datanet'),...(process.env.DATANET_TEST_PYTHON?{backend:process.env.DATANET_TEST_PYTHON,backendArgs:[base+'/adapters/harness/backend/server.py']}:{}),rootNetwork:'project_root',rootToolboxes:['network_access','node_creation','agent_management','interface_management','discussion'],maxSignalStrength:100});
 const root=await host.agentLoop.create(native('dsh-session').SessionId('creation-root'),{provider:'mock',model:'mock'},{cwd:temp});
 await host.parallel('agent/created',{agent:root});
 const exec=async(name,args={})=>{const result=await host.tools.execute({agent:root,name,arguments:args,callId:'creation-'+name,signal:new AbortController().signal});assert.equal(result.isError,false,JSON.stringify(result));return result.value};
 await exec('datanet_create_agent_channel');const worker=await exec('datanet_create_agent',{child_id:'worker'});
 await exec('datanet_create_network_channel',{preset:'discussion_group'});
 const group=await exec('datanet_create_network',{preset:'discussion_group',instance_id:'members',project:'创建验证',rounds:1,with_agents:true});
 const runtime=host.datanetComponents;
 assert.equal(group.status,'ok');
 const agents=host.agents.list();assert.equal(agents.length,7);assert.equal(new Set(agents.map(a=>a.session.id)).size,7);assert.equal(new Set(agents.map(a=>a.ctx)).size,7);
 const discussionAgents=agents.filter(agent=>host.tools.schemas(agent).some(t=>t.name==='submit_round'));
 assert.equal(discussionAgents.length,5);
 for(const agent of discussionAgents){const tools=host.tools.schemas(agent);assert.ok(tools.some(t=>t.name==='datanet_memory_read'));assert.ok(tools.some(t=>t.name==='datanet_memory_write'));assert.ok(!tools.some(t=>t.name==='datanet_send_message'));}
 const before=agents.find(agent=>agent.id===worker.session_id);
 const memoryWrite=await host.tools.execute({agent:before,name:'datanet_memory_write',arguments:{content:'native retained memory'},callId:'memory',signal:new AbortController().signal});assert.equal(memoryWrite.isError,false,JSON.stringify(memoryWrite));
 await exec('datanet_interfaces_channel');
 const pending=await exec('datanet_interfaces',{action:'remove',arguments:{direction:'both',target_node_id:worker.node_id}});
 await exec('datanet_interfaces',{action:'remove',arguments:{confirmation_id:pending.confirmation_id,choice:2}});
 assert.ok(!host.agents.list().some(agent=>agent.id===worker.session_id));
 await exec('datanet_interfaces',{action:'add',arguments:{direction:'read',target_node_id:worker.node_id}});
 const restored=host.agents.list().find(agent=>agent.id===worker.session_id);assert.ok(restored);assert.notEqual(restored.ctx,before.ctx);
 const memoryRead=await host.tools.execute({agent:restored,name:'datanet_memory_read',arguments:{},callId:'memory-restored',signal:new AbortController().signal});assert.equal(memoryRead.value.content,'native retained memory');
 const other=await host.agentLoop.create(native('dsh-session').SessionId('another-root'),{provider:'mock',model:'mock'},{cwd:temp});
 await host.parallel('agent/created',{agent:other});
 const execOther=async(name,args={})=>{const result=await host.tools.execute({agent:other,name,arguments:args,callId:'second-'+name,signal:new AbortController().signal});assert.equal(result.isError,false,JSON.stringify(result));return result.value};
 await execOther('datanet_create_agent_channel');const secondWorker=await execOther('datanet_create_agent',{child_id:'worker'});
 assert.notEqual(worker.session_id,secondWorker.session_id);
 assert.equal((await fs.readdir(path.join(temp,'.datanet/networks'))).length,2);
 await runtime.dispose();await host.fiber.dispose();clearInterval(keepAlive);console.log('PASS native AgentRegistry: independent Agent contexts, automatic memory tools, and isolated root networks; no model calls');
})().catch(error=>{console.error(error);process.exit(1)});
