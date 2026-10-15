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
 const link=(spec,ref)=>get(spec,ref.identifier),entry=await get(pathToFileURL(base+'/extensions/knowledge_base/capabilities/knowledge_agents/entry.js').href);await entry.link(link);await entry.evaluate();
 const loop=await get(pathToFileURL(base+'/adapters/harness/runtime/agent-loop/lib/index.js').href);await loop.link(link);await loop.evaluate();
 const host=new Context(),temp=await fs.mkdtemp(path.join(testRoot,'creation-'));
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']]){await host.plugin(native(name)[service]??native(name).default);}
 host.provide('sessionTitle',{rename(){}});host.sessions.flush=async()=>{};
 await host.plugin(loop.namespace.default,{agents:[]});
 const controller=await entry.namespace.apply(host,{workspace:temp,storage:path.join(temp,'.datanet'),...(process.env.DATANET_TEST_PYTHON?{backend:process.env.DATANET_TEST_PYTHON,backendArgs:[base+'/adapters/harness/backend/server.py']}:{}),maxSignalStrength:100});

 const llm=native('dsh-llm');
 class Model extends llm.LlmAdapter {
  requests=[];
  async resolveModel(provider,id){return {provider,id,name:id,toolUpdate:'addition-only',systemPromptUpdate:'in-history'};}
  async *stream(options){
   this.requests.push(options);
   const all=options.messages.flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).join('\n');
   const calls=options.messages.filter(m=>m.role==='assistant').flatMap(m=>m.content.filter(b=>b.type==='tool-call'));
   const values=options.messages.filter(m=>m.role==='tool').flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>{try{return JSON.parse(b.text)}catch{return null}})).filter(Boolean);
   const last=calls.at(-1)?.name;
   let call;
   if(all.includes('你是主 Agent 创建的任务助手')){
    const source=all.match(/sourceRecord=([a-f0-9]{32})/)?.[1];
    if(!last)call={name:'task_document_read',arguments:{}};
    else if(last==='task_document_read')call={name:'kb_fetch',arguments:{id:source}};
    else if(last==='kb_fetch')call={name:'kb_create_node',arguments:{name:'People Wiki',storage:'wiki'}};
    else if(last==='kb_create_node')call={name:'kb_store',arguments:{collection:values.findLast(v=>v.storage==='wiki').id,content:'Alice is 30. [[wanted-page]]',sources:[source]}};
    else if(last==='kb_store'){
      const stored=values.findLast(v=>v.version&&v.id),original=values.find(v=>v.content?.name==='Alice');
      call={name:'task_document_write',arguments:{content:'Alice knowledge task complete',sources:[{node_id:original.node_id,locator:source,version:1}],receipts:[stored]}};
    }else if(last==='task_document_write'){
      const reply=all.match(/"reply_tool":\s*"(datanet_reply_[a-f0-9]+)"/)?.[1];
      call={name:reply,arguments:{content:'Delivery: '+values.find(v=>v.result_id).result_id}};
    }
   }
   const block=call?{type:'tool-call',id:'kb-'+this.requests.length,name:call.name,arguments:JSON.stringify(call.arguments)}:{type:'text',text:'Knowledge task acknowledged'};
   yield {type:'block-start',index:0,blockType:block.type};
   if(!call)yield {type:'text-delta',index:0,text:block.text};
   yield {type:'block-end',index:0,block};
   yield {type:'usage',usage:{inputTokens:10,outputTokens:2}};
   yield {type:'finish',reason:{kind:'stop'}};
  }
 }
 const model=new Model();host.llm.registerAdapter(['mock'],model);
 const invariant=await get(pathToFileURL(base+'/adapters/harness/runtime/agent-loop/lib/invariant.js').href);await invariant.link(link);await invariant.evaluate();
 await host.plugin(native('dsh-invariants').InvariantRegistry);await host.plugin(invariant.namespace);
 const root=await host.agentLoop.create(native('dsh-session').SessionId('knowledge-root'),{provider:'mock',model:'mock'},{cwd:temp});
 await host.parallel('agent/created',{agent:root});
 const r=controller.runtimes.get(root.id);
 const exec=async(name,args={})=>{const result=await host.tools.execute({agent:root,name,arguments:args,callId:'kb-'+name,signal:new AbortController().signal});assert.equal(result.isError,false,JSON.stringify(result));return result.value};
 const intake=await exec('kb_ingest',{content:{name:'Alice',age:30}});
 assert.equal(intake.status,'pending');
 assert.equal(r.sessions.size,0,'the main Agent should perform ordinary work itself');
 const table=await exec('kb_create_node',{name:'People',storage:'sqlite',schema:{name:'string',age:'integer'}});
 const saved=await exec('kb_store',{collection:table.id,intake_id:intake.intake_id});
 const requests=model.requests.length;
 const found=await exec('kb_search',{query:'Alice'});assert.equal(found.total,1);
 const fetched=await exec('kb_fetch',{id:found.items[0].id});assert.equal(fetched.content.age,30);
 const again=await exec('kb_ingest',{content:{name:'Bob',age:31}});assert.equal(again.status,'stored');
 assert.equal(model.requests.length,requests,'known record shape should skip Agent calls');
 const task=await exec('kb_task',{content:'Compile the Alice source into Wiki knowledge.'});
 const helper=await exec('datanet_spawn_helper',{components:['wiki']});
 const worker=r.sessions.get(helper.node_id).handle.agent;
 assert.ok(!host.tools.schemas(worker).some(t=>t.name==='datanet_spawn_helper'));
 await exec('datanet_send_message',{target:helper.node_id,content:'Read the original task and compile Wiki. sourceRecord='+saved.records[0].id});
 const deadline=Date.now()+20000;
 while(Date.now()<deadline){
   const doc=await exec('task_document_read',{node_id:helper.result_id});
   if(doc.content==='Alice knowledge task complete')break;
   await new Promise(resolve=>setTimeout(resolve,40));
 }
 await worker.whenIdle();await root.whenIdle();
 const delivery=await exec('task_document_read',{node_id:helper.result_id});
 assert.equal(delivery.content,'Alice knowledge task complete');assert.equal(delivery.receipts.length,1);
 assert.equal(r.sessions.size,1,'only a single helper layer is needed');
 const denied=await host.tools.execute({agent:worker,name:'kb_store',arguments:{collection:table.id,content:{name:'bad',age:1}},callId:'scope-denied',signal:new AbortController().signal});
 assert.equal(denied.isError,true,'a Wiki helper must not write SQL');
 const recursive=await host.tools.execute({agent:worker,name:'datanet_spawn_helper',arguments:{},callId:'recursive-denied',signal:new AbortController().signal});
 assert.equal(recursive.isError,true);
 const messages=await exec('datanet_pending_messages');
 assert.ok(messages.messages.some(m=>m.message_type==='reply'&&m.content.includes(helper.result_id)));
 console.log('PASS native Harness knowledge application: single main, direct routing without model calls, scoped helper, original task, real message wakeup, delivery document and one-shot reply');
 await controller.components.dispose();await host.fiber.dispose();clearInterval(keepAlive);
})().catch(error=>{console.error(error);process.exit(1)});

