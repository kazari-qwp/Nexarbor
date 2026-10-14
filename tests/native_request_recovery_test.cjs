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
 const recovery=await get(pathToFileURL(productRoot+'/adapters/harness/framework/request-recovery.js').href);await recovery.link(link);await recovery.evaluate();
 const host=new Context();for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await host.plugin(native(name)[service]??native(name).default);
 await host.plugin(loop.namespace.default,{agents:[]});
 let executed=0;host.tools.register({name:'recovery_probe',description:'Test execution boundary',parameters:{type:'object',properties:{value:{type:'string'}}},output:{schema:{},render:()=>[{type:'text',text:'ok'}]},execute:()=>{executed++;return {ok:true}}});
 class Model extends llm.LlmAdapter{
  requests=[];counts=new Map();
  async resolveModel(provider,id){return {provider,id,name:id,toolUpdate:'addition-only',systemPromptUpdate:'in-history'}}
  async *stream(options){
   const goal=options.messages.flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).find(t=>t.endsWith('-case'));
   const n=(this.counts.get(goal)??0)+1;this.counts.set(goal,n);this.requests.push({goal,n,options});
   const broken=goal==='exhaust-case'||goal==='other-case'||goal==='recover-case'&&n===1||goal==='reset-case'&&(n===1||n===3);
   if(broken){
    const block={type:'tool-call',id:'bad-'+n,name:'recovery_probe',arguments:'{'};
    yield {type:'block-start',index:0,blockType:'tool-call'};yield {type:'block-end',index:0,block};
    yield {type:'finish',reason:{kind:'error',failure:{code:'MALFORMED_RESPONSE',message:goal==='other-case'?'DeepSeek Messages stream: invalid block index':'DeepSeek Messages stream: tool input is invalid JSON'}}};return;
   }
   const tool=goal==='recover-case'&&n===2||goal==='reset-case'&&(n===2||n===4);
   const block=tool?{type:'tool-call',id:'good-'+n,name:'recovery_probe',arguments:JSON.stringify({value:'corrected'})}:{type:'text',text:'完成'};
   yield {type:'block-start',index:0,blockType:block.type};if(!tool)yield {type:'text-delta',index:0,text:block.text};yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:tool?'tool-calls':'stop'}};
  }
 }
 const model=new Model();host.llm.registerAdapter(['mock'],model);
 const run=async goal=>{
  const agent=await host.agentLoop.create(native('dsh-session').SessionId(goal),{provider:'mock',model:'mock'});
  recovery.namespace.installRequestRecovery(agent.ctx,agent);
  agent.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:goal}]}));await agent.whenIdle();
  return {agent,events:agent.session.snapshotEvents(),requests:model.requests.filter(r=>r.goal===goal)};
 };
 const first=await run('recover-case');assert.equal(first.requests.length,3);assert.equal(executed,1);
 assert.equal(first.events.filter(e=>e.type==='datanet/request-recovery').length,1);
 assert.equal(first.events.filter(e=>e.type==='turn/start').length,1);
 assert.equal(first.events.findLast(e=>e.type==='turn/end').data.reason.kind,'completed');
 assert.ok(first.requests[1].options.messages.some(m=>m.content.some(b=>b.type==='text'&&b.text.includes(recovery.namespace.TOOL_JSON_RECOVERY_NOTICE))));
 assert.ok(first.requests[1].options.messages.some(m=>m.content.some(b=>b.type==='text'&&b.text.includes('工具：recovery_probe')&&b.text.includes('参数原文：\n{'))));
 for(let i=0;i<first.requests[0].options.messages.length;i++)assert.deepEqual(first.requests[1].options.messages[i],first.requests[0].options.messages[i]);
 assert.ok(!first.agent.session.deriveMessages().some(m=>m.role==='assistant'&&m.content.some(b=>b.type==='tool-call'&&b.arguments==='{')));
 const exhausted=await run('exhaust-case');assert.equal(exhausted.requests.length,3);assert.equal(executed,1);
 assert.equal(exhausted.events.filter(e=>e.type==='datanet/request-recovery').length,2);
 assert.equal(exhausted.events.findLast(e=>e.type==='turn/end').data.reason.error.code,'MALFORMED_RESPONSE');
 const unrelated=await run('other-case');assert.equal(unrelated.requests.length,1);assert.equal(unrelated.events.filter(e=>e.type==='datanet/request-recovery').length,0);
 const reset=await run('reset-case');assert.equal(reset.requests.length,5);assert.equal(executed,3);
 assert.equal(reset.events.findLast(e=>e.type==='turn/end').data.reason.kind,'completed');
 assert.equal(reset.events.filter(e=>e.type==='datanet/request-recovery').length,2);
 await host.fiber.dispose();clearInterval(keepAlive);
 console.log('PASS native request-error: corrective context, same turn, two-retry bound, unrelated errors excluded, budget reset per step, failed tool never executed');
})().catch(e=>{console.error(e);process.exit(1)});
