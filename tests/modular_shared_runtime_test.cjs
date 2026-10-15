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
 const controller=await entry.namespace.createAdapter(host,{extensionRoot:path.join(productRoot,'extensions','multi_agent'),workspace:temp,storage:path.join(temp,'.datanet'),...(process.env.DATANET_TEST_PYTHON?{backend:process.env.DATANET_TEST_PYTHON,backendArgs:[base+'/adapters/harness/backend/server.py']}:{}),rootNetwork:'project_root',rootToolboxes:['network_access','node_creation','agent_management','agent_delegation','interface_management','discussion'],maxSignalStrength:100});
 const llm=native('dsh-llm');
 class Model extends llm.LlmAdapter {
  requests=[];
  async resolveModel(provider,id){return {provider,id,name:id,toolUpdate:'addition-only',systemPromptUpdate:'in-history'};}
  async *stream(options){
   this.requests.push(options);
   yield* [{type:'block-start',index:0,blockType:'text'},{type:'text-delta',index:0,text:'ok'},{type:'block-end',index:0,block:{type:'text',text:'ok'}},{type:'usage',usage:{inputTokens:10,outputTokens:2}},{type:'finish',reason:{kind:'stop'}}];
  }
 }
 const model=new Model();host.llm.registerAdapter(['mock'],model);
 const invariant=await get(pathToFileURL(base+'/adapters/harness/runtime/agent-loop/lib/invariant.js').href);await invariant.link(link);await invariant.evaluate();
 await host.plugin(native('dsh-invariants').InvariantRegistry);await host.plugin(invariant.namespace);
 const root=await host.agentLoop.create(native('dsh-session').SessionId('creation-root'),{provider:'mock',model:'mock'},{cwd:temp});
 await host.parallel('agent/created',{agent:root});
 const r=controller.runtimes.get(root.id);
 const exec=async(name,args={})=>{const result=await host.tools.execute({agent:root,name,arguments:args,callId:'creation-'+name,signal:new AbortController().signal});assert.equal(result.isError,false,JSON.stringify(result));return result.value};

 const send=async text=>{root.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text}]}));await root.whenIdle();};
 await exec('datanet_create_node_channel');
 for(const [id,preset] of [['q','query_text'],['r','resident_text']]){
  await exec('datanet_create_node',{child_id:id,node_spec:{preset}});
  await r.bridge.call('write',{actor:'root',target:'root/'+id,key:'content',value:id==='r'?'first':'材料正文',strength:100});
 }
 await send('turn 1');assert.equal(model.requests.length,1);assert.match(model.requests[0].messages.at(-1).content[0].text,/first$/);
 assert.ok(!JSON.stringify(root.session.deriveMessages()).includes('first'));
 await exec('write_resident_text',{content:'second'});await send('turn 2');
 assert.match(model.requests.at(-1).messages.at(-1).content[0].text,/second$/);
 assert.ok(!JSON.stringify(model.requests.at(-1).messages).includes('first'));
 assert.ok(!JSON.stringify(root.session.deriveMessages()).includes('second'));
 const snapshot=root.session.snapshotEvents().filter(e=>e.type==='datanet/request-tail').at(-1);
 assert.deepEqual(JSON.parse(JSON.stringify(snapshot.data.messages)),JSON.parse(JSON.stringify(model.requests.at(-1).messages.slice(-1))));
 const tool=host.tools.schemas(root).find(t=>t.name.startsWith('query_text_')&&t.description.includes('root/q'));assert.ok(tool);
 await exec(tool.name);await send('loaded');await exec(tool.name);await send('again');
 assert.equal(root.session.deriveMessages().filter(m=>m.source?.document==='query-text:root/q').length,1);
 const document=root.session.snapshotEvents().find(e=>e.type==='user/message'&&e.data.source?.document==='query-text:root/q');
 root.session.append('user/message',llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'项目资料摘要'}]}),{surfaceOp:{op:'replace',startSeq:document.seq,endSeq:document.seq},sourceEventSeqs:[document.seq]});
 r.instructionHistory.prune(root.ctx);assert.equal(r.instructionHistory.has(root.ctx,'query-text:root/q'),false);
 await exec(tool.name);await send('after compaction');
 assert.equal(root.session.deriveMessages().filter(m=>m.source?.document==='query-text:root/q').length,1);
 const denied=await host.tools.execute({agent:root,name:'write_resident_text',arguments:{target:'root/q',content:'denied'},callId:'denied',signal:new AbortController().signal});assert.equal(denied.isError,true);
 console.log('PASS Python + native Harness: request tail, latest-only text, snapshot reconstruction, progressive query reload and resident-only writes');
 await exec('datanet_create_agent_channel');await exec('datanet_create_agent',{child_id:'worker'});
 const delegated=await exec('datanet_call_agent',{target:'root/worker',task:'最小委托',strength:100});
 assert.equal(delegated.status,'accepted',JSON.stringify(delegated));
 const completed=await exec('datanet_wait_agent',{delegation_id:delegated.delegation_id,timeout_ms:10000});
 assert.equal(completed.status,'completed',JSON.stringify(completed));assert.match(JSON.stringify(completed.result),/ok/);
 assert.ok(r.sessions.get('root/worker').handle.agent.session.deriveMessages().some(m=>m.role==='assistant'));
 console.log('PASS duplex RPC: Python delegates while native AgentLoop forwards events; result returned and report stored');
 const schemas=host.tools.schemas(root);await r.components.disable('capabilities/text');assert.deepEqual(host.tools.schemas(root),schemas);
 const revoked=await host.tools.execute({agent:root,name:tool.name,arguments:{},callId:'revoked',signal:new AbortController().signal});assert.equal(revoked.isError,true);
 await send('component removed');assert.ok(!JSON.stringify(model.requests.at(-1).messages).includes('second'));
 console.log('PASS component removal: tool definitions retained, execution revoked and resident tail removed');
 await controller.components.dispose();await host.fiber.dispose();clearInterval(keepAlive);
})().catch(error=>{console.error(error);process.exit(1)});
