// Opt-in paid integration: five ticks, six NPCs; root is a deterministic test operator.
if(process.env.DATANET_LIVE_TEST!=='1')throw Error('Paid test requires DATANET_LIVE_TEST=1');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const base=path.resolve(__dirname,'..'),out=process.env.DATANET_LIVE_OUTPUT;
if(!out||!process.env.DATANET_LIVE_CREDENTIALS)throw Error('Explicit output and credential paths required');
const keepAlive=setInterval(()=>{},1000);let controller,host,r;
const deadline=setTimeout(()=>{console.error('30-minute hard deadline');process.exit(2)},30*60*1000);deadline.unref();
(async()=>{
 await fs.mkdir(out,{recursive:true});
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
 const adapter=new deepseek.DeepSeekAdapter({options:()=>connection,resolveAuth:async(c)=>{assert.equal(new URL(c.baseURL).origin,'https://api.deepseek.com');return {headers:{'x-dsh-auth-token':record.payload.token}}},resolveUserId:()=> 'nexarbor-npc-one-day',prepareExtensions:async()=>({fields:{},accept:async()=>{}})});
 host.llm.registerAdapter(['deepseek-account'],adapter);
 const evidence={started_at:new Date().toISOString(),ticks:[],requests:[],limits:{ticks:5,npcs:6,requestsPerActivity:16,totalRequests:240,minutes:30},route:{provider:'deepseek-account',model:'deepseek-flash',reasoningEffort:'high',maxTokens:50000,contextWindow:500000}};
 const originalFetch=globalThis.fetch;
 globalThis.fetch=async(url,init)=>{assert.equal(new URL(url).origin,'https://api.deepseek.com');if(evidence.requests.length>=240)throw Error('Paid request cap reached');const row={started_at:Date.now(),status:null};evidence.requests.push(row);try{const response=await originalFetch(url,init);row.status=response.status;return response}catch(error){row.error=String(error);throw error}};
 const entry=await load(base+'/extensions/npc_world/capabilities/scene_operator/entry.js');
 const work=path.join(out,'workspace');await fs.mkdir(work,{recursive:true});
 controller=await entry.apply(host,{workspace:work,storage:path.join(work,'.datanet'),backend:base+'/.venv/Scripts/python.exe',backendArgs:[base+'/adapters/harness/backend/server.py'],worldAllowFullRun:true,agentMaxTokens:50000,turnTimeoutMs:180000,modelRoute:evidence.route});
 const root=await host.agentLoop.create(native('dsh-session').SessionId('npc-day-'+Date.now()),evidence.route,{cwd:work});await host.parallel('agent/created',{agent:root});r=controller.runtimes.get(root.id);
 const exec=async(name,args={})=>{const result=await host.tools.execute({agent:root,name,arguments:args,callId:name+'-'+Date.now(),signal:new AbortController().signal});assert.equal(result.isError,false,JSON.stringify(result));return result.value};
 const persist=async()=>{
  const sessions={};for(const [actor,entry] of r.sessions){const a=entry.handle.agent;sessions[actor]={id:a.id,events:a.session.snapshotEvents(),messages:a.session.deriveMessages()}};
  await fs.writeFile(path.join(out,'sessions.json'),JSON.stringify(sessions,null,2));await fs.writeFile(path.join(out,'evidence.json'),JSON.stringify(evidence,null,2));
 };
 try{
  for(let tick=0;tick<5;tick++){
   const started=Date.now(),result=await exec('world_round',{timeout_seconds:180});
   const state=await exec('world_observe');evidence.ticks.push({tick,seconds:(Date.now()-started)/1000,result,state});await persist();
   console.log(JSON.stringify({tick,seconds:evidence.ticks.at(-1).seconds,requests:evidence.requests.length,status:result.pulse.status,activities:state.activities,places:Object.fromEntries(Object.entries(state.actors).map(([k,v])=>[k,v.place]))}));
   assert.equal(result.pulse.status,'completed','stop on incomplete tick; no extra day or silent retry');
   for(const a of Object.values(state.activities))assert.equal(a.status,'completed');
  }
  evidence.point=await r.checkpoints.checkpoint();evidence.finished_at=new Date().toISOString();evidence.passed=true;await persist();console.log('DAY_COMPLETE '+path.join(out,'evidence.json'));
 }catch(error){evidence.error=String(error);evidence.finished_at=new Date().toISOString();await persist();throw error}
})().then(async()=>{await controller?.components.dispose();await host?.fiber.dispose();clearInterval(keepAlive);clearTimeout(deadline)}).catch(async error=>{console.error(String(error));try{await controller?.components.dispose();await host?.fiber.dispose()}catch{}process.exit(1)});
