const DENIED='DATANET_TOOL_PERMISSION_DENIED';
const marker=`[${DENIED}]`;
export const permissionReason=name=>`${marker} ${name} 当前已停用。`;
export function permissionError(name){const error=new Error(permissionReason(name));error.code=DENIED;return error;}
export function isPermissionDenied(result){
  return result?.code===DENIED||result?.value?.code===DENIED||result?.error?.message?.startsWith(marker)||
    (result?.isError&&result.content?.some(b=>b.type==='text'&&(b.text.startsWith(marker)||b.text.startsWith('Error: '+marker))));
}

// Keep declarations stable; capability changes only affect execution and tail messages.
export class ToolPermissions {
  constructor(message){this.message=message;this.states=new WeakMap();}
  state(ac){
    let s=this.states.get(ac);if(s)return s;
    s={tools:new Map(),notices:[],official:new Set(),officialSeen:new Set(),managed:false};this.states.set(ac,s);
    ac.tools.guard(exec=>{
      if(exec.agent?.ctx&&exec.agent.ctx!==ac)return;
      const local=s.tools.get(exec.name);
      if(local?.enabled===false||!local&&s.managed&&exec.name!=='run_code'&&!s.official.has(exec.name))return permissionReason(exec.name);
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
  notify(ac,name,enabled){this.state(ac).notices.push(`${name} ${enabled?'已恢复，可以调用。':'已停用，当前不能调用。'}`);}
  register(ac,definition){
    const s=this.state(ac);let record=s.tools.get(definition.name);
    if(!record){
      record={enabled:true,execute:definition.execute,lease:0};s.tools.set(definition.name,record);
      ac.tools.register({...definition,execute:(args,exec)=>{
        // Also protects direct dispatchers that do not provide an Agent identity.
        if(!record.enabled)throw permissionError(definition.name);
        return record.execute(args,exec);
      }});
    }else{
      record.execute=definition.execute;
      if(!record.enabled){record.enabled=true;this.notify(ac,definition.name,true);}
    }
    const lease=++record.lease;
    return ()=>{
      if(record.lease!==lease||!record.enabled)return;
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
