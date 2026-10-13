const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL}=require('node:url');
const keepAlive=setInterval(()=>{},1000);setTimeout(()=>{console.error('Native capability test deadline');process.exit(1)},30000).unref();
const root=path.resolve(__dirname,'..');
const nativeRoot=process.env.DATANET_NATIVE_MODULES??path.join(process.env.LOCALAPPDATA,'Programs','DeepSeek Harness','resources','app.asar','dsh','node_modules');
const native=name=>require(path.join(nativeRoot,'@deepseek-ai',name));
const context=vm.createContext({process,console,Buffer,URL,AbortController,AbortSignal,structuredClone,setTimeout,clearTimeout,setInterval,clearInterval,Symbol});
const cache=new Map();
async function load(file){
 if(cache.has(file))return cache.get(file);
 const mod=new vm.SourceTextModule(await fs.readFile(file,'utf8'),{context,identifier:pathToFileURL(file).href,initializeImportMeta:m=>m.url=pathToFileURL(file).href});cache.set(file,mod);
 await mod.link(async spec=>{
  if(spec.startsWith('.'))return load(path.resolve(path.dirname(file),spec));
  const ns=spec.startsWith('@deepseek-ai/')?native(spec.slice(13)):spec==='zod'?require(path.join(nativeRoot,'zod')):require(spec);
  const keys=[...new Set([...Object.keys(ns),'default'])];return new vm.SyntheticModule(keys,function(){for(const key of keys)this.setExport(key,key==='default'?(ns.default??ns):ns[key])},{context});
 });return mod;
}
(async()=>{
 const {Context}=native('cordis'),host=new Context();
 host.on('agent/error',payload=>console.error('Agent error',payload.error));
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await host.plugin(native(name)[service]??native(name).default);
 const loop=await load(root+'/adapters/harness/runtime/agent-loop/lib/index.js');await loop.evaluate();await host.plugin(loop.namespace.default,{agents:[]});
 const p=await load(root+'/adapters/harness/framework/tool-permissions.js');await p.evaluate();
 const c=await load(root+'/adapters/harness/framework/capabilities.js');await c.evaluate();
 const llm=native('dsh-llm');
 class Model extends llm.LlmAdapter{
  requests=[];async resolveModel(provider,id){return {provider,id,name:id,toolUpdate:'addition-only',systemPromptUpdate:'in-history'};}
  async *stream(options){this.requests.push(options);yield* [{type:'block-start',index:0,blockType:'text'},{type:'text-delta',index:0,text:'ok'},{type:'block-end',index:0,block:{type:'text',text:'ok'}},{type:'usage',usage:{inputTokens:1,outputTokens:1}},{type:'finish',reason:{kind:'stop'}}];}
 }
 const model=new Model();host.llm.registerAdapter(['mock'],model);
 const agent=await host.agentLoop.create(native('dsh-session').SessionId('own-layer-test'),{provider:'mock',model:'mock'},{cwd:root});
 const ac=agent.ctx,permissions=new p.namespace.ToolPermissions(llm.createUserMessage);let calls=0;
 const definition=name=>({name,description:name,parameters:{type:'object',properties:{}},output:{schema:{type:'string'},render:(_args,value)=>[{type:'text',text:value}]},execute:()=>{calls++;return 'ok';}});
 ac.tools.register(definition('subagent'));ac.tools.register(definition('read'));
 // Real own-layer definitions are exempt from Harness restrict().
 assert.ok(!host.tools.view(agent).restrictableNames.has('subagent'));
 c.namespace.updateCapabilityTools(ac,agent,{tools:['read']},host,permissions);
 const exec=name=>host.tools.execute({agent,name,arguments:{},callId:name,signal:new AbortController().signal});
 assert.equal((await exec('subagent')).isError,true);assert.equal(calls,0);
 assert.equal((await exec('read')).isError,false);assert.equal(calls,1);
 ac.tools.register(definition('late_ungranted'));assert.equal((await exec('late_ungranted')).isError,true);assert.equal(calls,1);
 permissions.register(ac,definition('datanet_local'));
 const send=async()=>{agent.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'test'}]}));await agent.whenIdle();};
 await send();let names=model.requests.at(-1).tools.map(t=>t.name);
 assert.ok(names.includes('read')&&names.includes('datanet_local'));assert.ok(!names.includes('subagent')&&!names.includes('late_ungranted'));
 c.namespace.updateCapabilityTools(ac,agent,{tools:[]},host,permissions);assert.equal((await exec('read')).isError,true);
 await send();assert.ok(model.requests.at(-1).tools.some(t=>t.name==='read')); // Retain declared definitions after revocation.
 c.namespace.updateCapabilityTools(ac,agent,{tools:['read']},host,permissions);assert.equal((await exec('read')).isError,false);
 assert.equal((await exec('datanet_local')).isError,false);
 await host.fiber.dispose();clearInterval(keepAlive);console.log('PASS native own-layer and late tool denial, request schema filtering, retained definitions and restored grants; no paid calls');
})().catch(error=>{console.error(error);process.exit(1)});
