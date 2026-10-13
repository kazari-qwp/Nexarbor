export const REPORT_DESCRIPTIONS = Object.freeze({
  channel:'查询你发起的委托或获准归档范围内的报告。进入后加载报告结构、索引用法和专用读取工具；这是普通查询入口，不启动排障或重试。',
  query:'按请求、委托或节点查询获授权报告索引及实际委托拓扑，返回可直接读取的相对路径；不返回报告正文。省略请求和委托时查询当前请求。',
  read:'按索引路径读取获授权报告文件，或读取按权限过滤的 node-index.json、topology.json。长文件按字符分页；路径不扩大权限。'
});
const object=(properties,required=[])=>({type:'object',properties,required,additionalProperties:false});
const str={type:'string',minLength:1};
const offset={type:'integer',minimum:0};
export class ReportChannel {
  constructor(store,{actor,load,register,guide,enter=(ac,p,next)=>next()}){this.enter=enter;this.store=store;this.actor=actor;this.load=load;this.register=register;this.guide=guide;this.unlocked=new WeakSet();this.opened=new WeakSet();}
  restore(ac){const actor=this.actor(ac);if(this.store.hasDelegated(actor)||this.store.hasArchiveGrant(actor))this.unlock(ac);}
  unlock(ac){if(this.unlocked.has(ac))return;this.unlocked.add(ac);this.register(ac,'datanet_reports_channel',REPORT_DESCRIPTIONS.channel,object({root_request_id:str,delegation_id:str}),p=>this.enter(ac,p,()=>this.open(ac,p)));}
  open(ac,p={}){
    if(!this.unlocked.has(ac))throw new Error('Report channel is not granted');
    const added=this.load(ac,'tool:datanet_reports',this.guide);
    if(!this.opened.has(ac)){this.opened.add(ac);
      this.register(ac,'datanet_reports_query',REPORT_DESCRIPTIONS.query,object({root_request_id:str,delegation_id:str,node_id:str,offset,limit:{type:'integer',minimum:1,maximum:50}}),args=>{
        const current=this.store.context(ac);return this.store.query(this.actor(ac),{...args,root_request_id:args.root_request_id??(args.delegation_id?undefined:current?.root_request_id)});
      });
      this.register(ac,'datanet_report_read',REPORT_DESCRIPTIONS.read,object({root_request_id:str,path:str,offset,limit:{type:'integer',minimum:1,maximum:20000}},['root_request_id','path']),args=>this.store.read(this.actor(ac),args));
    }
    const current=this.store.context(ac);
    return {tools:['datanet_reports_query','datanet_report_read'],instructions_added:added,...(p.root_request_id??current?.root_request_id?{root_request_id:p.root_request_id??current.root_request_id}:{}),...(p.delegation_id?{delegation_id:p.delegation_id}:{}),indices:['node-index.json','topology.json']};
  }
}
