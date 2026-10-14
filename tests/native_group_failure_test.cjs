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
 const link=(spec,ref)=>get(spec,ref.identifier),entry=await get(pathToFileURL(base+'/adapters/harness/framework/adapter.js').href);await entry.link(link);await entry.evaluate();
 const loop=await get(pathToFileURL(base+'/adapters/harness/runtime/agent-loop/lib/index.js').href);await loop.link(link);await loop.evaluate();
 const host=new Context(),temp=await fs.mkdtemp(path.join(testRoot,'creation-'));
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']]){await host.plugin(native(name)[service]??native(name).default);}
 host.provide('sessionTitle',{rename(){}});host.sessions.flush=async()=>{};
 await host.plugin(loop.namespace.default,{agents:[]});
 const controller=await entry.namespace.createAdapter(host,{workspace:temp,storage:path.join(temp,'.datanet'),backend:base+'/adapters/harness/runtime/backend/datanet-backend.exe',backendArgs:[],modelRoute:{provider:'mock-native',model:'native-flash'},rootNetwork:'project_root',rootToolboxes:['network_access','node_creation','agent_management','agent_delegation','interface_management','discussion'],maxSignalStrength:100});
 const llm=native('dsh-llm');
 const spill=path.join(temp,'terminal-output.txt'),full='START\n'+'line\n'.repeat(5000)+'END\n';
 await fs.writeFile(spill,full);
 host.tools.register({name:'pwsh',description:'Mock terminal result fixture',parameters:{type:'object',properties:{}},output:{schema:{type:'object'},render:()=>[{type:'text',text:'tail'}]},execute:()=>({stdout:{text:'tail',truncated:true,spillPath:spill},stderr:{text:'',truncated:false},exitCode:0})});

 class Model extends llm.LlmAdapter {
  requests=[];counts=new Map();
  async resolveModel(provider,id){return {provider,id,name:id,toolUpdate:'addition-only',systemPromptUpdate:'in-history'}}
  async *stream(options){
   this.requests.push(options);const text=options.messages.flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).join('\n');const actor=text.match(/所属节点为 (survivors\/worker_\d+)/)?.[1];
   const n=(this.counts.get(actor)??0)+1;this.counts.set(actor,n);let state=null;
   for(const m of options.messages){if(m.role==='tool')for(const b of m.content){try{const x=JSON.parse(b.text);if(x.group_id==='survivors')state=x}catch{}}}
   let call;
   if(actor&&actor!=='survivors/worker_1'&&n>1){
    const block={type:'tool-call',id:'bad-'+actor+'-'+n,name:'datanet_team_note',arguments:'{'};
    yield {type:'block-start',index:0,blockType:'tool-call'};yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'error',failure:{code:'MALFORMED_RESPONSE',message:'DeepSeek Messages stream: tool input is invalid JSON'}}};return;
   }
   if(actor&&actor!=='survivors/worker_1')call={name:'datanet_team_claim',arguments:{action:'claim',scope:'未完成-'+actor,paths:[actor.split('/')[1]+'.py']}};
   else if(actor&&state?.phase==='running'&&state.active_members?.length===1)call={name:'datanet_team_finish',arguments:{action:'propose',content:'单人接续交付完成',evidence:'原生故障隔离最小验证'}};
   else if(actor)call={name:'datanet_team_status',arguments:{}};
   const block=call?{type:'tool-call',id:'valid-'+this.requests.length,name:call.name,arguments:JSON.stringify(call.arguments)}:{type:'text',text:'已收到状态'};
   yield {type:'block-start',index:0,blockType:block.type};if(!call)yield {type:'text-delta',index:0,text:block.text};yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:call?'tool-calls':'stop'}};
  }
 }
 const model=new Model();host.llm.registerAdapter(['mock','mock-native'],model);
 const root=await host.agentLoop.create(native('dsh-session').SessionId('failure-root'),{provider:'mock',model:'mock'},{cwd:temp});await host.parallel('agent/created',{agent:root});
 const r=controller.runtimes.get(root.id);
 const exec=async(name,args={})=>{const result=await host.tools.execute({agent:root,name,arguments:args,callId:'fixture-'+name,signal:new AbortController().signal});assert.equal(result.isError,false,JSON.stringify(result));return result.value};
 await exec('datanet_create_network_channel',{preset:'decentralized_group'});
 const group=await exec('datanet_create_network',{preset:'decentralized_group',instance_id:'survivors',project:'三个成员允许故障隔离',member_count:3});
 await exec('datanet_cooperate',{group_id:'survivors',action:'start',task:'两个成员失败后由剩余成员完成',budget_minutes:1});
 let state;const deadline=Date.now()+15000;
 do{await new Promise(resolve=>setTimeout(resolve,40));state=await exec('datanet_cooperate',{group_id:'survivors',action:'status'});}while(['running','review'].includes(state.phase)&&Date.now()<deadline);
 assert.equal(state.phase,'completed',JSON.stringify(state));assert.equal(Object.keys(state.unavailable).length,2);assert.deepEqual(state.active_members,['survivors/worker_1']);
 assert.ok(Object.values(state.claims).every(c=>c.state==='released'));
 for(const member of group.members)await r.sessions.get(member).handle.agent.whenIdle();await root.whenIdle();
 for(const member of group.members.slice(1)){
  assert.ok(state.unavailable[member].reason.includes('MALFORMED_RESPONSE'),state.unavailable[member].reason);
  const events=r.sessions.get(member).handle.agent.session.snapshotEvents();assert.equal(events.filter(e=>e.type==='datanet/request-recovery').length,2);
  const corrected=model.requests.filter(req=>req.messages.some(m=>m.content.some(b=>b.type==='text'&&b.text.includes('工具：datanet_team_note'))));assert.ok(corrected.length>=2);
 }
 const notifications=root.session.deriveMessages().filter(m=>m.role==='user').map(m=>m.content.filter(b=>b.type==='text').map(b=>b.text).join('\n')).flatMap(t=>{try{return [JSON.parse(t)]}catch{return []}});
 assert.equal(notifications.filter(n=>n.type==='cooperation_degraded').length,1);assert.equal(notifications.filter(n=>n.type==='cooperation_result').length,1);
 await controller.components.dispose();await host.fiber.dispose();clearInterval(keepAlive);
 console.log('PASS native Harness + compiled Python: bounded JSON correction, original error returned, two peer losses, claims released, half-loss notification once, single survivor completed');
})().catch(error=>{console.error(error);process.exit(1)});
