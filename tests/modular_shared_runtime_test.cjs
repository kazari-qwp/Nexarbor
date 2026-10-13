const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL}=require('node:url');
const nativeRoot=process.env.DATANET_NATIVE_MODULES??path.join(process.env.LOCALAPPDATA,'Programs','DeepSeek Harness','resources','app.asar','dsh','node_modules');
const productRoot=path.resolve(__dirname,'..');
const testRoot=process.env.DATANET_TEST_TEMP??path.join(productRoot,'build','test-data');
require('node:fs').mkdirSync(testRoot,{recursive:true});
const native=name=>require(path.join(nativeRoot,'@deepseek-ai',name));
const {Context}=native('cordis'), llm=native('dsh-llm');
const context=vm.createContext({process,console,Buffer,URL,AbortController,structuredClone,setTimeout,clearTimeout,setInterval,clearInterval,Symbol});
async function moduleAt(file){
  const mod=new vm.SourceTextModule(await fs.readFile(file,'utf8'),{context,identifier:pathToFileURL(file).href,initializeImportMeta:m=>m.url=pathToFileURL(file).href});
  await mod.link(async spec=>{const ns=spec.startsWith('@deepseek-ai/')?native(spec.slice(13)):spec==='zod'?require(path.join(nativeRoot,'zod')):require(spec);const keys=[...new Set([...Object.keys(ns),'default'])];return new vm.SyntheticModule(keys,function(){for(const key of keys)this.setExport(key,key==='default'?(ns.default??ns):ns[key]);},{context});});
  await mod.evaluate();return mod.namespace;
}
const textResponse=text=>[{type:'block-start',index:0,blockType:'text'},{type:'text-delta',index:0,text},{type:'block-end',index:0,block:{type:'text',text}},{type:'usage',usage:{inputTokens:10,outputTokens:2}},{type:'finish',reason:{kind:'stop'}}];
(async()=>{
  const base=productRoot;
  const loop=await moduleAt(base+'/adapters/harness/runtime/agent-loop/lib/index.js');
  const invariant=await moduleAt(base+'/adapters/harness/runtime/agent-loop/lib/invariant.js');
  const host=new Context();
  for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry'],['dsh-invariants','InvariantRegistry']])await host.plugin(native(name)[service]??native(name).default);
  await host.plugin(loop.default,{agents:[]});await host.plugin(invariant);
  class Adapter extends llm.LlmAdapter{
    requests=[];
    async resolveModel(provider,model){return {provider,id:model,name:model,toolUpdate:'addition-only',systemPromptUpdate:'in-history'};}
    async *stream(options){this.requests.push(options);yield* textResponse('ok');}
  }
  const adapter=new Adapter();host.llm.registerAdapter(['mock'],adapter);
  const agent=await host.agentLoop.create(native('dsh-session').SessionId('shared-tail-native'),{provider:'mock',model:'mock'});
  const {InstructionHistory}=await import(pathToFileURL(base+'/adapters/harness/framework/instructions.js').href);
  const {ToolPermissions}=await import(pathToFileURL(base+'/adapters/harness/framework/tool-permissions.js').href);
  const {SharedTexts}=await import(pathToFileURL(base+'/components/nodes/text/controller.js').href);
  const instructions=new InstructionHistory(llm.createUserMessage);instructions.bind(agent.ctx,agent);
  const permissions=new ToolPermissions(llm.createUserMessage);
  let notebook='first', queries=0, connections=true;
  const bridge={async call(method,p){
    if(method==='text_bindings')return {read:connections?[{node_id:'root/q',delivery:'query',label:'[项目说明：root/q]'}]:[],write:connections?[{node_id:'group/notebook',name:'公共笔记'}]:[]};
    if(method==='resident_texts')return {texts:connections?[{text:'[公共笔记：group/notebook](由recorder维护)\n'+notebook}]:[]};
    if(method==='query_text'){queries++;return {node_id:p.target,text:'[项目说明：root/q]\n材料正文'};}
    if(method==='write_resident_text'){notebook=p.content;return {status:'ok',items:[{written:true,node_id:p.target}]};}
    if(method==='load_project')return {status:'ok',items:[{node_id:'root/q',name:'项目说明',description:'',content:'材料正文'}]};
    throw new Error(method);
  }};
  const shared=new SharedTexts({bridge,instructions,scope:()=>({actor:'group/recorder',maxStrength:2}),register:(ac,name,description,parameters,execute)=>permissions.register(ac,{name,description,parameters,output:{schema:{},render:(_a,value)=>[{type:'text',text:JSON.stringify(value)}]},execute})});
  shared.attach(agent.ctx,agent);await shared.sync(agent.ctx);
  const send=async text=>{agent.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text}]}));await agent.whenIdle();};
  await send('turn 1');assert.equal(adapter.requests.length,1);assert.match(adapter.requests[0].messages.at(-1).content[0].text,/first$/);
  assert.ok(!JSON.stringify(agent.session.deriveMessages()).includes('由recorder维护'));
  notebook='second';await send('turn 2');assert.equal(adapter.requests.length,2);assert.match(adapter.requests[1].messages.at(-1).content[0].text,/second$/);
  assert.ok(!JSON.stringify(adapter.requests[1].messages).includes('first'));
  assert.ok(!JSON.stringify(agent.session.deriveMessages()).includes('second'));
  const snapshot=agent.session.snapshotEvents().filter(e=>e.type==='datanet/request-tail').at(-1);
  assert.deepEqual(JSON.parse(JSON.stringify(snapshot.data.messages)),JSON.parse(JSON.stringify(adapter.requests[1].messages.slice(-1))));
  console.log('PASS real Harness loop + invariant: latest notebook only at request end, no old tail or history pollution, reconstructable snapshot');
  const execute=(name,args)=>host.tools.execute({agent,name,arguments:args,callId:'shared-'+Math.random(),signal:new AbortController().signal});
  const tool=host.tools.schemas(agent).find(t=>t.name.startsWith('query_text_'));
  assert.ok(tool);assert.equal((await execute(tool.name,{})).isError,false);await send('loaded');
  assert.match(JSON.stringify(agent.session.deriveMessages()),/材料正文/);
  assert.equal((await execute(tool.name,{})).isError,false);await send('again');
  assert.equal(agent.session.deriveMessages().filter(m=>m.source?.document==='query-text:root/q').length,1);
  await shared.project(agent.ctx,'group',['root/q']);assert.equal(queries,2);
  const document=agent.session.snapshotEvents().find(e=>e.type==='user/message'&&e.data.source?.document==='query-text:root/q');
  agent.session.append('user/message',llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'项目资料摘要'}]}),{surfaceOp:{op:'replace',startSeq:document.seq,endSeq:document.seq},sourceEventSeqs:[document.seq]});
  instructions.prune(agent.ctx);assert.equal(instructions.has(agent.ctx,'query-text:root/q'),false);
  await execute(tool.name,{});await send('after compaction');
  assert.equal(agent.session.deriveMessages().filter(m=>m.source?.document==='query-text:root/q').length,1);
  assert.ok(!agent.session.deriveMessages().some(m=>JSON.stringify(m.content).includes('由recorder维护')));
  console.log('PASS compaction boundary: query document reloads on demand; notebook never enters retained history');
  assert.equal((await execute('write_resident_text',{target:'root/q',content:'denied'})).isError,true);
  assert.equal((await execute('write_resident_text',{content:'third'})).isError,false);await send('updated');assert.match(adapter.requests.at(-1).messages.at(-1).content[0].text,/third$/);
  const schemas=host.tools.schemas(agent);connections=false;await shared.sync(agent.ctx);assert.deepEqual(host.tools.schemas(agent),schemas);
  assert.equal((await execute(tool.name,{})).isError,true);await send('removed');
  assert.ok(!JSON.stringify(adapter.requests.at(-1).messages).includes('由recorder维护'));
  connections=true;await send('reconnected');
  assert.ok(adapter.requests.at(-1).tools.some(t=>t.name===tool.name));
  assert.equal((await execute(tool.name,{})).isError,false);
  console.log('PASS native tools: bound query, history dedup, initial-project reuse, resident-only write, retained definitions with revoked permissions');
  console.log('PASS all shared-text runtime checks');
})().catch(error=>{console.error(error);process.exitCode=1;});
