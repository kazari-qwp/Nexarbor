const keepAlive=setInterval(()=>{},1000);setTimeout(()=>{console.error('Test deadline');process.exit(1)},120000).unref();
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
 const link=(spec,ref)=>get(spec,ref.identifier),entry=await get(pathToFileURL(base+'/extensions/npc_world/capabilities/scene_operator/entry.js').href);await entry.link(link);await entry.evaluate();
 const loop=await get(pathToFileURL(base+'/adapters/harness/runtime/agent-loop/lib/index.js').href);await loop.link(link);await loop.evaluate();
 const host=new Context(),temp=process.env.DATANET_TEST_OUTPUT?path.resolve(process.env.DATANET_TEST_OUTPUT):await fs.mkdtemp(path.join(testRoot,'creation-'));
 await fs.mkdir(temp,{recursive:true});
 if(process.env.DATANET_TEST_OUTPUT){try{await fs.access(path.join(temp,'sessions-manifest.json'));throw new Error('Refusing to overwrite an existing test run')}catch(error){if(error.code!=='ENOENT')throw error;}}
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']]){await host.plugin(native(name)[service]??native(name).default);}
 await host.plugin(native('dsh-session-title').SessionTitleService,{fallbackMaxWords:12,fallbackMaxBytes:120,maxTitleBytes:256});
 const durable=process.env.DATANET_DURABLE_TEST==='1';
 if(durable)await host.plugin(native('dsh-session-persistence-jsonl').default,{root:path.join(temp,'native-logs')});else host.sessions.flush=async()=>{};
 await host.plugin(loop.namespace.default,{agents:[]});

 const controller=await entry.namespace.apply(host,{workspace:temp,storage:path.join(temp,'.datanet'),backend:process.env.DATANET_TEST_PYTHON??base+'/.venv/Scripts/python.exe',backendArgs:[base+'/adapters/harness/backend/server.py'],worldAllowFullRun:false,worldMaxRequests:8,agentMaxTokens:4096});
 const llm=native('dsh-llm');
 class Model extends llm.LlmAdapter {
  requests=[];fail=false;
  async resolveModel(provider,id){return {provider,id,name:id,toolUpdate:'addition-only',systemPromptUpdate:'in-history'};}
  async *stream(options){
   if(this.catalogMode){
    const block={type:'text',text:'本次会话列表检查结束。'};
    yield {type:'block-start',index:0,blockType:block.type};yield {type:'text-delta',index:0,text:block.text};yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'stop'}};return;
   }
   if(this.directMoveMode){
    const step=this.directMoveRequests++;
    assert.ok(step<3,'move and trade must finish in three requests');
    let block;
    if(step===2)block={type:'text',text:'已到商店卖出木材，本时刻活动结束。'};
    else {
     const prefix=step===0?'near_move_here_':'near_trade_';
     const tool=options.tools.find(t=>(t.function?.name??t.name).startsWith(prefix)&&(step!==0||(t.function?.description??t.description).startsWith('商店：')));
     assert.ok(tool,'new place tools must be available after moving');
     block={type:'tool-call',id:'direct-'+step,name:tool.function?.name??tool.name,arguments:JSON.stringify(step===0?{}:{side:'sell',item:'wood',quantity:1})};
    }
    yield {type:'block-start',index:0,blockType:block.type};
    if(block.type==='text')yield {type:'text-delta',index:0,text:block.text};
    yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'stop'}};return;
   }
   if(this.movementMode){
    const step=this.movementRequests++;assert.ok(step<4,'bad move, valid move, work and normal finish');
    if(step===3){
     const block={type:'text',text:'移动后砍树完成，本时刻活动结束。'};
     yield {type:'block-start',index:0,blockType:block.type};yield {type:'text-delta',index:0,text:block.text};yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'stop'}};return;
    }
    const prefix=step===2?'near_chop_':'near_move_here_';
    const tool=options.tools.find(t=>(t.function?.name??t.name).startsWith(prefix)&&(step===2||(t.function?.description??t.description).startsWith('树林：')));
    assert.ok(tool,'movement must refresh local tools within the same tick');const name=tool.function?.name??tool.name;
    const plans=step===0?[{name,arguments:{unexpected:true}}]:step===1?[{name,arguments:{}},{name,arguments:{}}]:[{name,arguments:{}}];
    for(const [index,call] of plans.entries()){
     const block={type:'tool-call',id:'move-'+step+'-'+index,name:call.name,arguments:JSON.stringify(call.arguments)};
     yield {type:'block-start',index,blockType:block.type};yield {type:'block-end',index,block};
    }
    yield {type:'finish',reason:{kind:'stop'}};return;
   }
   if(this.checkpointMode){
    const block=this.checkpointRequests++===0?{type:'tool-call',id:'full-save-tool',name:'world_observe',arguments:'{}'}:{type:'text',text:'Checkpoint tool complete.'};
    yield {type:'block-start',index:0,blockType:block.type};
    if(block.type==='text')yield {type:'text-delta',index:0,text:block.text};
    yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'stop'}};return;
   }
   this.requests.push(options);
   if(this.fail)throw new Error('simulated native Agent failure');
   assert.ok(!options.tools.some(t=>['world_submit','node_list','node_tools','node_invoke'].includes(t.function?.name??t.name)));
   for(const name of ['node_read','world_messages','datanet_memory_read','datanet_memory_write'])assert.ok(options.tools.some(t=>(t.function?.name??t.name)===name));
   const texts=options.messages.flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).join('\n');
   assert.ok(texts.includes('第1天-早'),'time text must be admitted before the first NPC request');
   assert.equal(texts.split('[初始处境]').length-1,1,'opening is ordinary input, delivered once across steps');
   assert.ok(texts.includes('砍树出售木材'),'opening motivation reaches the first real native request');
   assert.ok(texts.includes('你是一位伐木工') && texts.includes('你是一位男性居民'));
   const system=options.messages.filter(m=>m.role==='system').flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).join('\n');
   assert.equal(system.split('# 小镇常识（只读）').length-1,1);
   assert.ok(system.includes('本世界的居民不需要睡觉'),'world common must be automatic system input');
   assert.ok(texts.includes('# 小镇地图')&&texts.includes('| 矿坑 | 铁匠铺 |'),'full map must be in maintained context');
   assert.ok(!system.includes('# 小镇地图'),'map belongs to context, not system input');
   assert.ok(!texts.includes('你目前正在怀孕') && !texts.includes('预产时刻'));
   const calls=options.messages.filter(m=>m.role==='assistant').flatMap(m=>m.content.filter(b=>b.type==='tool-call'));
   const last=calls.at(-1)?.name;
   const direct=options.tools.find(t=>(t.function?.name??t.name).startsWith('near_chop_'));assert.ok(direct,'local action must be assembled before the first request');
   const call=!calls.some(c=>c.name.startsWith('near_chop_'))?{name:direct.function?.name??direct.name,arguments:{}}:null;
   const block=call?{type:'tool-call',id:'npc-'+this.requests.length,name:call.name,arguments:JSON.stringify(call.arguments)}:{type:'text',text:'本时刻砍树计划已完成，正常结束。'};
   yield {type:'block-start',index:0,blockType:block.type};
   if(!call)yield {type:'text-delta',index:0,text:block.text};
   yield {type:'block-end',index:0,block};
   yield {type:'usage',usage:{inputTokens:10,outputTokens:2}};
   yield {type:'finish',reason:{kind:'stop'}};
  }
 }
 const model=new Model();host.llm.registerAdapter(['mock'],model);
 const root=await host.agentLoop.create(native('dsh-session').SessionId('npc-pulse-root'),{provider:'mock',model:'mock'},{cwd:temp});
 await host.parallel('agent/created',{agent:root});
 const r=controller.runtimes.get(root.id);
 const exec=async(name,args={})=>{const result=await host.tools.execute({agent:root,name,arguments:args,callId:'npc-'+name,signal:new AbortController().signal});assert.equal(result.isError,false,JSON.stringify(result));return result.value};
 await r.bridge.call('node_metadata_set',{actor:'root',target:'world/npc/woodcutter',namespace:'compatibility',values:{memory_style:'concise'}});
 const first=await exec('world_run_npc',{target:'world/npc/woodcutter'});
 const report=first.pulse.reports[0];assert.equal(report.returned,true);assert.equal(report.status,'completed');
 assert.deepEqual(JSON.parse(JSON.stringify(report.layers)),[['world/time'],['world/npc/woodcutter'],['world/savepoint'],['world/pulse']]);
 const worker=r.sessions.get('world/npc/woodcutter').handle.agent;
 assert.equal(worker.session.snapshotEvents().findLast(e=>e.type==='turn/end').data.reason.kind,'completed');
 const profileMessages=worker.session.deriveMessages().filter(m=>m.source?.kind==='datanet-instructions'&&m.content.some(b=>b.type==='text'&&(/\[提示文档：|\[按需知识\]|\[当前元数据：/).test(b.text)));
 assert.equal(profileMessages.length,5,'four independent documents plus one current metadata snapshot');
 const metadataMessage=profileMessages.find(m=>m.content.some(b=>b.type==='text'&&b.text.includes('[当前元数据：')));
 assert.ok(metadataMessage,'unified metadata must be injected through the history channel');
 const metadataText=metadataMessage.content.filter(b=>b.type==='text').map(b=>b.text).join('\n');
 assert.ok(metadataText.includes('memory_style')&&metadataText.includes('concise'),'matcher must automatically include the optional metadata namespace');
 assert.ok(metadataText.includes('woodcutter'),'NPC provider metadata must coexist with optional static metadata');
 assert.equal(new Set(profileMessages.map(m=>m.source.document)).size,5,'no repeated instruction copies across model steps');
 assert.equal(worker.session.snapshotEvents().filter(e=>e.type==='system/message').length,1,'identical assembled system text must not create repeated system updates');
 assert.ok(model.requests.every(o=>o.messages.some(m=>m.role==='system'&&m.content.some(b=>b.type==='text'&&b.text.includes('你是阿森。')))),'read-only personality must use the system prompt surface');
 assert.ok(!(await r.bridge.call('application/view',{actor:'world/npc/woodcutter'})).prompt.includes('伐木工'),'profession must not rewrite the role system prompt');
 assert.deepEqual(JSON.parse(JSON.stringify(Object.values(report.deliveries[1].value.executions[0].results).map(s=>s.operation))),['collect_information','assemble_tools','run_agent']);
 const world=await exec('world_observe',{});
 assert.equal(world.actors['world/npc/woodcutter'].inventory.wood,2);assert.equal(world.actors['world/npc/woodcutter'].inventory.axe,2);
 assert.equal(world.activities['world/npc/woodcutter'].status,'completed');
 assert.equal(model.requests.length,2);assert.ok(!host.tools.schemas(worker).some(t=>t.name==='world_submit'));
 const tails=worker.session.snapshotEvents().filter(e=>e.type==='datanet/request-tail');assert.ok(tails.length>=2);
 assert.ok(tails.every(e=>JSON.stringify(e.data.messages).includes('第1天-早')));
 if(durable){
   const point=await r.checkpoints.checkpoint();assert.ok(point,r.checkpoints.status().deferred??r.checkpoints.status().error);
   await assert.rejects(()=>r.checkpoints.positions.read({...point.contexts.root,prefix_hash:'corrupt'}),/checksum mismatch/);
   await assert.rejects(()=>r.checkpoints.positions.read({...point.contexts.root,event_count:999999}),/shorter/);
   const checkpointModule=await get(pathToFileURL(base+'/adapters/harness/framework/checkpoints.js').href);
   const detached=new checkpointModule.namespace.NativeCheckpoints(host,new Map([['root',{agent:root}]]),(method,args)=>r.bridge.call(method,args));
   const sleeping=await detached.checkpoint();assert.equal(sleeping.id,point.id,'unmounted residents reuse their verified durable positions');await detached.stop();
   const same=await r.checkpoints.checkpoint();assert.equal(same.id,point.id,'unchanged state and logs reuse the point');
   const before=await r.bridge.call('persistence_info');
   await r.bridge.call('agent_progress',{target:'root',checkpoint_test:1});
   const coreOnly=await r.checkpoints.checkpoint();assert.notEqual(coreOnly.id,point.id);
   assert.deepEqual(coreOnly.contexts,point.contexts,'core-only change reuses every log position');
   assert.equal((await r.bridge.call('persistence_info')).executor_cursor_count,before.executor_cursor_count,'no duplicate cursor object');
   worker.session.append('user/message',llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'AFTER_SAVED_POINT'}]}),{surfaceOp:'append'});
   const logOnly=await r.checkpoints.checkpoint();assert.equal(logOnly.commit_id,coreOnly.commit_id,'context-only changes are saved without a core change');assert.ok(logOnly.contexts['world/npc/woodcutter'].event_count>point.contexts['world/npc/woodcutter'].event_count);
   assert.equal((await r.bridge.call('persistence_info')).executor_cursor_count,before.executor_cursor_count+1);
   const recovered=await r.restorePoint(point.id,path.join(temp,'recovered-network'));
   assert.equal(recovered.executor_restore.status,'complete');
   assert.notEqual(recovered.root_session_id,root.id);
   const child=await host.sessionPersistence.open(recovered.sessions['world/npc/woodcutter'],'read');
   try{
     const read=await child.read();
     assert.equal(child.inheritedEventCount,point.contexts['world/npc/woodcutter'].event_count);
     assert.ok(!JSON.stringify(read.events).includes('AFTER_SAVED_POINT'));
     assert.ok(JSON.stringify(read.events).includes('near_chop_'));
   }finally{await child.close();}
   assert.ok((await host.sessionPersistence.stat(worker.id)),'original source log remains');
   console.log('PASS durable native checkpoints: disk-backed 7 sessions, unchanged/core-only cursor reuse, log-only update, exact prefix fork and independent core recovery');
 }
 // A non-assembler host producer can feed actual files into all four native input surfaces.
 const directFile=path.join(temp,'direct-input.md');await fs.writeFile(directFile,'External document smoke test.');
 const directPatch={system_prompt:{file:directFile},context:[{id:'direct-guide',text:{file:directFile}}],inputs:[{id:'direct-event',text:{file:directFile},delivery:'followup'}],tail:[{file:directFile}]};
 await r.bridge.call('application/inputs',{actor:'world/npc/woodcutter',source:'external-test',patch:directPatch});await worker.whenIdle();
 assert.equal(model.requests.length,3,'one new event causes exactly one new request');
 const latest=model.requests.at(-1);
 assert.ok(latest.messages.some(m=>m.role==='system'&&m.content.some(b=>b.type==='text'&&b.text.includes('External document smoke test.'))));
 assert.ok(worker.session.deriveMessages().some(m=>m.source?.kind==='nexarbor-input'&&m.source.event==='direct-event'));
 assert.ok(worker.session.deriveMessages().some(m=>m.source?.kind==='datanet-instructions'&&m.content.some(b=>b.type==='text'&&b.text.includes('External document smoke test.'))));
 assert.ok(worker.session.snapshotEvents().findLast(e=>e.type==='datanet/request-tail').data.messages.some(m=>m.content.some(b=>b.type==='text'&&b.text==='External document smoke test.')));
 const systemCount=worker.session.snapshotEvents().filter(e=>e.type==='system/message').length;
 await r.bridge.call('application/inputs',{actor:'world/npc/woodcutter',source:'external-test',patch:directPatch});await worker.whenIdle();
 assert.equal(model.requests.length,3,'repeating the same event must not wake another turn');
 assert.equal(worker.session.snapshotEvents().filter(e=>e.type==='system/message').length,systemCount,'identical file input must not cause another system update');
 // Same application, native error ending must never be mistaken for ready/completed.
 model.fail=true;
 const failed=await exec('world_run_npc',{target:'world/npc/woodcutter'});
 assert.equal(failed.pulse.reports[0].returned,false);assert.equal(failed.pulse.reports[0].status,'partial');
 const after=await exec('world_observe',{});
 assert.equal(after.activities['world/npc/woodcutter'].status,'unavailable');
 assert.equal(after.actors['world/npc/woodcutter'].inventory.wood,2);
 if(durable){
   const original=await r.checkpoints.checkpoint();assert.ok(original);
   await r.bridge.call('node_clock_advance',{target:'world/time',signal_id:'host-topology-test'});
   await r.bridge.call('node_activity_start',{target:'world/npc/woodcutter',signal_id:'host-topology-test'});
   await r.bridge.call('scene_action',{actor:'world/npc/woodcutter',target:'world/place/shop',module:'world.address',name:'move_here',arguments:{}});
   await r.bridge.call('node_activity_end',{target:'world/npc/woodcutter',signal_id:'host-topology-test',status:'completed'});
   const changed=await r.checkpoints.checkpoint();assert.ok(changed);assert.notEqual(changed.commit_id,original.commit_id);
   assert.deepEqual(changed.contexts,original.contexts,'real topology edits do not duplicate unchanged native positions');
   const bundle=await r.bridge.call('persistence_export',{point_id:changed.id});
   assert.ok(bundle.document.network.nodes.find(n=>n.node_id==='world/npc/woodcutter').connections.read_interfaces.some(e=>e.target_node_id==='world/place/shop'));
   console.log('PASS topology-only checkpoint: immediate movement edges saved while every native log position stayed unchanged');
 }
 if(durable){
   // The actual native loop writes the open tool; never manufacture lifecycle events.
   const originalCall=r.bridge.call.bind(r.bridge);let tested=false;
   model.checkpointMode=true;model.checkpointRequests=0;
   r.bridge.call=async(method,args,...rest)=>{
    if(method==='application/invoke'&&args.actor==='root'&&args.name==='world_observe'){
     for(let i=2;i<=5;i++)await originalCall('node_savepoint_arrive',{target:'world/savepoint',signal_id:'savepoint-fixture-'+i});
     assert.equal((await originalCall('persistence_info')).full_snapshot_requested,true);
     assert.equal(await r.checkpoints.checkpoint(),null,'open native tool must defer full publication');
     assert.match(r.checkpoints.status().deferred,/awaiting durable result/);tested=true;
    }
    return originalCall(method,args,...rest);
   };
   try{
    root.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'Run the checkpoint fixture.'}]}));await root.whenIdle();
   }finally{r.bridge.call=originalCall;model.checkpointMode=false;}
   assert.equal(tested,true);assert.equal(model.checkpointRequests,2);
   const full=await r.checkpoints.checkpoint();assert.ok(full);assert.equal(full.kind,'full');
   assert.equal((await r.bridge.call('persistence_info')).full_snapshot_requested,false);
   const bundle=await r.bridge.call('persistence_export',{point_id:full.id});
   assert.equal(bundle.document.network.nodes.find(n=>n.node_id==='world/savepoint').modules['checkpoint.counter'].state.count,5);
   await r.checkpoints.positions.read(full.contexts.root);
   console.log('PASS fifth signal full checkpoint: open tool defers, durable result releases full point with all native cursors');
 }
 if(durable){
   model.movementMode=true;model.movementRequests=0;
   const beforeMove=worker.session.seq;
   const moved=await exec('world_run_npc',{target:'world/npc/woodcutter'});
   model.movementMode=false;
   assert.equal(moved.pulse.reports[0].status,'completed');assert.equal(moved.pulse.reports[0].returned,true);
   assert.equal(moved.activities['world/npc/woodcutter'].status,'completed');
   assert.equal(model.movementRequests,4,'failed move can be corrected and work continues after moving');
   const events=worker.session.snapshotEvents(beforeMove);
   const results=events.filter(e=>e.type==='tool/result');
   const resultText=id=>JSON.stringify(results.find(e=>e.data.message.toolCallId===id)?.data.message);
   assert.match(resultText('move-0-0'),/additional|未声明|unexpected|参数|schema|valid/i);
   assert.match(resultText('move-1-0'),/action_budget/);
   assert.match(resultText('move-2-0'),/action_budget/);
   assert.match(resultText('move-1-1'),/no longer reachable|DATANET_TOOL_PERMISSION_DENIED/);
   assert.equal(events.findLast(e=>e.type==='turn/end').data.reason.kind,'completed');
   const state=await exec('world_observe',{target:'world/npc/woodcutter'});
   assert.equal(state.resident.place,'world/place/forest');
   assert.equal(state.resident.inventory.wood,4);
   const budgetNode=(await r.bridge.call('persistence_export',{point_id:(await r.checkpoints.checkpoint()).id})).document.network.nodes.find(n=>n.node_id==='world/npc/woodcutter');
   assert.equal(budgetNode.modules['action.budget'].state.spent,9);
   const point=await r.checkpoints.checkpoint();assert.ok(point);
   const saved=await r.checkpoints.positions.read(point.contexts['world/npc/woodcutter']);
   assert.ok(saved.events.some(e=>e.type==='tool/result'&&JSON.stringify(e.data).includes('action_budget')),'budget receipt is durable before turn completion');
   console.log('PASS movement: bad arguments corrected, stale batch entry rejected, movement then work share budget, normal finish and durable receipt');
 }
 if(durable){
   model.directMoveMode=true;model.directMoveRequests=0;
   const moved=await exec('world_run_npc',{target:'world/npc/woodcutter'});model.directMoveMode=false;
   assert.equal(model.directMoveRequests,3);assert.equal(moved.pulse.reports[0].status,'completed');
   assert.equal(moved.pulse.reports[0].returned,true);
   const state=await exec('world_observe',{target:'world/npc/woodcutter'});assert.equal(state.resident.place,'world/place/shop');assert.equal(state.resident.inventory.wood,3);
   const steps=Object.values(moved.pulse.reports[0].deliveries[1].value.executions[0].results);
   assert.deepEqual(JSON.parse(JSON.stringify(steps.map(s=>s.operation))),['collect_information','assemble_tools','run_agent']);
   assert.ok(steps[0].value.items.some(x=>x.label==='本地'&&x.fields['名称']==='树林'));
   const point=await r.checkpoints.checkpoint();assert.ok(point);
   await r.checkpoints.positions.read(point.contexts['world/npc/woodcutter']);
   console.log('PASS direct move: destination refresh supplies trade tool in same tick, sale succeeds, native normal completion and durable log');
 }
 if(durable){
   // Genuine bounded Mock turns make every test session nonblank through the
   // native lifecycle. Never fabricate turn/start events or edit session headers.
   model.catalogMode=true;
   const observed=await exec('world_observe',{});
   const rows=[{actor:'root',session:root.session,name:'根节点'}];
   host.sessionTitle.rename(root.session,'行动值最小测试（Mock） · 根节点');
   for(const [actor,entry] of r.sessions){
    const npc=entry.handle.agent,name=observed.actors[actor]?.name??actor;
    host.sessionTitle.rename(npc.session,'行动值最小测试（Mock） · '+name);
    const ended=await exec('world_run_npc',{target:actor});assert.equal(ended.pulse.reports[0].status,'completed');
    rows.push({actor,session:npc.session,name});
   }
   root.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'仅检查会话列表，回复一句确认即可。'}]}));await root.whenIdle();
   for(const row of rows)await host.sessions.flush(row.session);
   const point=await r.checkpoints.checkpoint();assert.ok(point);
   const catalog=[];
   for(const row of rows){
    assert.notEqual(row.session.header.origin,'subagent','native sidebar excludes native subagent sessions');
    assert.ok(row.session.snapshotEvents().some(e=>e.type==='turn/start'),'native sidebar excludes blank sessions');
    const saved=await host.sessionPersistence.open(row.session.id,'read');
    try{
     const log=await saved.read();assert.ok(log.events.some(e=>e.type==='session/title'));
     assert.ok(log.events.some(e=>e.type==='turn/start'));
    }finally{await saved.close();}
    catalog.push({actor:row.actor,session_id:row.session.id,name:row.name,origin:row.session.header.origin??null,events:row.session.seq,title:host.sessionTitle.get(row.session).title});
   }
   await fs.writeFile(path.join(temp,'sessions-manifest.json'),JSON.stringify({kind:'native-mock',workspace:temp,native_logs:path.join(temp,'native-logs'),root_session:root.id,point,sessions:catalog},null,2));
   console.log('PASS sidebar: root and all '+r.sessions.size+' NPC sessions have durable titles, real Mock turns and visible native headers');
   console.log('TEST_CLIENT_RUN '+temp);
 }
 await controller.components.dispose();await host.fiber.dispose();clearInterval(keepAlive);
 console.log('PASS native Harness NPC pulse: channel response sequence, stable role and personality prompt, explicit context-node sources, independent history documents, resident clock, location tool, natural completion, return to source, native error rejected; no model API calls');
})().catch(error=>{console.error(error);process.exit(1)});
