const keepAlive=setInterval(()=>{},1000);setTimeout(()=>{console.error('Test deadline');process.exit(1)},60000).unref();
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL,fileURLToPath}=require('node:url');
const nativeRoot=process.env.DATANET_NATIVE_MODULES??path.join(process.env.LOCALAPPDATA,'Programs','DeepSeek Harness','resources','app.asar','dsh','node_modules');
const productRoot=path.resolve(__dirname,'..');
const testRoot=process.env.DATANET_TEST_TEMP??path.join(productRoot,'build','test-data');
require('node:fs').mkdirSync(testRoot,{recursive:true});
const native=name=>require(path.join(nativeRoot,'@deepseek-ai',name)),{Context}=native('cordis');
const base=productRoot;
(async()=>{
 const cache=new Map(),context=vm.createContext({process,console,Buffer,URL,AbortController,AbortSignal,structuredClone,setTimeout,clearTimeout,setInterval,clearInterval,Symbol});
 const synthetic=(ns,id)=>{const keys=[...new Set([...Object.keys(ns),'default'])];return new vm.SyntheticModule(keys,function(){for(const key of keys)this.setExport(key,key==='default'?(ns.default??ns):ns[key])},{context,identifier:id})};
 async function get(spec,parent){
  const file=spec.startsWith('file:')?fileURLToPath(spec):spec.startsWith('.')?path.resolve(path.dirname(fileURLToPath(parent)),spec):null,key=file??spec;if(cache.has(key))return cache.get(key);
  if(file?.replaceAll('\\','/').endsWith('framework/capabilities.js')){const mod=synthetic({applyCapabilities:async()=>({officialPreset:'standard'}),updateCapabilityTools:()=>({})},key);cache.set(key,mod);return mod;}
  if(!file){const ns=spec.startsWith('@deepseek-ai/')?native(spec.slice(13)):spec==='zod'?require(path.join(nativeRoot,'zod')):await import(spec);const mod=synthetic(ns,key);cache.set(key,mod);return mod;}
  const mod=new vm.SourceTextModule(await fs.readFile(file,'utf8'),{context,identifier:pathToFileURL(file).href,initializeImportMeta:m=>m.url=pathToFileURL(file).href,importModuleDynamically:async(spec,ref)=>{const m=await get(spec,ref.identifier);if(m.status==='unlinked')await m.link(link);if(m.status==='linked')await m.evaluate();return m}});cache.set(key,mod);return mod;
 }
 const link=(spec,ref)=>get(spec,ref.identifier),entry=await get(pathToFileURL(base+'/adapters/harness/framework/adapter.js').href);await entry.link(link);await entry.evaluate();
 const loop=await get(pathToFileURL(base+'/adapters/harness/runtime/agent-loop/lib/index.js').href);await loop.link(link);await loop.evaluate();
 const host=new Context(),temp=await fs.mkdtemp(path.join(testRoot,'creation-'));
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']]){await host.plugin(native(name)[service]??native(name).default);}
 host.provide('sessionTitle',{rename(){}});host.sessions.flush=async()=>{};
 await host.plugin(loop.namespace.default,{agents:[]});
 const controller=await entry.namespace.createAdapter(host,{workspace:temp,storage:path.join(temp,'.datanet'),...(process.env.DATANET_TEST_PYTHON?{backend:process.env.DATANET_TEST_PYTHON,backendArgs:[process.env.DATANET_TEST_BACKEND_ENTRY??base+'/adapters/harness/backend/server.py']}:{}),modelRoute:{provider:'mock-native',model:'native-flash'},rootNetwork:'project_root',rootToolboxes:['network_access','node_creation','agent_management','agent_delegation','interface_management','discussion'],maxSignalStrength:100});
 const llm=native('dsh-llm');
 const spill=path.join(temp,'terminal-output.txt'),full='START\n'+'line\n'.repeat(5000)+'END\n';
 await fs.writeFile(spill,full);
 host.tools.register({name:'pwsh',description:'Mock terminal result fixture',parameters:{type:'object',properties:{}},output:{schema:{type:'object'},render:()=>[{type:'text',text:'tail'}]},execute:()=>({stdout:{text:'tail',truncated:true,spillPath:spill},stderr:{text:'',truncated:false},exitCode:0})});

 class Model extends llm.LlmAdapter {
  requests=[]; steps=new Map();
  async resolveModel(provider,id){return {provider,id,name:id,toolUpdate:'addition-only',systemPromptUpdate:'in-history'};}
  async *stream(options){
   this.requests.push(options);
   const all=options.messages.flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).join('\n');
   const actor=all.match(/所属节点为 (native\/worker_\d+)/)?.[1];
   const discussionActor=all.match(/所属节点：(discussion\/(?:leader|recorder|member_\d+))/)?.[1];
   const tail=options.messages.flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).findLast(t=>t.startsWith('[协作状态：native]'));
   const state=tail?JSON.parse(tail.slice(tail.indexOf('\n')+1)):null;
   let call;
   if(discussionActor){
    const latest=options.messages.filter(m=>m.role==='user').flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).findLast(t=>t.includes('项目任务：')||t.startsWith('讨论已结束。'));
    const lastCall=options.messages.findLast(m=>m.role==='assistant')?.content.find(b=>b.type==='tool-call');
    const finalIndex=options.messages.findLastIndex(m=>m.role==='user'&&m.content.some(b=>b.type==='text'&&b.text.startsWith('讨论已结束。')));
    const alreadyWritten=lastCall?.name==='node_write'&&options.messages.findLastIndex(m=>m.role==='assistant')>finalIndex;
    if(latest?.startsWith('讨论已结束。')){if(!alreadyWritten)call={name:'node_write',arguments:{target:'discussion/output',key:'content',value:latest.match(/任务“([^”]+)”/)?.[1]+'成果'}};}
    else call={name:'submit_round',arguments:{content:'本次任务测试'}};
   }
   if(actor&&state?.phase!=='completed'){
    const key=actor+':'+state?.run_id,step=this.steps.get(key)??0;this.steps.set(key,step+1);
    if(actor.endsWith('worker_1')&&step===0)call={name:'pwsh',arguments:{}};
    else if(actor.endsWith('worker_1')&&!state?.candidate)call={name:'datanet_team_finish',arguments:{action:'propose',content:'native cooperation passed '+state.run_id,evidence:'最小模拟验收'}};
    else if(actor.endsWith('worker_2')&&state?.candidate)call={name:'datanet_team_finish',arguments:{action:'approve',candidate_id:state.candidate.id,evidence:'共同状态与候选已读取'}};
    else call={name:'datanet_team_status',arguments:{}};
   }
   const block=call?{type:'tool-call',id:'native-'+this.requests.length,name:call.name,arguments:JSON.stringify(call.arguments)}:{type:'text',text:'完成'};
   yield {type:'block-start',index:0,blockType:block.type};
   if(!call)yield {type:'text-delta',index:0,text:block.text};
   yield {type:'block-end',index:0,block};
   yield {type:'usage',usage:{inputTokens:10,outputTokens:2}};
   yield {type:'finish',reason:{kind:'stop'}};
  }
 }
 const model=new Model();host.llm.registerAdapter(['mock','mock-native'],model);
 const invariant=await get(pathToFileURL(base+'/adapters/harness/runtime/agent-loop/lib/invariant.js').href);await invariant.link(link);await invariant.evaluate();
 await host.plugin(native('dsh-invariants').InvariantRegistry);await host.plugin(invariant.namespace);
 const root=await host.agentLoop.create(native('dsh-session').SessionId('cooperation-root'),{provider:'mock',model:'mock'},{cwd:temp});
 await host.parallel('agent/created',{agent:root});
 const r=controller.runtimes.get(root.id);
 const exec=async(name,args={})=>{const result=await host.tools.execute({agent:root,name,arguments:args,callId:'test-'+name,signal:new AbortController().signal});if(result.isError)await fs.writeFile(path.join(productRoot,'build','cooperation-native-failure.json'),JSON.stringify({name,args,result,requests:model.requests,sessions:[...r.sessions].map(([id,s])=>({id,messages:s.handle.agent.session.deriveMessages()}))},null,2));assert.equal(result.isError,false,JSON.stringify(result));return result.value};
 await exec('datanet_create_network_channel',{preset:'discussion_group'});
 const discussion=await exec('datanet_create_network',{preset:'discussion_group',instance_id:'discussion',project:'动态人数',member_count:1,rounds:1});
 assert.equal(discussion.members.length,3);
 const discussionSessions=discussion.members.map(m=>r.sessions.get(m).handle.agent.id);
 const d1=await exec('datanet_discuss',{group_id:'discussion',task:'讨论任务一'});
 const d2=await exec('datanet_discuss',{group_id:'discussion',task:'讨论任务二'});
 assert.notEqual(d1.run_id,d2.run_id);assert.equal(d1.output[0].content,'讨论任务一成果');assert.equal(d2.output[0].content,'讨论任务二成果');
 assert.deepEqual(discussion.members.map(m=>r.sessions.get(m).handle.agent.id),discussionSessions);
 await exec('datanet_create_network_channel',{preset:'decentralized_group'});
 const group=await exec('datanet_create_network',{preset:'decentralized_group',instance_id:'native',project:'最小原生协作通路测试',member_count:2});
 assert.equal(group.members.length,2);
 for(const member of group.members){const agent=r.sessions.get(member).handle.agent;assert.ok(host.tools.schemas(agent).some(t=>t.name==='datanet_team_finish'));assert.ok(host.tools.schemas(agent).some(t=>t.name==='datanet_team_send'));}
 const receipt=await exec('datanet_cooperate',{group_id:'native',action:'start',task:'提交并共同验收模拟成果',budget_minutes:1});assert.equal(receipt.status,'accepted');
 let state;const deadline=Date.now()+20000;
 do{await new Promise(resolve=>setTimeout(resolve,50));state=await exec('datanet_cooperate',{group_id:'native',action:'status'});}while(['running','review'].includes(state.phase)&&Date.now()<deadline);
 assert.equal(state.phase,'completed',JSON.stringify(state));
 assert.equal(state.candidate.review.execution_log_count,1);
 const manifest=JSON.parse(await fs.readFile(state.candidate.review.manifest_path,'utf8'));
 const saved=JSON.parse(await fs.readFile(manifest.execution_logs[0].path,'utf8'));
 assert.equal(saved.streams.stdout.text,full);
 const firstRun=state.run_id,firstArchive=state.archive_path,peerSessions=group.members.map(m=>r.sessions.get(m).handle.agent.id);
 // Restart immediately, while the final native tools/delegations may still be draining.
 const second=await exec('datanet_cooperate',{group_id:'native',action:'start',task:'第二个模拟任务',budget_minutes:1});
 assert.notEqual(second.run_id,firstRun);
 const secondDeadline=Date.now()+20000;
 do{await new Promise(resolve=>setTimeout(resolve,50));state=await exec('datanet_cooperate',{group_id:'native',action:'status'});}while(['running','review'].includes(state.phase)&&Date.now()<secondDeadline);
 assert.equal(state.phase,'completed',JSON.stringify(state));assert.equal(state.run_id,second.run_id);
 assert.deepEqual(group.members.map(m=>r.sessions.get(m).handle.agent.id),peerSessions);
 assert.ok(state.runs[firstRun]);
 const oldOutput=await fs.readFile(path.resolve(state.workspace,'../../..',firstArchive,'output.md'),'utf8');assert.ok(oldOutput.includes(firstRun));assert.ok(!oldOutput.includes(second.run_id));
 for(const member of group.members)await r.sessions.get(member).handle.agent.whenIdle();
 await root.whenIdle();
 for(const id of Object.values(state.jobs)){const settled=await exec('datanet_wait_agent',{delegation_id:id,timeout_ms:10000});assert.equal(settled.status,'completed',JSON.stringify(settled));}
 const notifications=root.session.deriveMessages().filter(m=>JSON.stringify(m).includes('cooperation_result'));assert.equal(notifications.length,2);
 assert.ok(root.session.deriveMessages().some(m=>JSON.stringify(m).includes('cooperation_result')));
 assert.ok(model.requests.some(request=>request.messages.at(-1)?.content.some(b=>b.type==='text'&&b.text.startsWith('[协作状态：native]'))));
 for(const member of group.members){const agent=r.sessions.get(member).handle.agent;assert.ok(!agent.session.deriveMessages().some(m=>m.content.some(b=>b.type==='text'&&b.text.startsWith('[协作状态：native]'))));}
 const out=await r.bridge.call('read',{actor:'root',target:state.entry_points.output,request:{method:'key',key:'content'},strength:100});assert.match(out.items[0].content,/native cooperation passed/);
 // Exercise the actual request middleware, native system updates and native additions.
 assert.ok(model.requests.length>0);
 assert.ok(model.requests.every(request=>request.provider==='mock-native'&&request.model==='native-flash'));
 let version='CACHE_SYSTEM_A';
 root.ctx.systemPrompt.section({name:'cache-probe',order:95,text:()=>version});
 const followup=async text=>{root.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text}]}));await root.whenIdle();};
 await followup('cache baseline');
 const baseline=model.requests.at(-1),firstSystem=baseline.messages.find(m=>m.role==='system');
 assert.ok(baseline.messages.filter(m=>m.role==='system').at(-1).content.some(b=>b.type==='text'&&b.text.includes('CACHE_SYSTEM_A')));
 version='CACHE_SYSTEM_B';
 host.tools.register({name:'cache_probe_added',description:'Native addition fixture',parameters:{type:'object',properties:{}},output:{schema:{},render:()=>[{type:'text',text:'ok'}]},execute:()=>({ok:true})});
 await followup('cache update');
 const updated=model.requests.at(-1);
 assert.deepEqual(updated.messages.find(m=>m.role==='system'),firstSystem);
 assert.ok(updated.messages.filter(m=>m.role==='system').at(-1).content.some(b=>b.type==='text'&&b.text.includes('CACHE_SYSTEM_B')));
 assert.ok(updated.messages.some(m=>m.role==='developer'&&m.content.some(b=>b.type==='tool-addition')));
 assert.ok(updated.tools.some(t=>t.name==='cache_probe_added'));
 await controller.components.disable('network_presets/decentralized_group');
 const revoked=await host.tools.execute({agent:root,name:'datanet_cooperate',arguments:{group_id:'native',action:'status'},callId:'revoked',signal:new AbortController().signal});assert.equal(revoked.isError,true);assert.ok(host.tools.schemas(root).some(t=>t.name==='datanet_cooperate'));
 await followup('after revocation');
 assert.ok(!model.requests.at(-1).messages.some(m=>m.role==='developer'&&m.content.some(b=>b.type==='tool-removal')));
 await controller.components.dispose();await host.fiber.dispose();clearInterval(keepAlive);
 console.log('PASS native Harness: two tasks on each group, preserved sessions, isolated runs and archives, automatic root results, component revocation, native route and append-only system/tool updates; mock model only');
})().catch(error=>{console.error(error);process.exit(1)});
