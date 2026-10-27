// Verify a completed pulse against native log prefixes; never rewind the source logs.
const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const keepAlive=setInterval(()=>{},1000);
(async()=>{
 const source=path.resolve(process.argv[2]),output=path.resolve(process.argv[3]),root=path.resolve(__dirname,'../..');
 const loader=await require(path.join(root,'adapt/harness/native/loader.cjs'))(),{Context}=loader.native('cordis');
 const {NativePositions,canonical}=await loader.load(path.join(root,'adapt/harness/framework/checkpoints.js'));
 const {durableEvent}=await loader.load(path.join(root,'adapt/harness/runtime/session-events.js'));
 const ctx=new Context(),persistence=loader.native('dsh-session-persistence-jsonl');await ctx.plugin(persistence.default??persistence,{root:path.join(source,'native-logs')});
 try{
  const document=JSON.parse(await fs.readFile(path.join(source,'verified-tick-16.json'),'utf8'));
  const pulse=document.network.nodes.find(n=>n.type==='pulse');assert.equal(pulse.parameters.state.sequence,16);assert.equal(pulse.parameters.state.phase,'completed');assert.equal(pulse.parameters.state.active_signal,null);
  const wave=document.signals[pulse.parameters.state.last_signal];assert.equal(wave.status,'completed');assert.equal(wave.signal.sequence,16);
  const cutoff=wave.finished_at*1000,positions=new NativePositions(ctx),contexts={},rows=[];
  for(const [actor,binding]of Object.entries(document.agents)){
   await positions.read(binding.context_cursor);
   const handle=await ctx.sessionPersistence.open(binding.session_id,'read');
   try{
    const {events}=await handle.read();let count=0;while(count<events.length&&events[count].time<=cutoff)count++;
    const before=events.slice(0,count),last=before.at(-1),pending=new Set();let digest=binding.context_cursor.header_hash;
    assert.equal(last.type,'turn/end');assert.equal(last.data.reason.kind,'completed');
    for(const [i,e]of before.entries()){
     assert.equal(e.seq,i);digest=crypto.createHash('sha256').update(digest+'\n'+canonical(durableEvent(e))).digest('hex');
     if(e.type==='assistant/message')for(const b of e.data.message.content??[])if(b.type==='tool-call')pending.add(b.id);
     if(e.type==='tool/call')pending.add(e.data.callId);if(e.type==='tool/result')pending.delete(e.data.message.toolCallId);
    }
    assert.equal(pending.size,0);assert.ok(events.slice(count).every(e=>e.time>cutoff));
    const cursor={...binding.context_cursor,event_count:count,prefix_hash:digest};await positions.read(cursor);contexts[actor]=cursor;
    rows.push({actor,event_count:count,last_turn_end:last.seq,completed:true,unpaired_tools:0,next_event_time:events[count]?.time??null});
   }finally{await handle.close();}
  }
  await fs.writeFile(output,JSON.stringify({passed:true,cutoff,contexts,rows},null,2));console.log(JSON.stringify({passed:true,cutoff,rows}));
 }finally{await ctx.fiber.dispose();}
})().finally(()=>clearInterval(keepAlive)).catch(e=>{console.error(e);process.exitCode=1;});
