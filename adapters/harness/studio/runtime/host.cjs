// Optional, bounded native Agent executor. Only core-declared tools are registered.
const fs=require('node:fs/promises'),path=require('node:path'),readline=require('node:readline'),crypto=require('node:crypto');
const toolContent=require('./tool-content.cjs');
const callbacks=new Map(),agents=new Map();let next=0,host,native,config,history,permissions,createUserMessage,checkpoints,modelAdapters;
const keepAlive=setInterval(()=>{},1000),write=value=>process.stdout.write(JSON.stringify(value)+'\n');
const rpc=(method,params)=>new Promise((resolve,reject)=>{const host_id=String(++next);callbacks.set(host_id,{resolve,reject});write({host_id,method,params});});
const plain=value=>JSON.parse(JSON.stringify(value));
const user=(text,source={kind:'user'})=>createUserMessage({source,content:[{type:'text',text}]});
const agentRpc=(entry,method,params)=>{if(entry.retired)throw Error('Agent session was restored; this execution is retired');return rpc(method,{...params,executor_session_id:entry.agent.id,...(entry.ticket?{node_access_ticket:entry.ticket}:{})});};
let requestCount=0,started=Date.now(),closed=false;
async function init(p){
 config=p;const loader=await require('./loader.cjs')();native=loader.native;
 const {Context}=native('cordis');host=new Context();
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry'],['dsh-skill','SkillRegistry']])await host.plugin(native(name)[service]??native(name).default);
 if(native('dsh-tool-skill').inject.includes('workingDirectory')){await host.plugin(native('dsh-fs-local').LocalFileSystem,{cwd:p.directory});await host.plugin(native('dsh-working-directory').WorkingDirectoryService,{defaultDirectory:path.resolve(p.directory)});}
 await host.plugin(native('dsh-session-title').SessionTitleService,{fallbackMaxWords:12,fallbackMaxBytes:120,maxTitleBytes:256});
 await host.plugin(native('dsh-attachment-local').LocalAttachmentStore,{dshHome:p.directory});
 const optionsFile=path.join(p.directory,'native-model.json');let options={};try{options=JSON.parse(await fs.readFile(optionsFile,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
 const persistence=native('dsh-session-persistence-jsonl');await host.plugin(persistence.default??persistence,{root:options.native_logs??path.join(p.directory,'native-logs')});
 await host.plugin((await loader.load(p.root+'/adapters/harness/runtime/agent-loop/lib/index.js')).default,{agents:[]});
 modelAdapters=await require('./model-adapters.cjs')({host,native,root:p.root,credentials:p.credentials,defaults:options.model??{}});
 config.model={provider:'deepseek-account',model:'deepseek-flash',reasoningEffort:'low',maxTokens:16000,contextWindow:500000,...options.model};config.maxRequests=options.max_requests??240;config.maxSeconds=options.max_seconds??1200;
 const original=globalThis.fetch;globalThis.fetch=async(url,args)=>{if(++requestCount>config.maxRequests||Date.now()-started>config.maxSeconds*1000)throw Error('Native execution request budget reached');return original(url,args);};
 createUserMessage=native('dsh-llm').createUserMessage;
 const instructions=await loader.load(p.root+'/adapters/harness/framework/instructions.js'),tools=await loader.load(p.root+'/adapters/harness/framework/tool-permissions.js');history=new instructions.InstructionHistory(createUserMessage);permissions=new tools.ToolPermissions(createUserMessage);
 checkpoints=new (await loader.load(p.root+'/adapters/harness/framework/checkpoints.js')).NativeCheckpoints(host,agents,rpc);checkpoints.ready=true;
 return {ready:true,model:config.model,limits:{requests:config.maxRequests,seconds:config.maxSeconds}};
}
async function refresh(entry){
 if(entry.retired)throw Error('Agent session was restored; this execution is retired');
 if(entry.compacted){
  const referenced=[...new Set(entry.agent.session.deriveMessages().flatMap(m=>(m.content??[]).filter(b=>b.type==='tool-call').map(b=>b.name)))];
  const keep=new Set(await agentRpc(entry,'executor_prune',{actor:entry.actor,referenced}));
  for(const name of entry.definitions.keys())if(!keep.has(name))entry.definitions.delete(name);
  entry.compacted=false;
 }
 const view=await agentRpc(entry,'executor_prepare',{actor:entry.actor});entry.view=view;
 permissions.refusals(entry.agent.ctx,view.unavailable??{});
 const skillSignature=JSON.stringify((view.skill_bundles??[]).map(s=>[s.name,s.digest]));
 if(entry.skillSignature!==skillSignature){if(entry.skillLayer)for(const dispose of entry.skillLayer.tools)await dispose();entry.skillLayer={agent:entry.agent,tools:[]};await require('../../runtime/skills.cjs').mount({host,native},entry.skillLayer,view.skill_bundles??[]);entry.skillSignature=skillSignature;}
 const desired=new Set(view.tools.map(t=>t.name));
 for(const definition of view.retained_tools??[]){
  if(entry.definitions.has(definition.name))continue;
  entry.definitions.set(definition.name,JSON.stringify(definition));
  const dispose=permissions.register(entry.agent.ctx,{...definition,output:{schema:{},render:toolContent.render},execute:async args=>toolContent.prepare({host,native},await agentRpc(entry,'executor_invoke',{actor:entry.actor,name:definition.name,arguments:args}))});
  if(desired.has(definition.name))entry.tools.set(definition.name,dispose);else dispose();
 }
 for(const [name,dispose] of entry.tools)if(!desired.has(name)){dispose();entry.tools.delete(name);}
 for(const definition of view.tools){
  const signature=JSON.stringify(definition);if(entry.definitions.get(definition.name)===signature&&entry.tools.has(definition.name))continue;
  entry.tools.get(definition.name)?.();entry.definitions.set(definition.name,signature);
  entry.tools.set(definition.name,permissions.register(entry.agent.ctx,{...definition,output:{schema:{},render:toolContent.render},execute:async args=>toolContent.prepare({host,native},await agentRpc(entry,'executor_invoke',{actor:entry.actor,name:definition.name,arguments:args}))}));
 }
 for(const doc of view.context)history.load(entry.agent.ctx,doc.id,doc.text);
 const retained=new Set([...entry.agent.session.deriveMessages(),...entry.agent.inbox.nextStep,...entry.agent.inbox.nextTurn].map(m=>m.id));
 for(const event of view.inputs){
  const id=crypto.createHash('sha256').update(entry.actor+'\0'+event.source+'\0'+event.id).digest('hex');
  if(!retained.has(id))entry.agent.steer({...user(event.text,{kind:'nexarbor-input',source:event.source,event:event.id}),id});
 }
 if(view.inputs.length)await agentRpc(entry,'executor_ack',{actor:entry.actor,events:view.inputs.map(e=>({source:e.source,id:e.id}))});
 return view;
}
async function retire(entry){entry.retired=true;entry.agent.cancel('user');agents.delete(entry.actor);for(const dispose of entry.tools.values())dispose();if(entry.skillLayer)for(const dispose of entry.skillLayer.tools)await dispose();}
async function agentFor(p){
 const selected=await modelAdapters.resolve(p.model_profile);
 const existing=agents.get(p.actor);
 if(existing&&existing.modelSignature!==selected.signature){
  if(existing.running)throw Error('请等待当前 Agent 完成后切换模型');
  const cursor=await checkpoints.positions.capture(existing.agent.session,{allowPending:true}),id=await checkpoints.positions.fork(cursor,'nexarbor-model-'+crypto.randomUUID());
  await retire(existing);p={...p,session_id:id,context_cursor:await checkpoints.positions.captureStored(id),model_signature:selected.signature};
 }else if(!existing&&p.session_id&&p.model_signature!==selected.signature){
  const cursor=p.context_cursor??await checkpoints.positions.captureStored(p.session_id),id=await checkpoints.positions.fork(cursor,'nexarbor-model-'+crypto.randomUUID());
  p={...p,session_id:id,context_cursor:await checkpoints.positions.captureStored(id),model_signature:selected.signature};
 }
 if(agents.has(p.actor)){
  const current=agents.get(p.actor);
  if(!p.session_id||current.agent.id===p.session_id)return current;
  if(current.running)throw Error('请等待当前 Agent 完成后切换上下文分支');
  await retire(current);
 }
 const scope=crypto.createHash('sha256').update(config.directory+'\0'+p.actor).digest('hex').slice(0,24);let id=p.session_id||'nexarbor-'+scope,cursor=p.context_cursor;
 if(cursor){
  const head=await checkpoints.positions.captureStored(id);
  if(head.event_count!==cursor.event_count||head.prefix_hash!==cursor.prefix_hash){id=await checkpoints.positions.fork(cursor);cursor=await checkpoints.positions.captureStored(id);}
 }
 let agent;
 try{agent=(await host.agentLoop.resume(host,{resumeSessionId:id,agentOptions:selected.model})).agent;}
 catch(error){if(!/not found|ENOENT|does not exist/i.test(String(error)))throw error;agent=await host.agentLoop.create(native('dsh-session').SessionId(id),selected.model,{cwd:config.directory});}
 const entry={actor:p.actor,agent,modelSignature:selected.signature,tools:new Map(),definitions:new Map(),view:{},steps:0,maxSteps:12,ticket:p.node_access_ticket};agents.set(p.actor,entry);
 host.sessionTitle.rename(agent.session,p.name);
 history.bind(agent.ctx,agent);permissions.bind(agent.ctx,agent);
 agent.ctx.on('session/event',(session,event)=>{if(session===agent.session){if(event.type==='compaction/end'&&!event.data?.error)entry.compacted=true;checkpoints.schedule();}});
 agent.ctx.systemPrompt.section({name:'nexarbor:assembled',order:90,interpolate:false,text:()=>[entry.view.system_prompt??'',...(entry.view.skill_errors??[]).map(s=>'Skill '+s.id+' 暂不可用：'+s.error)].join('\n')});
 agent.ctx.on('agent/prepare-context',()=>refresh(entry));
 agent.ctx.on('agent/request-tail',async(_p,next)=>[...await next(),...(entry.view.tail??[]).map(text=>({role:'user',content:[{type:'text',text}]}))]);
 agent.ctx.on('agent/request',async(_p,next)=>{if(++entry.steps>entry.maxSteps)throw Error('Agent step budget reached');return next();});
 await agentRpc(entry,'executor_bind',{actor:p.actor,session_id:agent.id,model_signature:selected.signature,...(cursor?{context_cursor:cursor}:{})});checkpoints.schedule();
 return entry;
}
async function run(p){
 const entry=await agentFor(p);if(entry.running)throw Error('Agent already running');entry.running=true;entry.ticket=p.node_access_ticket;entry.steps=0;entry.maxSteps=p.max_steps;
 const before=entry.agent.session.seq;let expired=false;const timer=setTimeout(()=>{expired=true;entry.agent.cancel('user');},p.timeout_seconds*1000);
 try{
  await refresh(entry);entry.agent.followup(user(p.message||'请处理当前请求。'));await entry.agent.whenIdle();
  const ending=entry.agent.session.snapshotEvents(before).findLast(e=>e.type==='turn/end');
  const status=!expired&&ending?.data.reason.kind==='completed'?'completed':expired?'timeout':'failed';
  await host.sessions.flush(entry.agent.session);
  await checkpoints.checkpoint();
  const messages=entry.agent.session.deriveMessages();
  await fs.writeFile(path.join(config.directory,'native-sessions.json'),JSON.stringify([...agents.values()].map(e=>({actor:e.actor,session_id:e.agent.id,title:host.sessionTitle.get(e.agent.session).title,events:e.agent.session.seq})),null,2));
  return {status,session_id:entry.agent.id,steps:entry.steps,output:messages.filter(m=>m.role==='assistant').at(-1)?.content.filter(b=>b.type==='text').map(b=>b.text).join('\n')??'',error:status==='completed'?null:JSON.stringify(ending?.data.reason),requests:requestCount};
 }finally{clearTimeout(timer);entry.running=false;entry.ticket=null;await host.sessions.flush(entry.agent.session);}
}
async function close(){if(closed)return;closed=true;for(const e of agents.values())e.agent.cancel('user');try{await checkpoints?.checkpoint();}catch{}await checkpoints?.stop();await host?.fiber.dispose();clearInterval(keepAlive);}
async function captureContexts(p){
 if(p.requireIdle&&[...agents.values()].some(e=>e.running))throw Error('请等待当前 Agent 完成后保存上下文');
 const result={};
 for(const [actor,id] of Object.entries(p.bindings)){
  let entry=agents.get(actor);
  if(entry&&entry.agent.id!==id){if(entry.running)throw Error('Agent binding changed during context capture');await retire(entry);entry=null;}
  result[actor]=entry?await checkpoints.positions.capture(entry.agent.session,{allowPending:true}):await checkpoints.positions.captureStored(id);
 }
 return result;
}
async function restoreContexts(p){
 const contexts={};
 for(const [actor,cursor] of Object.entries(p.contexts)){
  const entry=agents.get(actor);
  const restored=await checkpoints.positions.restore(cursor,entry?.agent.session,{onDiverged:()=>{if(entry)void retire(entry);}});contexts[actor]=restored.cursor;
 }
 return {contexts};
}
readline.createInterface({input:process.stdin}).on('line',line=>{
 let value;try{value=JSON.parse(line);}catch{return;}
 if(value.host_id){const p=callbacks.get(value.host_id);if(p){callbacks.delete(value.host_id);value.error?p.reject(Error(value.error)):p.resolve(value.result);}return;}
 Promise.resolve().then(()=>value.method==='init'?init(value.params):value.method==='shutdown'?close().then(()=>({ok:true})):value.method==='core-commit'?(checkpoints?.schedule(),{ok:true}):value.method==='agent-context-capture'?captureContexts(value.params):value.method==='agent-context-restore'?restoreContexts(value.params):value.method==='agent-run'?run(value.params):value.method==='agent-read'?agentFor(value.params).then(async e=>{const messages=e.agent.session.deriveMessages();return {session_id:e.agent.id,status:e.running?'running':'idle',messages,previews:await toolContent.previews({host,native},messages)};}):value.method==='agent-cancel'?(agents.get(value.params.actor)?.agent.cancel('user'),{ok:true}):Promise.reject(Error('Unknown native operation'))).then(result=>write({id:value.id,result}),error=>write({id:value.id,error:modelAdapters?modelAdapters.redact(error):String(error.stack??error)}));
}).on('close',()=>close().finally(()=>process.exit()));
