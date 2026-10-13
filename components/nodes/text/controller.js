import {createHash} from 'node:crypto';

const empty={type:'object',properties:{},additionalProperties:false};
export const QUERY_DESCRIPTION='读取该查询文本，将当前正文加入上下文；需要时再次查询。';
export const WRITE_DESCRIPTION='写入有写入连接的常驻文本。target只能选择这些常驻文本节点；只有一个目标时可省略。';
const toolId=id=>'query_text_'+createHash('sha256').update(id).digest('hex').slice(0,16);

export class SharedTexts {
  constructor({bridge,register,instructions,scope,on=(ac,event,fn)=>ac.on(event,fn)}){Object.assign(this,{bridge,register,instructions,scope,on});this.states=new WeakMap();}
  params(ac){const s=this.scope(ac);return {actor:s.actor,strength:s.maxStrength};}
  attach(ac,agent){
    if(this.states.has(ac))return;
    this.states.set(ac,{agent,queries:new Map(),writer:null,targets:[]});
    this.on(ac,'agent/prepare-context',async()=>{await this.sync(ac);});
    this.on(ac,'agent/request-tail',async(_payload,next)=>{
      const previous=await next();
      const {texts}=await this.bridge.call('resident_texts',this.params(ac));
      return [...previous,...texts.map(({text})=>({role:'user',content:[{type:'text',text}]}))];
    });
  }
  async sync(ac){
    const state=this.states.get(ac);if(!state)return;
    const bindings=await this.bridge.call('text_bindings',this.params(ac));
    const active=new Set();
    for(const node of bindings.read.filter(n=>n.delivery==='query')){
      active.add(node.node_id);
      if(state.queries.has(node.node_id))continue;
      const dispose=this.register(ac,toolId(node.node_id),node.label+'\n'+QUERY_DESCRIPTION,empty,async()=>{
        const result=await this.bridge.call('query_text',{...this.params(ac),target:node.node_id});
        if(result.status&&result.status!=='ok')throw new Error(JSON.stringify(result));
        return {node_id:node.node_id,instructions_added:this.instructions.load(ac,'query-text:'+node.node_id,result.text)};
      });
      state.queries.set(node.node_id,dispose);
    }
    for(const [id,dispose] of state.queries)if(!active.has(id)){dispose();state.queries.delete(id);}
    state.targets=bindings.write.map(n=>n.node_id);
    if(state.targets.length&&!state.writer){
      // Keep the declaration stable; the framework checks the current target set at dispatch.
      state.writer=this.register(ac,'write_resident_text',WRITE_DESCRIPTION,{type:'object',properties:{target:{type:'string',description:'有写入连接的常驻文本节点ID。'},content:{type:'string'},mode:{type:'string',enum:['upsert','append'],default:'upsert'}},required:['content'],additionalProperties:false},async p=>{
        const target=p.target??(state.targets.length===1?state.targets[0]:undefined);
        if(!target||!state.targets.includes(target))throw new Error('请选择有写入连接的常驻文本节点');
        const result=await this.bridge.call('write_resident_text',{...this.params(ac),...p,target});
        if(result.status&&result.status!=='ok')throw new Error(JSON.stringify(result));
        return result;
      });
    }else if(!state.targets.length&&state.writer){state.writer();state.writer=null;}
  }
  async syncAll(agents){for(const ac of agents)await this.sync(ac);}
  async project(ac,groupId,ids){
    if(ids.every(id=>this.instructions.has(ac,"query-text:"+id)))return;
    const result=await this.bridge.call('load_project',{...this.params(ac),group_id:groupId});
    if(result.status!=='ok')throw new Error(JSON.stringify(result));
    for(const node of result.items){
      const label='['+node.name+'：'+node.node_id+']'+(node.description?'('+node.description+')':'');
      this.instructions.load(ac,'query-text:'+node.node_id,label+'\n'+node.content);
    }
  }
}
