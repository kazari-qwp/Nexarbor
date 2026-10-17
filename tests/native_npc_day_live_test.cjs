// Opt-in paid integration: one day, four days, or isolated childbirth; deterministic root operator.
if(process.env.DATANET_LIVE_TEST!=='1')throw Error('Paid test requires DATANET_LIVE_TEST=1');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const base=path.resolve(__dirname,'..'),out=process.env.DATANET_LIVE_OUTPUT;
if(!out||!process.env.DATANET_LIVE_CREDENTIALS)throw Error('Explicit output and credential paths required');
const scenario=process.env.DATANET_NPC_SCENARIO??'one-day';
if(!['one-day','four-day','birth'].includes(scenario))throw Error('Unknown NPC scenario');
if(scenario==='birth'&&!process.env.DATANET_NPC_EXTENSION_ROOT)throw Error('Childbirth test requires an explicitly prepared isolated fixture extension');
const resuming=process.env.DATANET_NPC_RESUME==='1';
const tickCount=scenario==='four-day'?20:scenario==='birth'?2:5,requestCap=scenario==='four-day'?1400:scenario==='birth'?32:240;
const keepAlive=setInterval(()=>{},1000);let controller,host,r;
const deadline=setTimeout(()=>{console.error('30-minute hard deadline');process.exit(2)},30*60*1000);deadline.unref();
(async()=>{
 await fs.mkdir(out,{recursive:true});
 try{await fs.access(path.join(out,'evidence.json'));if(!resuming)throw Error('Refusing to overwrite an existing test result');}catch(error){if(error.code!=='ENOENT'||resuming)throw error;}
 const {native,load}=await require('./native_modules.cjs')();
 const nativeRoot=path.join(process.env.LOCALAPPDATA,'Programs/DeepSeek Harness/resources/app.asar/dsh/node_modules');
 const yaml=require(path.join(nativeRoot,'yaml'));
 const record=yaml.parse(await fs.readFile(process.env.DATANET_LIVE_CREDENTIALS,'utf8')).records['deepseek-account-platform/default'];
 assert.equal(record.kind,'grant');assert.equal(new URL(record.payload.issuer).origin,'https://platform.deepseek.com');
 assert.ok(record.payload.token&&!record.payload.token.startsWith('dsh_mock_'));
 const {Context}=native('cordis');host=new Context();
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry'],['dsh-skill','SkillRegistry']])await host.plugin(native(name)[service]??native(name).default);
 host.provide('sessionTitle',{rename(){}});
 await host.plugin(native('dsh-session-persistence-jsonl').default,{root:path.join(out,'native-logs')});
 const loop=await load(base+'/adapters/harness/runtime/agent-loop/lib/index.js');await host.plugin(loop.default,{agents:[]});
 const deepseek=native('dsh-llm-deepseek');
 const models=JSON.parse(await fs.readFile(base+'/in-history.patch.yml','utf8')).find(row=>row.id==='llm-deepseek').config.models;
 const connection=deepseek.resolveAdapterOptions({models,maxTokens:50000,retryPolicy:{mode:'normal',maxRetries:0},streamIdleTimeoutMs:60000});
 const adapter=new deepseek.DeepSeekAdapter({options:()=>connection,resolveAuth:async(c)=>{assert.equal(new URL(c.baseURL).origin,'https://api.deepseek.com');return {headers:{'x-dsh-auth-token':record.payload.token}}},resolveUserId:()=> 'nexarbor-npc-'+scenario,prepareExtensions:async()=>({fields:{},accept:async()=>{}})});
 host.llm.registerAdapter(['deepseek-account'],adapter);
 let evidence={scenario,started_at:new Date().toISOString(),ticks:[],requests:[],limits:{ticks:tickCount,npcs:scenario==='birth'?6:7,requestsPerActivity:16,totalRequests:requestCap,minutes:30},route:{provider:'deepseek-account',model:'deepseek-flash',reasoningEffort:'high',maxTokens:50000,contextWindow:500000}};
 if(resuming){
  evidence=JSON.parse(await fs.readFile(path.join(out,'evidence.json'),'utf8'));assert.equal(evidence.scenario,scenario);
  if(evidence.completed||evidence.ticks.length>=tickCount)throw Error('Test already completed; refusing a repeated run');
  evidence.interruptions??=[];evidence.interruptions.push({at:evidence.finished_at,ticks:evidence.ticks.length,error:evidence.error});
  evidence.activity_failures=evidence.ticks.flatMap(t=>Object.entries(t.result.activities).filter(([,a])=>a.status!=='completed').map(([actor,a])=>({tick:t.tick,actor,...a})));
  delete evidence.error;delete evidence.finished_at;
 }
 const originalFetch=globalThis.fetch;
 globalThis.fetch=async(url,init)=>{assert.equal(new URL(url).origin,'https://api.deepseek.com');if(evidence.requests.length>=requestCap)throw Error('Paid request cap reached');if(Date.now()-Date.parse(evidence.started_at)>=30*60*1000)throw Error('Total paid test deadline reached');const row={started_at:Date.now(),status:null};evidence.requests.push(row);try{const response=await originalFetch(url,init);row.status=response.status;return response}catch(error){row.error=String(error);throw error}};
 const entry=await load(base+'/extensions/npc_world/capabilities/scene_operator/entry.js');
 const work=path.join(out,'workspace');await fs.mkdir(work,{recursive:true});
 controller=await entry.apply(host,{workspace:work,storage:path.join(work,'.datanet'),backend:base+'/.venv/Scripts/python.exe',backendArgs:[base+'/adapters/harness/backend/server.py'],worldAllowFullRun:scenario!=='birth',...(process.env.DATANET_NPC_EXTENSION_ROOT?{extensionRoot:process.env.DATANET_NPC_EXTENSION_ROOT}:{}),agentMaxTokens:50000,turnTimeoutMs:180000,modelRoute:evidence.route});
 let root;
 if(resuming){
  const directories=await fs.readdir(path.join(work,'.datanet/networks'));assert.equal(directories.length,1);
  const id=evidence.root_session??Buffer.from(directories[0],'hex').toString('utf8');
  root=(await host.agentLoop.resume(host,{resumeSessionId:id,agentOptions:evidence.route})).agent;
 }else root=await host.agentLoop.create(native('dsh-session').SessionId('npc-'+scenario+'-'+Date.now()),evidence.route,{cwd:work});
 evidence.root_session=root.id;
 await host.parallel('agent/created',{agent:root});r=controller.runtimes.get(root.id);
 const exec=async(name,args={})=>{const result=await host.tools.execute({agent:root,name,arguments:args,callId:name+'-'+Date.now(),signal:new AbortController().signal});assert.equal(result.isError,false,JSON.stringify(result));return result.value};
 const persist=async()=>{
  const sessions={};for(const [actor,entry] of r.sessions){const a=entry.handle.agent;sessions[actor]={id:a.id,events:a.session.snapshotEvents(),messages:a.session.deriveMessages()}};
  await fs.writeFile(path.join(out,'sessions.json'),JSON.stringify(sessions,null,2));await fs.writeFile(path.join(out,'evidence.json'),JSON.stringify(evidence,null,2));
 };
 try{
  let newborn=evidence.newborn;
  if(resuming){const restored=await exec('world_observe');assert.equal(restored.clock.tick,evidence.ticks.at(-1).state.clock.tick,'resume must continue after the last completed tick');}
  for(let tick=evidence.ticks.length;tick<tickCount;tick++){
   const started=Date.now(),result=scenario==='birth'?await exec('world_run_npc',{target:tick===0?'world/npc/yue':newborn,timeout_ms:90000}):await exec('world_round',{timeout_seconds:180});
   const state=await exec('world_observe');evidence.ticks.push({tick,seconds:(Date.now()-started)/1000,result,state});
   console.log(JSON.stringify({tick,seconds:evidence.ticks.at(-1).seconds,requests:evidence.requests.length,status:result.pulse.status,activities:state.activities,places:Object.fromEntries(Object.entries(state.actors).map(([k,v])=>[k,v.place]))}));
   assert.equal(result.pulse.status,'completed','stop on incomplete tick; no extra day or silent retry');
   if(scenario==='birth'){
    if(tick===0){
     const children=Object.entries(state.actors).filter(([id,a])=>a.role==='child');assert.equal(children.length,1,'mother must create exactly one child');
     newborn=children[0][0];evidence.newborn=newborn;assert.equal(children[0][1].place,'world/place/hospital');
     for(const parent of ['world/npc/lin','world/npc/yue'])assert.deepEqual(state.actors[parent].children,[newborn]);
     assert.ok(!r.sessions.get(newborn)?.handle.agent.session.snapshotEvents().some(e=>e.type==='assistant/message'),'child must not act in its birth tick');
    }else{assert.equal(state.activities[newborn].status,'completed');assert.ok(r.sessions.get(newborn).handle.agent.session.snapshotEvents().some(e=>e.type==='assistant/message'),'new child must execute native AgentLoop');}
   }else{
    evidence.activity_failures??=[];
    for(const [actor,a] of Object.entries(result.activities))if(a.status!=='completed'){
     evidence.activity_failures.push({tick,actor,...a});
     if(scenario==='one-day')assert.equal(a.status,'completed');
    }
   }
   await persist();
  }
  evidence.point=await r.checkpoints.checkpoint();evidence.finished_at=new Date().toISOString();evidence.completed=true;evidence.passed=!evidence.activity_failures?.length;await persist();console.log('SCENARIO_COMPLETE '+scenario+' '+path.join(out,'evidence.json'));
 }catch(error){evidence.error=String(error);evidence.finished_at=new Date().toISOString();await persist();throw error}
})().then(async()=>{await controller?.components.dispose();await host?.fiber.dispose();clearInterval(keepAlive);clearTimeout(deadline)}).catch(async error=>{console.error(String(error));try{await controller?.components.dispose();await host?.fiber.dispose()}catch{}process.exit(1)});
