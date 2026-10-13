import {permissionError} from '../../../adapters/harness/framework/tool-permissions.js';
import {randomUUID} from 'node:crypto';
import {mkdir,readFile,writeFile,rename} from 'node:fs/promises';
import path from 'node:path';

export const SEND_DESCRIPTION='向自己的管理者或直接被管理的 Agent 发信；运行中插话，空闲时唤醒。';
export const REPLY_DESCRIPTION='仅用来回复此条消息，调用一次后失效';
const contentSchema={type:'string',minLength:1};
const object=(properties,required)=>({type:'object',properties,required,additionalProperties:false});

// One durable receipt is one reply capability. A reply creates a new receipt.
export class MessageRouter {
  constructor(directory,{bindings,register,message,canSend,guide='',load=()=>false,onWake=()=>{},onError=()=>{},on=(ac,event,fn)=>ac.on(event,fn),section=(ac,def)=>ac.systemPrompt.section(def),received=()=>{},ttl=30*60*1000,clock=Date.now}) {
    if(!Number.isFinite(ttl)||ttl<=0)throw new Error('Reply lifetime must be positive');
    Object.assign(this,{directory,bindings,register,message,canSend,guide,load,onWake,onError,on,section,received,ttl,clock});
    this.file=path.join(directory,'messages.json');this.entries={};this.agents=new Map();this.surfaces=new Map();this.timers=new Map();this.tail=Promise.resolve();this.closed=false;
  }
  enqueue(fn){const p=this.tail.then(fn);this.tail=p.catch(()=>{});return p;}
  async init(){await mkdir(this.directory,{recursive:true});try{const db=JSON.parse(await readFile(this.file,'utf8'));if(db.version!==1)throw new Error('Unsupported message store');this.entries=db.messages;}catch(e){if(e.code!=='ENOENT')throw e;}for(const e of Object.values(this.entries))if(e.status==='pending'&&e.expires_at<=this.clock())e.status='expired';await this.save();}
  async save(){const tmp=this.file+'.tmp';await writeFile(tmp,JSON.stringify({version:1,messages:this.entries},null,2),'utf8');await rename(tmp,this.file);}
  binding(id){return this.bindings()[id];}
  manager(id){return this.binding(id)?.manager_id??null;}
  contacts(id){return [this.manager(id),...(this.binding(id)?.managed_ids??[])].filter((v,i,a)=>v&&v!==id&&this.binding(v)&&a.indexOf(v)===i);}
  manages(actor,target,scope='descendants'){if(actor===target)return true;if(scope==='self')return false;if(scope==='children')return this.manager(target)===actor;const seen=new Set();for(let p=this.manager(target);p&&!seen.has(p);p=this.manager(p)){if(p===actor)return true;seen.add(p);}return false;}
  pending(actor){return Object.values(this.entries).filter(e=>e.to===actor&&e.status==='pending'&&e.expires_at>this.clock());}
  attach(actor,agent){
    this.detach(actor);this.agents.set(actor,agent);this.surfaces.set(actor,{agent,send:null,replies:new Map()});
    this.section(agent.ctx,{name:'datanet:messages',order:89.1,interpolate:false,text:()=>{
      const pending=this.pending(actor);return [this.canSend(actor)?'可主动联系：'+JSON.stringify(this.contacts(actor)):'',pending.length?'待回复消息：'+JSON.stringify(pending.map(e=>({message_id:e.id,from:e.from,reply_tool:e.reply_tool,expires_at:new Date(e.expires_at).toISOString()}))):''].filter(Boolean).join('\n');
    }});
    this.refresh(actor);
    // Admission is synchronous but the process may stop after persisting a receipt.
    // Restore only messages absent from both durable history and the native inbox.
    const seen=new Set([...(agent.session.deriveMessages?.()??[]),...(agent.inbox?.nextTurn??[]),...(agent.inbox?.nextStep??[])].map(m=>m.id));
    for(const e of this.pending(actor))if(e.message&&!seen.has(e.inbox_id)){
      if(agent.status==='idle')this.onWake(actor,agent);
      agent.steer(e.message);
    }
    this.on(agent.ctx,'agent/inbox/discarded',({message})=>{for(const e of this.pending(actor))if(e.inbox_id===message.id)this.enqueue(async()=>{e.status='discarded';await this.save();this.refresh(actor);}).catch(this.onError);});
  }
  detach(actor){const s=this.surfaces.get(actor);if(s){s.send?.();for(const dispose of s.replies.values())dispose();}this.surfaces.delete(actor);this.agents.delete(actor);}
  refresh(actor){
    const s=this.surfaces.get(actor);if(!s)return;
    if(this.canSend(actor)&&!s.send)s.send=this.register(s.agent.ctx,'datanet_send_message',SEND_DESCRIPTION,object({target:{type:'string',minLength:1},content:contentSchema},['target','content']),(p,exec)=>{this.authority(actor,exec);this.load(s.agent.ctx,'tool:datanet_messages',this.guide);return this.send(actor,p.target,p.content);});
    if(!this.canSend(actor)&&s.send){s.send();s.send=null;}
    const available=new Map(this.pending(actor).map(e=>[e.id,e]));
    for(const [id,dispose] of s.replies)if(!available.has(id)){dispose();s.replies.delete(id);clearTimeout(this.timers.get(id));this.timers.delete(id);}
    for(const [id,e] of available){if(!s.replies.has(id))s.replies.set(id,this.register(s.agent.ctx,e.reply_tool,REPLY_DESCRIPTION,object({content:contentSchema},['content']),(p,exec)=>{this.authority(actor,exec);this.load(s.agent.ctx,'tool:datanet_messages',this.guide);return this.reply(actor,id,p.content);}));this.arm(e);}
  }
  authority(actor,exec){if(exec?.agent&&exec.agent!==this.agents.get(actor))throw new Error('Message tool belongs to another Agent');}
  arm(e){if(this.timers.has(e.id))return;const timer=setTimeout(()=>{this.timers.delete(e.id);this.enqueue(async()=>{if(e.status==='pending'){e.status='expired';await this.save();this.refresh(e.to);}}).catch(this.onError);},Math.max(1,e.expires_at-this.clock()));timer.unref?.();this.timers.set(e.id,timer);}
  send(actor,target,content){return this.enqueue(async()=>{if(!this.canSend(actor))throw permissionError('datanet_send_message');if(!this.contacts(actor).includes(target))throw new Error('Target is outside Agent management contacts');return this.deliver(actor,target,content);});}
  reply(actor,id,content){return this.enqueue(async()=>{
    const original=this.entries[id];if(!original||original.to!==actor)throw new Error('Reply belongs to another Agent');
    if(original.status!=='pending'||original.expires_at<=this.clock())throw permissionError(original.reply_tool);
    return this.deliver(actor,original.from,content,original);
  });}
  async deliver(from,to,content,original){
    if(this.closed)throw new Error('Message router is closed');
    if(typeof content!=='string'||!content.trim())throw new Error('Message content is required');
    const sender=this.agents.get(from),receiver=this.agents.get(to);if(!sender||!receiver)throw new Error('Target Agent is not mounted; message was not accepted');
    const id=randomUUID(),e={id,from,to,content,status:'pending',created_at:this.clock(),expires_at:this.clock()+this.ttl,reply_tool:'datanet_reply_'+id.replaceAll('-',''),...(original?{reply_to:original.id,communication_id:original.communication_id}: {communication_id:id})};
    const message=this.message(sender,e);e.inbox_id=message.id;e.message=message;
    this.entries[id]=e;if(original)original.status='replied';
    try{await this.save();this.received({actor:to,agent:receiver,message:e});this.refresh(to);this.refresh(from);if(receiver.status==='idle')this.onWake(to,receiver);receiver.steer(message);}
    catch(error){delete this.entries[id];if(original)original.status='pending';await this.save();this.refresh(to);this.refresh(from);throw error;}
    return {status:'accepted',communication_id:e.communication_id,message_id:id,inbox_message_id:e.inbox_id};
  }
  async close(){this.closed=true;for(const timer of this.timers.values())clearTimeout(timer);for(const actor of [...this.agents.keys()])this.detach(actor);await this.tail;}
}
