import {createHash} from 'node:crypto';

// Documents are ordinary history messages; tool grants have a separate lifetime.
export class InstructionHistory {
  constructor(message){this.message=message;this.states=new WeakMap();}
  bind(ac,agent){
    if(this.states.has(ac))return;
    const state={agent,loaded:new Map()};this.states.set(ac,state);
    for(const message of agent.session.deriveMessages()){
      const source=message.source;
      if(source?.kind==='datanet-instructions')state.loaded.set(source.document,{digest:source.digest,message,pending:false});
    }
    ac.on('agent/pre-step',async(_payload,next)=>{
      const decision=await next();if(decision.kind!=='enter')return decision;
      const documents=[];
      for(const record of state.loaded.values())if(record.pending){documents.push(record.message);record.pending=false;}
      return documents.length?{...decision,messages:[...decision.messages,...documents]}:decision;
    });
    ac.on('session/event',(session,event)=>{
      if(session.id!==agent.session.id||event.type!=='compaction/end'||event.data?.error)return;
      this.prune(ac);
    });
  }
  has(ac,id){return this.states.get(ac)?.loaded.has(id)??false;}
  load(ac,id,text){
    const state=this.states.get(ac);if(!state)throw new Error('Instruction history is not mounted');
    const digest=createHash('sha256').update(text).digest('hex');
    const before=state.loaded.get(id);
    if(before?.digest===digest&&(before.pending||state.agent.session.deriveMessages().some(m=>m.id===before.message.id)))return false;
    const message=this.message({source:{kind:'datanet-instructions',form:'instructions',document:id,digest},content:[{type:'text',text:`[DataNet 文档：${id}]\n${text}`}]});
    state.loaded.set(id,{digest,message,pending:true});return true;
  }
  prune(ac){
    const state=this.states.get(ac);if(!state)return;
    const retained=new Set(state.agent.session.deriveMessages().map(m=>m.id));
    for(const [id,record] of state.loaded)if(!record.pending&&!retained.has(record.message.id))state.loaded.delete(id);
  }
}
