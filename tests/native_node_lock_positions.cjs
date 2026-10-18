// Installed Harness SDK, local mock inference only. No API keys or network calls.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const keep=setInterval(()=>{},1000);setTimeout(()=>{console.error('node lock fixture deadline');process.exit(1)},25000).unref();
(async()=>{
 const root=path.resolve(__dirname,'..'),directory=path.join(root,'build','node-lock-native-'+Date.now());await fs.mkdir(directory,{recursive:true});
 const {native,load}=await require('./native_modules.cjs')(),{Context}=native('cordis'),host=new Context();
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await host.plugin(native(name)[service]??native(name).default);
 await host.plugin(native('dsh-session-persistence-jsonl').default,{root:path.join(directory,'logs')});
 await host.plugin((await load(root+'/adapters/harness/runtime/agent-loop/lib/index.js')).default,{agents:[]});
 const llm=native('dsh-llm');let release,entered;const ready=new Promise(resolve=>entered=resolve),gate=new Promise(resolve=>release=resolve);
 host.tools.register({name:'node_lock_probe',description:'Local transaction fixture',parameters:{type:'object',additionalProperties:false},output:{schema:{},render:()=>[{type:'text',text:'done'}]},execute:async()=>{entered();await gate;return {ok:true}}});
 let requests=0;
 class Model extends llm.LlmAdapter{
  async resolveModel(provider,id){return {provider,id,name:id};}
  async *stream(){
   const block=++requests===1?{type:'tool-call',id:'lock-call',name:'node_lock_probe',arguments:'{}'}:{type:'text',text:'done'};
   yield {type:'block-start',index:0,blockType:block.type};if(block.type==='text')yield {type:'text-delta',index:0,text:block.text};
   yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:block.type==='tool-call'?'tool-calls':'stop'}};
  }
 }
 host.llm.registerAdapter(['mock'],new Model());
 const agent=await host.agentLoop.create(native('dsh-session').SessionId('node-lock-prefix'),{provider:'mock',model:'mock'});
 const {NativePositions}=await load(root+'/adapters/harness/framework/checkpoints.js'),positions=new NativePositions(host);
 agent.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'BEFORE_LOCK'}]}));await ready;
 assert.equal(await positions.capture(agent.session),null,'ordinary recovery points wait for tool results');
 const before=await positions.capture(agent.session,{allowPending:true});assert.ok(before);
 assert.deepEqual(await positions.capture(agent.session,{allowPending:true}),before,'unchanged log reuses its cursor');
 agent.steer(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'UNCOMMITTED_CONTEXT'}]}));
 const after=await positions.capture(agent.session,{allowPending:true});assert.ok(after.event_count>before.event_count);
 const fork=await positions.fork(before),restored=await positions.captureStored(fork),prefix=await positions.read(restored);
 assert.ok(JSON.stringify(prefix.events).includes('BEFORE_LOCK'));
 assert.ok(!JSON.stringify(prefix.events).includes('UNCOMMITTED_CONTEXT'));
 assert.ok(prefix.events.some(e=>e.type==='turn/end'&&e.data.reason.kind==='forked'));
 assert.ok(prefix.events.some(e=>e.type==='tool/result'),'unanswered tool is closed without replay');
 assert.ok(agent.session.seq>=after.event_count,'original append-only history stays intact');
 agent.cancel('user');release();await agent.whenIdle();await host.fiber.dispose();clearInterval(keep);
 const evidence={passed:true,paid_api_calls:0,mock_requests:requests,before:before.event_count,uncommitted:after.event_count,restored:restored.event_count,forked:true,original_log_preserved:true};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify({directory,...evidence}));
})().catch(error=>{console.error(error);process.exit(1)});
