// Owned subprocess fixture. Parent force-kills write mode while Mock inference is pending.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const keep=setInterval(()=>{},1000);setTimeout(()=>{console.error('fixture deadline');process.exit(1)},30000).unref();
(async()=>{
 const base=path.resolve(__dirname,'..'),folder=path.resolve(process.argv[3]),mode=process.argv[2];
 const {native,load}=await require('./native_modules.cjs')();
 const {Context}=native('cordis'),host=new Context();
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await host.plugin(native(name)[service]??native(name).default);
 await host.plugin(native('dsh-session-persistence-jsonl').default,{root:path.join(folder,'logs')});
 const {NativeCheckpoints,NativePositions}=await load(base+'/adapters/harness/framework/checkpoints.js');
 const {Bridge}=await load(base+'/adapters/harness/framework/bridge.js');
 const directory=path.join(folder,'core');
 const bridge=new Bridge(process.env.DATANET_TEST_PYTHON??base+'/.venv/Scripts/python.exe',directory,[base+'/adapters/harness/backend/server.py'],{DATANET_COMPONENT_ROOT:base+'/extensions/.none',PYTHONDONTWRITEBYTECODE:'1'});
 const call=(name,args={})=>bridge.call(name,args);
 if(mode==='write'){
   const loop=await load(base+'/adapters/harness/runtime/agent-loop/lib/index.js');await host.plugin(loop.default,{agents:[]});
   let started;const waiting=new Promise(resolve=>started=resolve);const llm=native('dsh-llm');
   class Model extends llm.LlmAdapter{
     async resolveModel(provider,id){return {provider,id,name:id};}
     async *stream(options){started();await new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('cancelled')),{once:true}));}
   }
   host.llm.registerAdapter(['mock'],new Model());
   const handle=await host.agents.create({sessionId:'crash-root',meta:{cwd:folder},agentOptions:{provider:'mock',model:'mock'}}),agent=handle.agent;
   await call('bind_agent',{target:'root',session_id:agent.id,manager_id:null});
   await fs.writeFile(path.join(directory,'root-memory.md'),'SAVED_MEMORY');await call('save');
   const cp=new NativeCheckpoints(host,new Map([['root',{agent}]]),call);cp.ready=true;
   bridge.notifications.add(()=>cp.schedule());host.on('session/event',session=>{if(session===agent.session)cp.schedule();});
   agent.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'SAVED_REQUEST'}]}));await waiting;
   agent.steer(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'QUEUED_INPUT'}]}));
   const point=await cp.checkpoint();assert.ok(point,JSON.stringify(cp.status()));
   await fs.writeFile(path.join(folder,'position.json'),JSON.stringify(point));
   await fs.writeFile(path.join(directory,'root-memory.md'),'UNCOMMITTED_MEMORY');
   console.log('READY'); // Parent kills this process tree; no cancel(), dispose() or close().
 }else{
   const point=JSON.parse(await fs.readFile(path.join(folder,'position.json'),'utf8'));
   const latest=await call('persistence_latest_point');assert.equal(latest.id,point.id);
   const positions=new NativePositions(host),source=await positions.read(point.contexts.root);
   assert.ok(JSON.stringify(source.events).includes('SAVED_REQUEST'));assert.ok(JSON.stringify(source.events).includes('QUEUED_INPUT'));
   assert.ok(!source.events.some(event=>event.type==='turn/end'),'the saved model request really was in flight');
   const session=await positions.fork(point.contexts.root),target=path.join(folder,'restored');
   const result=await call('persistence_restore',{point_id:point.id,directory:target,sessions:{root:session}});
   assert.equal(result.executor_restore.status,'complete');assert.equal(await fs.readFile(path.join(target,'root-memory.md'),'utf8'),'SAVED_MEMORY');
   const read=await host.sessionPersistence.open(session,'read');try{
     const {events}=await read.read();assert.equal(read.inheritedEventCount,point.contexts.root.event_count);
     assert.ok(events.some(event=>event.type==='turn/end'&&event.data.reason.kind==='forked'));
     assert.ok(JSON.stringify(events).includes('SAVED_REQUEST'));
   }finally{await read.close();}
   await bridge.close();await host.fiber.dispose();clearInterval(keep);console.log('PASS hard-killed thinking process: native prefix and core memory recovered, incomplete turn closed, no inference or tool replay');
 }
})().catch(error=>{console.error(error);process.exit(1)});
