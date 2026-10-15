const keepAlive=setInterval(()=>{},1000);setTimeout(()=>{console.error('Test deadline');process.exit(1)},20000).unref();
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL,fileURLToPath}=require('node:url');
const nativeRoot=process.env.DATANET_NATIVE_MODULES??path.join(process.env.LOCALAPPDATA,'Programs','DeepSeek Harness','resources','app.asar','dsh','node_modules');
const productRoot=path.resolve(__dirname,'..'),native=name=>require(path.join(nativeRoot,'@deepseek-ai',name));
const {Context}=native('cordis'),llm=native('dsh-llm');
(async()=>{
 const context=vm.createContext({process,console,Buffer,URL,AbortController,AbortSignal,structuredClone,setTimeout,clearTimeout,setInterval,clearInterval,Symbol}),cache=new Map();
 async function get(spec,parent){
  const file=spec.startsWith('file:')?fileURLToPath(spec):spec.startsWith('.')?path.resolve(path.dirname(fileURLToPath(parent)),spec):null,key=file??spec;
  if(cache.has(key))return cache.get(key);
  if(!file){const ns=spec.startsWith('@deepseek-ai/')?native(spec.slice(13)):spec==='zod'?require(path.join(nativeRoot,'zod')):await import(spec);const keys=[...new Set([...Object.keys(ns),'default'])];const m=new vm.SyntheticModule(keys,function(){for(const k of keys)this.setExport(k,k==='default'?(ns.default??ns):ns[k])},{context});cache.set(key,m);return m;}
  const m=new vm.SourceTextModule(await fs.readFile(file,'utf8'),{context,identifier:pathToFileURL(file).href,initializeImportMeta:x=>x.url=pathToFileURL(file).href});cache.set(key,m);return m;
 }
 const link=(spec,ref)=>get(spec,ref.identifier);
 const loop=await get(pathToFileURL(productRoot+'/adapters/harness/runtime/agent-loop/lib/index.js').href);await loop.link(link);await loop.evaluate();

 const nativeSession=native('dsh-session'),persistence=native('dsh-session-persistence-jsonl');
 const directory=await fs.mkdtemp(path.join(productRoot,'build/late-persistence-'));
 class Model extends llm.LlmAdapter{
  async resolveModel(provider,id){return {provider,id,name:id,toolUpdate:'addition-only',systemPromptUpdate:'in-history'}}
  async *stream(options){
   const block={type:'text',text:'restoration probe completed'};
   yield {type:'block-start',index:0,blockType:'text'};yield {type:'text-delta',index:0,text:block.text};
   yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'stop'}};
  }
 }
 const make=async()=>{
  const ctx=new Context();
  for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await ctx.plugin(native(name)[service]??native(name).default);
  // Match desktop startup: the optional storage service arrives after AgentLoop.
  await ctx.plugin(loop.namespace.default,{agents:[]});
  assert.equal(ctx.get('sessionPersistence'),undefined);
  await ctx.plugin(persistence.default,{root:directory,compression:'zstd'});
  ctx.llm.registerAdapter(['mock'],new Model());
  ctx.on('agent/request-tail',async()=>[{role:'user',content:[{type:'text',text:'ephemeral tail'}]}]);
  return ctx;
 };
 const id=nativeSession.SessionId('late-storage-probe'),first=await make();
 const agent=await first.agentLoop.create(id,{provider:'mock',model:'mock'});
 agent.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'first turn'}]}));
 await agent.whenIdle();
 assert.equal(agent.session.snapshotEvents().findLast(e=>e.type==='turn/end').data.reason.kind,'completed');
 assert.ok(agent.session.snapshotEvents().some(e=>e.type==='datanet/request-tail'));
 agent.session.append('datanet/request-recovery',{attempt:1,maxCorrections:2});
 await first.fiber.dispose();
 const second=await make(),handle=await second.agentLoop.resume(second,{resumeSessionId:id,agentOptions:{provider:'mock',model:'mock'}});
 const restored=handle.agent;
 const tails=restored.session.snapshotEvents().filter(e=>e.type==='datanet/request-tail');
 assert.ok(tails.length>0);assert.ok(tails.every(e=>e.ignorable===true));
 restored.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'second turn'}]}));
 await restored.whenIdle();
 assert.equal(restored.session.snapshotEvents().findLast(e=>e.type==='turn/end').data.reason.kind,'completed');
 await second.fiber.dispose();
 const third=await make(),read=await third.sessionPersistence.open(id,'read'),cold=await read.read();
 assert.equal(cold.events.filter(e=>e.type==='turn/end').length,2);
 assert.ok(cold.events.filter(e=>e.type==='datanet/request-tail').every(e=>e.ignorable===true));
 assert.equal(cold.events.filter(e=>e.type==='datanet/request-recovery'&&e.ignorable===true).length,1);
 await read.close();await third.fiber.dispose();clearInterval(keepAlive);
 console.log('PASS native AgentLoop: late persistence, real request tail, close/resume, continued turn, second cold read');
})().catch(error=>{console.error(error);process.exit(1)});
