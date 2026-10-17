// Real Harness Session, registry, compaction transaction, projection and durable resume; no API calls.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const keepAlive=setInterval(()=>{},1000);setTimeout(()=>{console.error('Tool compaction deadline');process.exit(1)},60000).unref();
const root=path.resolve(__dirname,'..');
(async()=>{
 const {native,load}=await require('./native_modules.cjs')();
 const {Context}=native('cordis'),llm=native('dsh-llm'),{SessionId}=native('dsh-session');
 const loop=await load(root+'/adapters/harness/runtime/agent-loop/lib/index.js');
 const invariant=await load(root+'/adapters/harness/runtime/agent-loop/lib/invariant.js');
 const {ToolPermissions}=await load(root+'/adapters/harness/framework/tool-permissions.js');
 const {updateCapabilityTools}=await load(root+'/adapters/harness/framework/capabilities.js');
 const directory=await fs.mkdtemp(path.join(root,'build/tool-compaction-'));
 let executions=0;
 const definition=(name,description=name)=>({name,description,parameters:{type:'object',properties:{}},output:{schema:{type:'string'},render:(_args,value)=>[{type:'text',text:value}]},execute:()=>{executions++;return 'done';}});
 class Model extends llm.LlmAdapter{
  requests=[];call=null;overflow=null;
  async resolveModel(provider,id){return {provider,id,name:id,toolUpdate:'addition-only',systemPromptUpdate:'in-history'};}
  async *stream(options){
   this.requests.push(options);
   if(this.overflow){const fn=this.overflow;this.overflow=null;await fn();throw new llm.LlmError('test overflow','CONTEXT_WINDOW_EXCEEDED');}
   const block=this.call?{type:'tool-call',id:'call-'+this.requests.length,name:this.call,arguments:'{}'}:{type:'text',text:'Completed. '+('Prior conversation detail. '.repeat(180))};this.call=null;
   yield {type:'block-start',index:0,blockType:block.type};
   if(block.type==='text')yield {type:'text-delta',index:0,text:block.text};
   yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'stop'}};
  }
 }
 const make=async()=>{
  const host=new Context();host.on('agent/error',({error})=>console.error('Native Agent error:',error));
  for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await host.plugin(native(name)[service]??native(name).default);
  await host.plugin(loop.default,{agents:[]});
  await host.plugin(native('dsh-invariants').InvariantRegistry);await host.plugin(invariant);
  await host.plugin(native('dsh-session-persistence-jsonl').default,{root:directory});
  await host.plugin(native('dsh-token-meter').default);
  class Compactor extends native('dsh-compaction-basic').BasicCompactionEngine{
   fail=false;
   async summarize(){if(this.fail)throw new Error('summary failed');return {summary:[{type:'text',text:'Summary.'}],provider:'mock',model:'mock'};}
  }
  await host.plugin(Compactor,{auto:false});
  const model=new Model();host.llm.registerAdapter(['mock'],model);
  host.tools.register(definition('global_read'));
  const permissions=new ToolPermissions(llm.createUserMessage);
  const mount=(agent,tools=['global_read'])=>{permissions.bind(agent.ctx,agent);updateCapabilityTools(agent.ctx,agent,{tools},host,permissions);};
  return {host,model,permissions,mount};
 };
 let {host,model,permissions,mount}=await make();
 const agent=await host.agentLoop.create(SessionId('tool-compaction'),{provider:'mock',model:'mock'},{cwd:root});mount(agent);
 const ac=agent.ctx;
 const peer=await host.agentLoop.create(SessionId('tool-compaction-peer'),{provider:'mock',model:'mock'},{cwd:root});mount(peer);
 permissions.register(peer.ctx,definition('temporary'));
 const send=async(text='Continue.')=>{agent.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text}]}));await agent.whenIdle();assert.equal(agent.session.snapshotEvents().findLast(e=>e.type==='turn/end').data.reason.kind,'completed');};
 const names=request=>llm.projectToolUpdates(request.messages,request.tools,'addition-only',request.toolHistory).tools.map(t=>t.name);
 const lastNames=()=>names(model.requests.at(-1));
 const exec=name=>host.tools.execute({agent,name,arguments:{},callId:'direct-'+name,signal:new AbortController().signal});
 let remove=permissions.register(ac,definition('temporary'));
 permissions.register(ac,definition('active'));
 await send();assert.ok(lastNames().includes('temporary'));
 remove();updateCapabilityTools(ac,agent,{tools:[]},host,permissions);
 await send();assert.ok(lastNames().includes('temporary')&&lastNames().includes('global_read'));
 const before=executions;assert.ok((await exec('temporary')).isError);assert.ok((await exec('global_read')).isError);assert.equal(executions,before);
 // Failure closes with an error, leaves definitions and permissions untouched.
 host.compaction.fail=true;await assert.rejects(host.compaction.compactNow(agent,new AbortController().signal),/could not produce a smaller summary/);host.compaction.fail=false;
 assert.ok(host.tools.schemas(agent).some(t=>t.name==='temporary'));await send();assert.ok(lastNames().includes('global_read'));
 // Real manual transaction: summary replacement + successful compaction/end.
 await host.compaction.compactNow(agent,new AbortController().signal);
 assert.ok(!host.tools.schemas(agent).some(t=>['temporary','global_read'].includes(t.name)));
 updateCapabilityTools(ac,agent,{tools:[]},host,permissions);
 await send();assert.deepEqual(lastNames(),['active']);
 assert.ok(host.tools.schemas(peer).some(t=>t.name==='temporary'));
 assert.ok(host.tools.schemas(peer).some(t=>t.name==='global_read'));
 assert.ok(agent.session.snapshotEvents().filter(e=>e.type==='request/header').at(-1).data.startsSeries);
 console.log('PASS native full/failed compaction: removed revoked local/global schemas; active tools remain; guards deny execution');
 // Re-registering after removal is fresh; an obsolete disposer cannot revoke it.
 const oldRemove=remove;remove=permissions.register(ac,definition('temporary','new schema'));oldRemove();
 assert.equal((await exec('temporary')).isError,false);
 await send();assert.equal(model.requests.at(-1).tools.find(t=>t.name==='temporary').description,'new schema');
 // Re-enable official tools, then make actual model tool calls whose recent tail survives a partial compact.
 updateCapabilityTools(ac,agent,{tools:['global_read']},host,permissions);
 const firstNode=agent.session.surface.nodes[1],end=agent.session.surface.nodes.at(-1);
 model.call='temporary';await send();model.call='global_read';await send();
 remove();updateCapabilityTools(ac,agent,{tools:[]},host,permissions);
 const off=ac.on('agent/pre-step',async(payload,next)=>{
  off();await host.compaction.compactRegion(firstNode,end,agent,payload.signal);return next();
 });
 await send();assert.ok(lastNames().includes('temporary')&&lastNames().includes('global_read'));
 assert.ok((await exec('temporary')).isError);assert.ok((await exec('global_read')).isError);
 await host.compaction.compactNow(agent,new AbortController().signal);await send();assert.deepEqual(lastNames(),['active']);
 console.log('PASS partial compaction: retained tool-call/result pairs keep schemas without restoring permission; later full compaction reclaims them');
 // Automatic compaction runs in pre-step AFTER assembly: the immediately following request must be fresh.
 const removeAuto=permissions.register(ac,definition('auto_temporary'));await send();removeAuto();
 const auto=ac.on('agent/pre-step',async(payload,next)=>{auto();const nodes=[...agent.session.surface.nodes].slice(1);await host.compaction.compactRegion(nodes[0],nodes.at(-1),agent,payload.signal);return next();});
 await send();assert.ok(!lastNames().includes('auto_temporary'));
 // Same-name definition refresh happens at the boundary rather than busting a live series.
 permissions.register(ac,definition('active','updated schema'));await send();assert.equal(model.requests.at(-1).tools.find(t=>t.name==='active').description,'active');
 await host.compaction.compactNow(agent,new AbortController().signal);await send();assert.equal(model.requests.at(-1).tools.find(t=>t.name==='active').description,'updated schema');
 console.log('PASS pre-step boundary reassembly and same-name schema refresh');
 // Overflow recovery occurs inside a step and must also discard the assembly captured before compaction.
 const removeOverflow=permissions.register(ac,definition('overflow_temporary'));await send();removeOverflow();
 model.overflow=async()=>{};
 const retry=ac.on('agent/request-error',async(payload,next)=>{
  if(payload.failure.code!=='CONTEXT_WINDOW_EXCEEDED')return next();
  const nodes=[...agent.session.surface.nodes].slice(1);await host.compaction.compactRegion(nodes[0],nodes.at(-1),agent,payload.signal);return {kind:'retry'};
 });
 await send();retry();assert.ok(!lastNames().includes('overflow_temporary'));
 console.log('PASS overflow compaction: retried request drops stale schema immediately');
 const removeResume=permissions.register(ac,definition('resume_temporary'));await send();removeResume();
 await host.compaction.compactNow(agent,new AbortController().signal); // close before a new header is written
 await host.sessions.flush(agent.session);await host.fiber.dispose();
 const restored=await make();({host,model,permissions,mount}=restored);
 const handle=await host.agentLoop.resume(host,{resumeSessionId:agent.id,agentOptions:{provider:'mock',model:'mock'}}),resumed=handle.agent;
 mount(resumed,[]);permissions.register(resumed.ctx,definition('active','updated schema'));
 resumed.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'Resume.'}]}));await resumed.whenIdle();
 assert.deepEqual(names(model.requests.at(-1)),['active']);assert.equal(resumed.session.snapshotEvents().findLast(e=>e.type==='turn/end').data.reason.kind,'completed');
 await host.fiber.dispose();clearInterval(keepAlive);
 console.log('PASS native disk close/resume: no revoked schemas or grants resurrected; no paid calls');
})().catch(error=>{console.error(error);process.exit(1)});
