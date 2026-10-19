// 两种制作职责共享原生会话；仅登记宿主按工作副本授权的工具。
const readline=require('node:readline'),crypto=require('node:crypto');
let runtime,positions,closed=false;const sessions=new Map(),callbacks=new Map();let serial=0;const keep=setInterval(()=>{},1000);
const write=value=>process.stdout.write(JSON.stringify(value)+'\n');
const rpc=params=>new Promise((resolve,reject)=>{const host_id=String(++serial);callbacks.set(host_id,{resolve,reject});write({host_id,method:'maker-tool',params});});
async function create(p){
 let id=p.resume_session;if(p.portable_prefix){await require('./portable-images.cjs').admitImages(runtime,p.portable_prefix);id=(await positions.importPrefix(p.portable_prefix,'maker-'+crypto.randomUUID())).session_id;}
 if(p.fork_cursor)id=await positions.fork(p.fork_cursor,'maker-'+crypto.randomUUID());
 const previous=sessions.get(id);if(previous?.running)throw Error('该会话正在运行');for(const dispose of previous?.tools??[])dispose();if(typeof previous?.requestHook==='function')previous.requestHook();if(typeof previous?.prompt==='function')previous.prompt();
 const agent=previous?.agent??(id?(await runtime.host.agentLoop.resume(runtime.host,{resumeSessionId:id,agentOptions:runtime.model})).agent:await runtime.host.agentLoop.create(runtime.native('dsh-session').SessionId('maker-'+crypto.randomUUID()),runtime.model,{cwd:p.directory}));
 const entry={agent,task:p.task,tools:[],steps:0,start_seq:agent.session.seq,kind:p.kind,previews:previous?.previews??[]};sessions.set(agent.id,entry);
 runtime.host.sessionTitle.rename(agent.session,(p.kind==='network'?'网络预设制作':'模块／工具制作')+' · '+p.name);
 entry.prompt=agent.ctx.systemPrompt.section({name:'nexarbor-maker',order:90,interpolate:false,text:p.instructions});
 for(const definition of p.tools)entry.tools.push(agent.ctx.tools.register({...definition,output:{schema:{},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]},execute:args=>rpc({task:entry.task,tool:definition.name,arguments:args})}));
 entry.requestHook=agent.ctx.on('agent/request',async(_p,next)=>{if(++entry.steps>(p.max_steps??70))throw Error('制作已达到步骤上限');return next();});
 const cursor=await positions.capture(agent.session,{allowPending:true});return {session_id:agent.id,seed_cursor:cursor};
}
async function read(p){const e=sessions.get(p.session_id);if(!e)throw Error('会话尚未载入');const events=e.agent.session.snapshotEvents(e.start_seq).filter(v=>v.data?.usage).map(v=>({seq:v.seq,usage:v.data.usage}));return {session_id:e.agent.id,requests:e.steps,host_requests:runtime.requests(),steps:e.steps,messages:e.agent.session.deriveMessages().slice(-35),previews:e.previews??[],events};}
async function run(p){
 const entry=sessions.get(p.session_id);if(!entry||entry.running)throw Error('会话不存在或正在执行');entry.running=true;const before=entry.agent.session.seq;let expired=false;
 const timer=setTimeout(()=>{expired=true;entry.agent.cancel('user');},p.timeout*1000);
 try{
  const input=await require('./message-content.cjs')(runtime,p);entry.previews=[...(entry.previews??[]),...input.previews];
  entry.agent.followup(runtime.createUserMessage({source:{kind:'user'},content:input.content}));await entry.agent.whenIdle();await runtime.host.sessions.flush(entry.agent.session);
  const end=entry.agent.session.snapshotEvents(before).findLast(e=>e.type==='turn/end');
  return {...await read(p),status:!expired&&end?.data.reason.kind==='completed'?'completed':expired?'timeout':'failed',reason:end?.data.reason,cursor:await positions.capture(entry.agent.session,{allowPending:true})};
 }finally{clearTimeout(timer);entry.running=false;}
}
async function handle(method,p){
 if(method==='init'){runtime=await require('./model-host.cjs')(p);positions=new(await runtime.loader.load(p.root+'/adapters/harness/framework/checkpoints.js')).NativePositions(runtime.host);return {ready:true,model:runtime.model};}
 if(method==='import-context'){await require('./portable-images.cjs').admitImages(runtime,p.prefix);return positions.importPrefix(p.prefix,'maker-'+crypto.randomUUID());}if(method==='export-context')return require('./portable-images.cjs').exportImages(runtime,await positions.exportPrefix(p.cursor));if(method==='create')return create(p);if(method==='run')return run(p);if(method==='read')return read(p);
 if(method==='inspect'){const stored=await positions.read(p.cursor);return {events:stored.events.filter(v=>v.data?.usage).map(v=>({seq:v.seq,usage:v.data.usage})),event_count:stored.events.length};}
 if(method==='cancel'){sessions.get(p.session_id)?.agent.cancel('user');return {ok:true};}if(method==='shutdown'){await close();return {ok:true};}throw Error('未知制作操作');
}
async function close(){if(closed)return;closed=true;for(const e of sessions.values())e.agent.cancel('user');await runtime?.host.fiber.dispose();clearInterval(keep);}
readline.createInterface({input:process.stdin}).on('line',line=>{let value;try{value=JSON.parse(line);}catch{return;}if(value.host_id){const cb=callbacks.get(value.host_id);if(cb){callbacks.delete(value.host_id);value.error?cb.reject(Error(value.error)):cb.resolve(value.result);}return;}Promise.resolve().then(()=>handle(value.method,value.params??{})).then(result=>write({id:value.id,result}),error=>write({id:value.id,error:error.stack??String(error)}));}).on('close',()=>close().finally(()=>process.exit()));
