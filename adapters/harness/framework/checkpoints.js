// Native log positions and prefix forks; core stores opaque cursor references only.
import {createHash,randomUUID} from 'node:crypto';
import {buildForkSeed} from '@deepseek-ai/dsh-session';
import {durableEvent,durableSessionHandle} from '../runtime/session-events.js';

export const canonical=value=>JSON.stringify(sort(value));
function sort(value){if(Array.isArray(value))return value.map(sort);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,sort(value[k])]));return value;}
const hash=value=>createHash('sha256').update(typeof value==='string'?value:canonical(value)).digest('hex');
const chain=(previous,event)=>hash(previous+'\n'+canonical(durableEvent(event)));
const headerHash=header=>hash({...header,delegationDepth:header.delegationDepth??0});

// A point between a tool effect and its durable result is not an advertised recovery point.
function updatePending(pending,event){
  if(event.type==='assistant/message')for(const block of event.data.message.content??[])if(block.type==='tool-call')pending.add(block.id);
  if(event.type==='tool/call')pending.add(event.data.callId);
  if(event.type==='tool/result')pending.delete(event.data.message.toolCallId);
}

export class NativePositions{
  constructor(ctx){this.ctx=ctx;this.cache=new WeakMap();}
  async capture(session,{allowPending=false}={}){
    const persistence=this.ctx.get('sessionPersistence');
    if(!persistence)throw new Error('Native session persistence is not mounted');
    const count=session.seq,header=headerHash(session.header),old=this.cache.get(session);
    if(old&&old.cursor.event_count===count&&old.cursor.header_hash===header){if(old.pending.size&&!allowPending)return null;if(old.cursor.adapter)return old.cursor;}
    const start=old&&old.cursor.header_hash===header&&old.cursor.event_count<=count?old.cursor.event_count:0;
    const pending=new Set(start?old.pending:[]);let digest=start?old.cursor.prefix_hash:header;
    const suffix=session.snapshotEvents(start,count);
    for(const event of suffix){digest=chain(digest,event);updatePending(pending,event);}
    // Ordinary global points wait for results; exclusive node snapshots may retain an open-tool prefix.
    if(pending.size&&!allowPending){this.cache.set(session,{cursor:{header_hash:header,event_count:count,prefix_hash:digest},pending});return null;}
    const flushed=await this.ctx.sessions.flush(session);
    if(flushed===false)throw new Error('Native session has no durability writer');
    const cursor={adapter:'deepseek-harness',version:1,session_id:session.id,header_hash:header,event_count:count,prefix_hash:digest,inherited_event_count:session.inheritedEventCount,log:persistence.locate?.(session.header)??{kind:'native'}};
    this.cache.set(session,{cursor,pending});return cursor;
  }
  async captureStored(sessionId){
    const persistence=this.ctx.get('sessionPersistence');if(!persistence)throw Error('Native session persistence is not mounted');
    const handle=await persistence.open(sessionId,'read');
    try{
      const {events}=await handle.read();let digest=headerHash(handle.header);
      for(const [index,event] of events.entries()){if(event.seq!==index)throw Error('Native log prefix is not contiguous');digest=chain(digest,event);}
      return {adapter:'deepseek-harness',version:1,session_id:sessionId,header_hash:headerHash(handle.header),event_count:events.length,prefix_hash:digest,inherited_event_count:handle.inheritedEventCount,log:persistence.locate?.(handle.header)??{kind:'native'}};
    }finally{await handle.close();}
  }
  async read(cursor){
    if(cursor?.adapter!=='deepseek-harness'||cursor.version!==1||!Number.isSafeInteger(cursor.event_count)||cursor.event_count<0)throw new Error('Invalid Harness recovery position');
    const persistence=this.ctx.get('sessionPersistence');if(!persistence)throw new Error('Native session persistence is not mounted');
    const handle=await persistence.open(cursor.session_id,'read');
    try{
      if(headerHash(handle.header)!==cursor.header_hash||handle.inheritedEventCount!==cursor.inherited_event_count)throw new Error('Native session header/generation mismatch');
      const {events}=await handle.read(0,cursor.event_count);
      if(events.length!==cursor.event_count)throw new Error('Native log is shorter than its saved position');
      let digest=cursor.header_hash;for(const [i,event] of events.entries()){if(event.seq!==i)throw new Error('Native log prefix is not contiguous');digest=chain(digest,event);}
      if(digest!==cursor.prefix_hash)throw new Error('Native log prefix checksum mismatch');
      return {header:structuredClone(handle.header),events};
    }finally{await handle.close();}
  }
  async fork(cursor,id='datanet-recovery-'+randomUUID()){
    const {header,events}=await this.read(cursor),seed=events.length?buildForkSeed(events,events.length-1):[];
    const child={...header,id,createdAt:Date.now(),parentSession:cursor.session_id,isSeeded:true};
    const handle=durableSessionHandle(await this.ctx.get('sessionPersistence').create(child,{inheritedEventCount:events.length}));
    try{if(seed.length)await handle.append(seed);await handle.flush();}finally{await handle.close();}
    return id;
  }
}

export class NativeCheckpoints{
  constructor(ctx,native,call){this.ctx=ctx;this.native=native;this.call=call;this.positions=new NativePositions(ctx);this.detached=new Map();this.ready=false;this.closed=false;this.dirty=false;this.last=null;this.error=null;this.deferred=null;}
  schedule(){
    if(!this.ready||this.closed)return;
    this.dirty=true;if(this.timer||this.running)return;
    this.timer=setTimeout(()=>{this.timer=null;this.drain().catch(error=>{this.error=String(error.message??error);});},25);this.timer.unref?.();
  }
  async drain(){
    if(this.running)return this.running;
    this.running=(async()=>{while(this.dirty&&!this.closed){this.dirty=false;await this.capture();}})();
    try{return await this.running;}finally{this.running=null;}
  }
  async capture(kind='incremental'){
    const info=await this.call('persistence_info');
    if(info.executor_restore_required&&Object.keys(info.executor_restore_required).length){this.deferred='executor restoration pending';return null;}
    if(info.pending.length){this.deferred='uncertain core operation';return null;}
    if(info.node_locks_preparing){this.deferred='node snapshots preparing';return null;}
    const contexts={},counts=[];let previous=this.last;
    for(const [actor,id] of Object.entries(info.bindings)){
      if(info.locked_contexts?.[actor]){contexts[actor]=info.locked_contexts[actor];continue;}
      const entry=this.native.get(actor);
      if(!entry){
        previous??=await this.call('persistence_latest_point');
        const saved=previous?.contexts?.[actor];
        if(saved?.session_id!==id){this.deferred='Agent mount in progress';return null;}
        if(this.detached.get(actor)!==saved.prefix_hash){await this.positions.read(saved);this.detached.set(actor,saved.prefix_hash);}
        contexts[actor]=saved;continue;
      }
      if(entry.agent.session.id!==id){this.deferred='Agent mount in progress';return null;}
      const cursor=await this.positions.capture(entry.agent.session);
      if(!cursor){this.deferred='tool call awaiting durable result';return null;}
      contexts[actor]=cursor;counts.push([entry.agent.session,cursor.event_count]);
    }
    if(counts.some(([session,count])=>session.seq!==count)){this.deferred='native log changed during capture';return null;}
    try{
      const point=await this.call('persistence_checkpoint',{expected_commit:info.commit_id,bindings:info.bindings,contexts,kind});
      this.last=point;this.error=null;this.deferred=null;return point;
    }catch(error){
      if(/changed during|Network changed|Uncertain operations/.test(String(error))){this.deferred='state changed during capture';return null;}
      throw error;
    }
  }
  async checkpoint(kind='incremental'){
    if(this.closed)throw new Error('Checkpoint coordinator stopped');
    if(!this.ctx.get('sessionPersistence'))throw new Error('Native session persistence is not mounted');
    if(this.timer){clearTimeout(this.timer);this.timer=null;}
    await this.drain();
    this.running=this.capture(kind);
    try{return await this.running;}finally{this.running=null;if(this.dirty)this.schedule();}
  }
  status(){return {last:this.last,error:this.error,deferred:this.deferred};}
  async stop(){this.closed=true;if(this.timer)clearTimeout(this.timer);await this.running?.catch(()=>{});}
}
