const keepAlive=setInterval(()=>{},1000);setTimeout(()=>{console.error('Recovery deadline');process.exit(1)},30000).unref();
// Offline recovery of an accidentally truncated native branch. No model or tools run.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
(async()=>{
 const [directory,parentId,branchId,output]=process.argv.slice(2);assert(directory&&parentId&&branchId&&output);
 const loader=await require('../adapt/harness/native/loader.cjs')(),native=loader.native,{Context}=native('cordis'),ctx=new Context();
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry']])await ctx.plugin(native(name)[service]);const persistence=native('dsh-session-persistence-jsonl');await ctx.plugin(persistence.default??persistence,{root:path.join(directory,'native-logs')});
 try{
  const {NativePositions}=await loader.load(path.resolve('adapt/harness/framework/checkpoints.js'));const positions=new NativePositions(ctx),parent=await positions.exportPrefix(await positions.captureStored(parentId)),branch=await positions.exportPrefix(await positions.captureStored(branchId));
  assert.equal(branch.header.parentSession,parentId);let common=0;while(common<Math.min(parent.events.length,branch.events.length)&&JSON.stringify(parent.events[common])===JSON.stringify(branch.events[common]))common++;
  const start=branch.events.findIndex(e=>e.time>=branch.header.createdAt);assert(start>=common&&common>0);
  const suffix=structuredClone(branch.events.slice(start)),allowed=new Set(['session/end-seed','session/title','agent/inbox/spliced','turn/start','turn/end','step/start','step/end','user/message','assistant/message','tool/call','tool/result','request/header','datanet/request-tail']);
  const turns=parent.events.map(e=>e.data?.turn).filter(Number.isInteger),first=suffix.find(e=>e.type==='turn/start');assert(first);const shift=Math.max(...turns)-first.data.turn+1;
  const {Session,buildForkSeed}=native('dsh-session'),merged=buildForkSeed(parent.events,parent.events.length-1);
  for(const event of suffix){assert(allowed.has(event.type),'Unsupported event requires an explicit recovery: '+event.type);if(event.type==='session/title')assert.equal(event.data.messageSeqs.length,0);if(Number.isInteger(event.data?.turn))event.data.turn+=shift;event.seq=merged.length;merged.push(event);}
  const id='nexarbor-history-recovered-'+crypto.randomUUID(),header={...parent.header,id,createdAt:Date.now(),parentSession:parentId,isSeeded:true};
  const seed=buildForkSeed(merged,merged.length-1),session=Session.create(id,seed,header,merged.length),actual=session.deriveMessages();
  const left=Session.create(parentId,parent.events,parent.header,parent.cursor.inherited_event_count).deriveMessages(),right=Session.create(branchId,branch.events,branch.header,branch.cursor.inherited_event_count).deriveMessages(),expected=new Map([...left,...right].map(m=>[m.id,m]));
  assert.equal(actual.length,expected.size);for(const m of actual)assert.deepEqual(m,expected.get(m.id));assert.deepEqual(actual.slice(0,left.length),left);
  const {durableSessionHandle}=await loader.load(path.resolve('adapt/harness/runtime/session-events.js')),handle=durableSessionHandle(await ctx.get('sessionPersistence').create(header,{inheritedEventCount:merged.length}));try{await handle.append(seed);await handle.flush();}finally{await handle.close();}
  const cursor=await positions.captureStored(id),report={paid_api_calls:0,source_sessions:[parentId,branchId],common_events:common,branch_live_start:start,turn_shift:shift,parent_messages:left.length,branch_messages:right.length,recovered_messages:actual.length,all_original_messages_exact:true,parent_prefix_exact:true,cursor};await fs.writeFile(output,JSON.stringify(report,null,2));console.log(JSON.stringify({...report,cursor:{session_id:cursor.session_id,event_count:cursor.event_count}}));
 }finally{await ctx.fiber.dispose();clearInterval(keepAlive);}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
