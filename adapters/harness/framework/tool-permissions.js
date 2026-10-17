const DENIED='DATANET_TOOL_PERMISSION_DENIED';
const marker=`[${DENIED}]`;
export const permissionReason=name=>`${marker} ${name} 当前已停用。`;
export function permissionError(name){const error=new Error(permissionReason(name));error.code=DENIED;return error;}
export function isPermissionDenied(result){
  return result?.code===DENIED||result?.value?.code===DENIED||result?.error?.message?.startsWith(marker)||
    (result?.isError&&result.content?.some(b=>b.type==='text'&&(b.text.startsWith(marker)||b.text.startsWith('Error: '+marker))));
}

// Keep declarations stable within a series; successful compaction reclaims revoked schemas.
export class ToolPermissions {
  constructor(message){this.message=message;this.states=new WeakMap();}
  state(ac){
    let s=this.states.get(ac);if(s)return s;
    s={tools:new Map(),notices:[],official:new Set(),officialSeen:new Set(),managed:false};this.states.set(ac,s);
    ac.tools.guard(exec=>{
      if(exec.agent?.ctx&&exec.agent.ctx!==ac)return;
      const local=s.tools.get(exec.name);
      if(local?.enabled===false||!local&&s.managed&&exec.name!=='run_code'&&!s.official.has(exec.name))return s.refusals?.[exec.name]??permissionReason(exec.name);
    });
    ac.on('agent/tool-schemas',async(_payload,next)=>{
      const tools=await next();
      return s.managed?tools.filter(tool=>s.tools.has(tool.name)||s.officialSeen.has(tool.name)||tool.name==='run_code'):tools;
    });
    ac.on('agent/pre-step',async(_payload,next)=>{
      const decision=await next();if(decision.kind!=='enter'||!s.notices.length)return decision;
      const message=this.message({source:{kind:'user'},content:[{type:'text',text:'[DataNet 工具权限]\n'+s.notices.join('\n')}]});
      s.notices=[];return {...decision,messages:[...decision.messages,message]};
    });
    return s;
  }
  bind(ac,agent){
    const s=this.state(ac);if(s.agent)return;
    s.agent=agent;
    ac.on('session/event',(session,event)=>{
      if(session!==agent.session||event.type!=='compaction/end'||event.data?.error!==undefined)return;
      this.rebase(ac);
    });
  }
  refusals(ac,reasons){this.state(ac).refusals=reasons;}
  onRebase(ac,callback){this.state(ac).rebaseOfficial=callback;}
  rebase(ac){
    const s=this.state(ac);if(!s.agent)return;
    // A retained call/result still needs its declaration, but never its permission.
    const referenced=new Set();
    for(const message of s.agent.session.deriveMessages())for(const block of message.content??[]){
      if(block.type==='tool-call')referenced.add(block.name);
    }
    for(const [name,record] of s.tools){
      if(referenced.has(name))continue;
      if(!record.enabled){record.dispose();s.tools.delete(name);}
      else if(record.definition!==record.registered){record.dispose();this.install(ac,record);}
    }
    s.officialSeen=new Set([...s.officialSeen].filter(name=>s.official.has(name)||referenced.has(name)));
    s.rebaseOfficial?.([...s.officialSeen]);
  }
  install(ac,record){
    const definition=record.definition;
    record.dispose=ac.tools.register({...definition,execute:(args,exec)=>{
      if(!record.enabled)throw permissionError(definition.name);
      return record.execute(args,exec);
    }});
    record.registered=definition;
  }
  notify(ac,name,enabled){this.state(ac).notices.push(`${name} ${enabled?'已恢复，可以调用。':'已停用，当前不能调用。'}`);}
  register(ac,definition){
    const s=this.state(ac);let record=s.tools.get(definition.name);
    if(!record){
      record={enabled:true,execute:definition.execute,definition,lease:0};s.tools.set(definition.name,record);
      this.install(ac,record);
    }else{
      record.execute=definition.execute;record.definition=definition;
      if(!record.enabled){record.enabled=true;this.notify(ac,definition.name,true);}
    }
    const lease=++record.lease;
    return ()=>{
      if(s.tools.get(definition.name)!==record||record.lease!==lease||!record.enabled)return;
      record.enabled=false;this.notify(ac,definition.name,false);
    };
  }
  official(ac,names){
    const s=this.state(ac),next=new Set(names),retained=new Set([...s.officialSeen,...next]);
    for(const name of s.official)if(!next.has(name))this.notify(ac,name,false);
    for(const name of next)if(s.officialSeen.has(name)&&!s.official.has(name))this.notify(ac,name,true);
    s.official=next;s.officialSeen=retained;s.managed=true;return [...retained];
  }
}
