// 两种制作职责共享原生会话；仅登记宿主按工作副本授权的工具。
const readline=require('node:readline'),crypto=require('node:crypto'),toolContent=require('../runtime/tool-content.cjs');
let runtime,positions,closed=false;const sessions=new Map(),callbacks=new Map();let serial=0;const keep=setInterval(()=>{},1000);
const write=value=>process.stdout.write(JSON.stringify(value)+'\n');
const rpc=params=>new Promise((resolve,reject)=>{const host_id=String(++serial);callbacks.set(host_id,{resolve,reject});write({host_id,method:'maker-tool',params});});
async function create(p){
 const selected=await runtime.resolveModel(p.model_profile);
 if(p.resume_session&&p.model_signature!==selected.signature){const cursor=await positions.captureStored(p.resume_session);p={...p,fork_cursor:cursor,resume_session:undefined};}
 let id=p.resume_session;if(p.portable_prefix){await require('./portable-images.cjs').admitImages(runtime,p.portable_prefix);id=(await positions.importPrefix(p.portable_prefix,'maker-'+crypto.randomUUID())).session_id;}
 if(p.fork_cursor)id=await positions.fork(p.fork_cursor,'maker-'+crypto.randomUUID());
 const previous=sessions.get(id);if(previous?.running)throw Error('该会话正在运行');for(const dispose of previous?.tools??[])await dispose();if(typeof previous?.requestHook==='function')previous.requestHook();if(typeof previous?.prompt==='function')previous.prompt();
 const agent=previous?.agent??(id?(await runtime.host.agentLoop.resume(runtime.host,{resumeSessionId:id,agentOptions:selected.model})).agent:await runtime.host.agentLoop.create(runtime.native('dsh-session').SessionId('maker-'+crypto.randomUUID()),selected.model,{cwd:p.directory}));
 const entry={agent,supportsImages:selected.supportsImages!==false,task:p.task,tools:[],steps:0,updates:new Set(),start_seq:agent.session.seq,kind:p.kind,previews:previous?.previews??[]};sessions.set(agent.id,entry);
 runtime.host.sessionTitle.rename(agent.session,(p.kind==='network'?'网络预设制作':'模块／工具制作')+' · '+p.name);
 const skill=require('./network-skill.cjs');
 entry.prompt=agent.ctx.systemPrompt.section({name:'nexarbor-maker',order:90,interpolate:false,text:p.instructions});
 const register=original=>{const definition=structuredClone(original);if(definition.name==='view_network'&&!entry.supportsImages){definition.description+=' 当前模型使用紧凑拓扑索引。';definition.parameters.properties.image.default=false;}entry.tools.push(agent.ctx.tools.register({...definition,output:{schema:{},render:toolContent.render},execute:async args=>toolContent.prepare(runtime,await rpc({task:entry.task,tool:definition.name,arguments:definition.name==='view_network'&&!entry.supportsImages?{...args,image:false}:args}))}));};
 await skill.install(runtime,entry,p.tools,register);
 entry.requestHook=agent.ctx.on('agent/request',async(_p,next)=>{if(++entry.steps>(p.max_steps??100000))throw Error('制作已达到步骤上限');return next();});
 const cursor=await positions.capture(agent.session,{allowPending:true});return {session_id:agent.id,seed_cursor:cursor,model_signature:selected.signature,model_name:selected.model.model};
}
async function read(p){const e=sessions.get(p.session_id);if(!e)throw Error('会话尚未载入');const events=e.agent.session.snapshotEvents(e.start_seq).filter(v=>v.data?.usage).map(v=>({seq:v.seq,usage:v.data.usage}));return {session_id:e.agent.id,requests:e.steps,host_requests:runtime.requests(),steps:e.steps,messages:e.agent.session.deriveMessages().slice(-35),previews:[...(e.previews??[]),...Object.entries(await toolContent.previews(runtime,e.agent.session.deriveMessages().slice(-35))).map(([id,preview])=>({id,preview}))],events};}
async function run(p){
 const entry=sessions.get(p.session_id);if(!entry||entry.running)throw Error('会话不存在或正在执行');entry.running=true;const before=entry.agent.session.seq;let expired=false;
 const timer=setTimeout(()=>{expired=true;entry.acceptingUpdates=false;entry.agent.cancel('user');},p.timeout*1000);
 try{
  const input=await require('./message-content.cjs')(runtime,p);entry.previews=[...(entry.previews??[]),...input.previews];
  entry.agent.followup(runtime.createUserMessage({source:{kind:'user'},content:input.content}));entry.acceptingUpdates=true;await entry.agent.whenIdle();entry.acceptingUpdates=false;await entry.agent.whenIdle();await runtime.host.sessions.flush(entry.agent.session);
  const events=entry.agent.session.snapshotEvents(before),end=events.findLast(e=>e.type==='turn/end');
  return {...await read(p),status:!expired&&end?.data?.reason?.kind==='completed'?'completed':expired?'timeout':'failed',reason:end?.data?.reason,...(end?.data?.reason?.error?.code==='MALFORMED_RESPONSE'?{tool_input_errors:require('./malformed-tool.cjs')(events)}:{}),cursor:await positions.capture(entry.agent.session,{allowPending:true})};
 }finally{clearTimeout(timer);entry.acceptingUpdates=false;entry.running=false;}
}
function message(p){
 const entry=sessions.get(p.session_id);if(!entry)throw Error('会话尚未载入');
 if(typeof p.update_id!=='string'||!p.update_id||p.update_id.length>100||typeof p.prompt!=='string'||!p.prompt.trim()||p.prompt.length>17000)throw Error('追加消息格式无效');
 if(entry.updates.has(p.update_id))return {delivered:true,duplicate:true};
 if(!entry.running||!entry.acceptingUpdates)return {delivered:false,reason:'idle'};
 entry.updates.add(p.update_id);entry.agent.followup(runtime.createUserMessage({source:{kind:'user'},content:[{type:'text',text:p.prompt}]}));return {delivered:true};
}
async function handle(method,p){
 if(method==='init'){runtime=await require('./model-host.cjs')(p);positions=new(await runtime.loader.load(p.root+'/adapters/harness/framework/checkpoints.js')).NativePositions(runtime.host);return {ready:true,model:runtime.model};}
 if(method==='import-context'){await require('./portable-images.cjs').admitImages(runtime,p.prefix);return positions.importPrefix(p.prefix,'maker-'+crypto.randomUUID());}if(method==='export-context')return require('./portable-images.cjs').exportImages(runtime,await positions.exportPrefix(p.cursor));if(method==='create')return create(p);if(method==='run')return run(p);if(method==='message')return message(p);if(method==='read')return read(p);
 if(method==='inspect'){const stored=await positions.read(p.cursor);return {events:stored.events.filter(v=>v.data?.usage).map(v=>({seq:v.seq,usage:v.data.usage})),event_count:stored.events.length};}
 if(method==='cancel'){sessions.get(p.session_id)?.agent.cancel('user');return {ok:true};}if(method==='shutdown'){await close();return {ok:true};}throw Error('未知制作操作');
}
async function close(){if(closed)return;closed=true;for(const e of sessions.values())e.agent.cancel('user');await runtime?.host.fiber.dispose();clearInterval(keep);}
readline.createInterface({input:process.stdin}).on('line',line=>{let value;try{value=JSON.parse(line);}catch{return;}if(value.host_id){const cb=callbacks.get(value.host_id);if(cb){callbacks.delete(value.host_id);value.error?cb.reject(Error(value.error)):cb.resolve(value.result);}return;}Promise.resolve().then(()=>handle(value.method,value.params??{})).then(result=>write({id:value.id,result}),error=>write({id:value.id,error:runtime?.redact?runtime.redact(error):error.stack??String(error)}));}).on('close',()=>close().finally(()=>process.exit()));
