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
 const link=(spec,ref)=>get(spec,ref.identifier),entry=await get(pathToFileURL(base+'/extensions/npc_world/capabilities/world_runtime/entry.js').href);await entry.link(link);await entry.evaluate();
 const loop=await get(pathToFileURL(base+'/adapters/harness/runtime/agent-loop/lib/index.js').href);await loop.link(link);await loop.evaluate();
 const host=new Context(),temp=await fs.mkdtemp(path.join(testRoot,'creation-'));
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']]){await host.plugin(native(name)[service]??native(name).default);}
 host.provide('sessionTitle',{rename(){}});host.sessions.flush=async()=>{};
 await host.plugin(loop.namespace.default,{agents:[]});

 const controller=await entry.namespace.apply(host,{workspace:temp,storage:path.join(temp,'.datanet'),backend:process.env.DATANET_TEST_PYTHON??base+'/.venv/Scripts/python.exe',backendArgs:[base+'/adapters/harness/backend/server.py'],worldAllowFullRun:false,worldMaxRequests:8,agentMaxTokens:4096});
 const llm=native('dsh-llm');
 class Model extends llm.LlmAdapter {
  requests=[];fail=false;
  async resolveModel(provider,id){return {provider,id,name:id,toolUpdate:'addition-only',systemPromptUpdate:'in-history'};}
  async *stream(options){
   this.requests.push(options);
   if(this.fail)throw new Error('simulated native Agent failure');
   assert.ok(!options.tools.some(t=>(t.function?.name??t.name)==='world_submit'));
   const texts=options.messages.flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).join('\n');
   assert.ok(texts.includes('第1天-早'),'time text must be admitted before the first NPC request');
   assert.ok(texts.includes('你是一位伐木工') && texts.includes('你是一位男性居民'));
   assert.ok(!texts.includes('你目前正在怀孕') && !texts.includes('预产时刻'));
   const calls=options.messages.filter(m=>m.role==='assistant').flatMap(m=>m.content.filter(b=>b.type==='tool-call'));
   const last=calls.at(-1)?.name;
   const call=!last?{name:'node_tools',arguments:{target:'world/service/forest',direction:'write'}}:last==='node_tools'?{name:'node_invoke',arguments:{target:'world/service/forest',tool:'chop',arguments:{},direction:'write'}}:null;
   const block=call?{type:'tool-call',id:'npc-'+this.requests.length,name:call.name,arguments:JSON.stringify(call.arguments)}:{type:'text',text:'本时刻砍树计划已完成，正常结束。'};
   yield {type:'block-start',index:0,blockType:block.type};
   if(!call)yield {type:'text-delta',index:0,text:block.text};
   yield {type:'block-end',index:0,block};
   yield {type:'usage',usage:{inputTokens:10,outputTokens:2}};
   yield {type:'finish',reason:{kind:'stop'}};
  }
 }
 const model=new Model();host.llm.registerAdapter(['mock'],model);
 const root=await host.agentLoop.create(native('dsh-session').SessionId('npc-pulse-root'),{provider:'mock',model:'mock'},{cwd:temp});
 await host.parallel('agent/created',{agent:root});
 const r=controller.runtimes.get(root.id);
 const exec=async(name,args={})=>{const result=await host.tools.execute({agent:root,name,arguments:args,callId:'npc-'+name,signal:new AbortController().signal});assert.equal(result.isError,false,JSON.stringify(result));return result.value};
 await r.bridge.call('node_metadata_set',{actor:'root',target:'world/npc/woodcutter',namespace:'compatibility',values:{memory_style:'concise'}});
 const first=await exec('world_run_npc',{target:'world/npc/woodcutter'});
 const report=first.pulse.reports[0];assert.equal(report.returned,true);assert.equal(report.status,'completed');
 assert.deepEqual(JSON.parse(JSON.stringify(report.layers)),[['world/time'],['world/npc/woodcutter'],['world/pulse']]);
 const worker=r.sessions.get('world/npc/woodcutter').handle.agent;
 assert.equal(worker.session.snapshotEvents().findLast(e=>e.type==='turn/end').data.reason.kind,'completed');
 const profileMessages=worker.session.deriveMessages().filter(m=>m.source?.kind==='datanet-instructions'&&m.source.document.startsWith('prompt'));
 assert.equal(profileMessages.length,4,'three independent documents plus one current metadata snapshot');
 const metadataMessage=profileMessages.find(m=>m.source.document.startsWith('prompt-state:'));
 assert.ok(metadataMessage,'unified metadata must be injected through the history channel');
 const metadataText=metadataMessage.content.filter(b=>b.type==='text').map(b=>b.text).join('\n');
 assert.ok(metadataText.includes('memory_style')&&metadataText.includes('concise'),'matcher must automatically include the optional metadata namespace');
 assert.ok(metadataText.includes('woodcutter'),'NPC provider metadata must coexist with optional static metadata');
 assert.equal(new Set(profileMessages.map(m=>m.source.document)).size,4,'no repeated instruction copies across model steps');
 assert.ok(!(await r.bridge.call('application/view',{actor:'world/npc/woodcutter'})).prompt.includes('伐木工'),'profession must not rewrite the role system prompt');
 assert.deepEqual(JSON.parse(JSON.stringify(report.deliveries[1].value.responders[0].steps.map(s=>s.tool))),['match_prompts','world_run_actor']);
 const world=await r.bridge.call('world_observe',{actor:'root'});
 assert.equal(world.actors['world/npc/woodcutter'].inventory.wood,2);assert.equal(world.actors['world/npc/woodcutter'].inventory.axe,2);
 assert.equal(world.round.outcomes['world/npc/woodcutter'].status,'completed');
 assert.equal(model.requests.length,3);assert.ok(!host.tools.schemas(worker).some(t=>t.name==='world_submit'));
 const tails=worker.session.snapshotEvents().filter(e=>e.type==='datanet/request-tail');assert.ok(tails.length>=3);
 assert.ok(tails.every(e=>JSON.stringify(e.data.messages).includes('第1天-早')));
 // Same application, native error ending must never be mistaken for ready/completed.
 model.fail=true;
 const failed=await exec('world_run_npc',{target:'world/npc/woodcutter'});
 assert.equal(failed.pulse.reports[0].returned,false);assert.equal(failed.pulse.reports[0].status,'partial');
 const after=await r.bridge.call('world_observe',{actor:'root'});
 assert.equal(after.round.outcomes['world/npc/woodcutter'].status,'unavailable');
 assert.equal(after.actors['world/npc/woodcutter'].inventory.wood,2);
 await controller.components.dispose();await host.fiber.dispose();clearInterval(keepAlive);
 console.log('PASS native Harness NPC pulse: channel response sequence, stable role prompt, independent history documents, resident clock, location tool, natural completion, return to source, native error rejected; no model API calls');
})().catch(error=>{console.error(error);process.exit(1)});
