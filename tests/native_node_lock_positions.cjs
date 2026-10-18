// Installed Harness SDK, local mock inference only. No API keys or network calls.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const keep=setInterval(()=>{},1000);setTimeout(()=>{console.error('node lock fixture deadline');process.exit(1)},25000).unref();
(async()=>{
 const root=path.resolve(__dirname,'..'),directory=path.join(root,'build','node-lock-native-'+Date.now());await fs.mkdir(directory,{recursive:true});
 const {native,load}=await require('./native_modules.cjs')(),{Context}=native('cordis'),host=new Context();
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await host.plugin(native(name)[service]??native(name).default);
 const persistence=native('dsh-session-persistence-jsonl');await host.plugin(persistence.default??persistence,{root:path.join(directory,'logs')});
 await host.plugin((await load(root+'/adapters/harness/runtime/agent-loop/lib/index.js')).default,{agents:[]});
 const llm=native('dsh-llm');let release,entered,ready,gate;const resetGate=()=>{ready=new Promise(resolve=>entered=resolve);gate=new Promise(resolve=>release=resolve);};resetGate();
 host.tools.register({name:'node_lock_probe',description:'Local transaction fixture',parameters:{type:'object',additionalProperties:false},output:{schema:{},render:()=>[{type:'text',text:'done'}]},execute:async()=>{entered();await gate;return {ok:true}}});
 let requests=0;
 class Model extends llm.LlmAdapter{
  async resolveModel(provider,id){return {provider,id,name:id};}
  async *stream(){
   const block=++requests%2===1?{type:'tool-call',id:'lock-call-'+requests,name:'node_lock_probe',arguments:'{}'}:{type:'text',text:'done'};
   yield {type:'block-start',index:0,blockType:block.type};if(block.type==='text')yield {type:'text-delta',index:0,text:block.text};
   yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:block.type==='tool-call'?'tool-calls':'stop'}};
  }
 }
 host.llm.registerAdapter(['mock'],new Model());
 const {NativePositions}=await load(root+'/adapters/harness/framework/checkpoints.js'),positions=new NativePositions(host);
 const stable=await host.agentLoop.create(native('dsh-session').SessionId('node-lock-unchanged'),{provider:'mock',model:'mock'});
 stable.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'LIVE_TOOL'}]}));await ready;
 const same=await positions.capture(stable.session,{allowPending:true});let retired=false;
 const reuse=await positions.restore(same,stable.session,{onDiverged:()=>{retired=true;stable.cancel('user');}});
 assert.ok(reuse.reused);assert.equal(retired,false);release();await stable.whenIdle();
 assert.ok(stable.session.deriveMessages().some(m=>m.role==='assistant'&&m.content.some(b=>b.type==='text'&&b.text==='done')),'unchanged rollback must let the live tool turn finish');
 resetGate();const agent=await host.agentLoop.create(native('dsh-session').SessionId('node-lock-prefix'),{provider:'mock',model:'mock'});
 agent.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'BEFORE_LOCK'}]}));await ready;
 assert.equal(await positions.capture(agent.session),null,'ordinary recovery points wait for tool results');
 const before=await positions.capture(agent.session,{allowPending:true});assert.ok(before);
 assert.deepEqual(await positions.capture(agent.session,{allowPending:true}),before,'unchanged log reuses its cursor');
 agent.steer(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'UNCOMMITTED_CONTEXT'}]}));
 const after=await positions.capture(agent.session,{allowPending:true});assert.ok(after.event_count>before.event_count);
 let diverged=false;const recovery=await positions.restore(before,agent.session,{onDiverged:()=>{diverged=true;agent.cancel('user');}}),restored=recovery.cursor,prefix=await positions.read(restored);
 assert.equal(recovery.reused,false);assert.equal(diverged,true);
 assert.ok(JSON.stringify(prefix.events).includes('BEFORE_LOCK'));
 assert.ok(!JSON.stringify(prefix.events).includes('UNCOMMITTED_CONTEXT'));
 assert.ok(prefix.events.some(e=>e.type==='turn/end'&&e.data.reason.kind==='forked'));
 assert.ok(prefix.events.some(e=>e.type==='tool/result'),'unanswered tool is closed without replay');
 assert.ok(agent.session.seq>=after.event_count,'original append-only history stays intact');
 agent.cancel('user');release();await agent.whenIdle();await host.fiber.dispose();clearInterval(keep);
 const evidence={passed:true,paid_api_calls:0,mock_requests:requests,before:before.event_count,uncommitted:after.event_count,restored:restored.event_count,forked:true,unchanged_live_turn_preserved:true,original_log_preserved:true};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify({directory,...evidence}));
})().catch(error=>{console.error(error);process.exit(1)});
