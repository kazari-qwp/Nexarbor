// 旧小镇的可逆数据迁移。通用模块中没有 NPC ID、时钟名或世界规则。
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const hash=s=>createHash('sha256').update(s).digest('hex').slice(0,16);
const mount=(config,channels,strength=4,state={})=>({config,state,access:{strength,channels}});
const edge=(target,channels)=>({target_node_id:target,metadata:{channels,threshold:1,multiplier:1,attributes:{}}});
function node(id,name,type='node'){return {type,node_id:id,name,description:'',management_parent_id:null,divergence:-1,data_kind:type==='text_file'?'text':'none',parameters:{},connections:{interfaces:[]},agent:null,modules:{},offered_tools:[],toolboxes:[],expose:[],execution:null,context_cursor:null,inputs:null};}
export function assemblyTownDocument(document,{template=false}={}){
 const doc=structuredClone(document),nodes=doc.network?.nodes??[],added=[],files=doc.files??={},by=new Map(nodes.map(n=>[n.node_id,n]));
 const actors=nodes.filter(n=>n.type==='agent'&&n.modules?.['agents.context']);if(!actors.length)return {document:doc,changed:false};
 if(!template&&(!by.has('world/time')||!by.has('place/home1')))return {document:doc,changed:false};
 const add=n=>{if(!by.has(n.node_id)){added.push(n);by.set(n.node_id,n)};return by.get(n.node_id)};
 function text(id,name,value,config={}){const t=node(id,name,'text_file');t.parameters.file_path='context/'+hash(id)+'.md';files[t.parameters.file_path]=value;t.modules['context.text']=mount(config,['system_prompt','context','inputs','tail'],0);return add(t);}
 for(const actor of actors){
  const old=actor.modules['agents.context'],c=old.config??{},state=old.state??{},groupId='context/'+actor.node_id;
  const group=add(node(groupId,actor.name+' · 上下文'));
  const config={sources:[],bindings:[{node:actor.node_id,module:'records.store',operation:'read',arguments:{},channels:['records'],pointer:'/values'}],document_roots:[]};
  group.modules['context.assembler']=mount(config,['context.assemble','system_prompt','context','inputs','tail','records'],4);
  group.modules['context.assembler'].access.extension={operations:['read_text'],targets:[]};
  group.connections.interfaces.push(edge(actor.node_id,['records']));
  const link=(t,kind)=>{
   if(template){const value=files[t.parameters.file_path],source={id:t.node_id,kind,type:'text',text:value,...t.modules['context.text'].config};config.sources.push(source);const index=added.indexOf(t);if(index>=0)added.splice(index,1);by.delete(t.node_id);delete files[t.parameters.file_path];}
   else group.connections.interfaces.push(edge(t.node_id,[kind]));
  };
  link(text(groupId+'/persona',actor.name+' · 人格',c.persona??'',{order:0}),'system_prompt');
  let common=c.common??'';
  // 记忆维护属于可见规则，不再由执行器偷偷加一句系统提示词。
  if(!common.includes('私人记忆'))common+='\n需要时主动记录或检索自己的私人记忆，过时信息由你判断。';
  link(text('context/shared/'+hash(common),'世界规则',common,{order:10}),'system_prompt');
  for(const item of c.knowledge??[]){const signature=JSON.stringify([item.id,item.text,item.when]);link(text('context/knowledge/'+hash(signature),item.id,item.text,{order:20,when:item.when??{}}),'context');}
  if(c.opening)link(text(groupId+'/opening',actor.name+' · 开场输入',c.opening,{event_id:'agents.context.opening',order:0}),'inputs');
  const clock=by.get(c.clock);if(clock){
   clock.modules['context.text']??=mount({},['system_prompt','context','inputs','tail'],0);
   const counter=clock.modules['clock.counter'];if(counter){counter.config.write_text=true;counter.config.text_template??='当前时间：第{day}天 {slot}（计数 {tick}）';const tick=counter.state?.tick??counter.config.initial_tick??0,labels=counter.config.labels??['清晨','上午','下午','傍晚','夜晚'],day=tick?Math.floor((tick-1)/labels.length)+1:1,slot=labels[tick?((tick-1)%labels.length):0];files[clock.parameters.file_path]=counter.config.text_template.replaceAll('{day}',String(day)).replaceAll('{slot}',slot).replaceAll('{tick}',String(tick));}
   link(clock,'tail');
  }else if(template&&c.clock){group.connections.interfaces.push(edge(c.clock,['tail']));}
  actor.modules['agents.memory']=mount({max_memories:c.max_memories??100},['self'],0,{memories:structuredClone(state.memories??[])});
  actor.modules['places.query']=mount(Object.fromEntries(['clock','public_fields','map_title','map_layout'].filter(k=>c[k]!==undefined).map(k=>[k,structuredClone(c[k])])),['self','records','movement','info'],12);
  delete actor.modules['agents.context'];
  actor.connections.interfaces.push(edge(groupId,['context.assemble']));
  actor.execution??={executor:'harness',strength:2,channels:['self']};actor.execution.channels=[...new Set([...actor.execution.channels,'context.assemble'])];
  actor.execution.prepare=[...(actor.execution.prepare??[]).filter(p=>p.module!=='agents.context'),{module:'places.query',operation:'publish',arguments:{},channels:['self']},{node:groupId,module:'context.assembler',operation:'assemble',arguments:{},channels:['context.assemble']}];
  for(const item of actor.offered_tools??[])if(item.ref?.startsWith('module:agents.context/'))item.ref=item.ref.replace('agents.context/',/\/(remember|recall)$/.test(item.ref)?'agents.memory/':'places.query/');
  const prior=actor.inputs?.['module:agents.context'];if(prior){actor.inputs['prepare:'+groupId+':context.assembler:assemble']={system_prompt:'',context:[],tail:[],inputs:structuredClone(prior.inputs??[])};delete actor.inputs['module:agents.context'];}
  else if(state.opening_queued&&c.opening){actor.inputs??={};actor.inputs['prepare:'+groupId+':context.assembler:assemble']={system_prompt:'',context:[],tail:[],inputs:[{id:'agents.context.opening',text:c.opening,delivery:'followup',status:'delivered'}]};}
 }
 doc.network.nodes=[...nodes,...added];doc.files=files;return {document:doc,changed:true};
}
export function assemblyTownTemplates(templates=[]){return templates.map(template=>{
 const out=structuredClone(template),result=assemblyTownDocument(out.document,{template:true});if(!result.changed)return out;out.document=result.document;
 // 新生角色的人格替换从旧模块字段迁移到组装器的直接文本来源。
 for(const binding of out.bindings){const marker='/modules/agents.context/config/';if(!binding.path.includes(marker))continue;const field=binding.path.split(marker)[1],actorIndex=Number(binding.path.split('/')[3]),actor=out.document.network.nodes[actorIndex],group=out.document.network.nodes.find(n=>n.node_id==='context/'+actor.node_id),index=out.document.network.nodes.indexOf(group);const source=group.modules['context.assembler'].config.sources.findIndex(s=>s.id.endsWith('/'+(field==='opening'?'opening':'persona')));if(source>=0)binding.path='/network/nodes/'+index+'/modules/context.assembler/config/sources/'+source+'/text';}
 return out;
});}
export function assemblyTownLayout(layout,document){
 const result=structuredClone(layout??{});for(const n of document.network.nodes){if(!n.modules?.['context.assembler'])continue;const actor=n.modules['context.assembler'].config.bindings[0].node,anchor=result[actor];if(anchor&&!result[n.node_id])result[n.node_id]={x:anchor.x-220,y:anchor.y+140};}
 return result;
}
export async function updateTownAssembly(rpc,directory){
 const marker=path.join(directory,'town-assembly-v1.json');try{await fs.access(marker);return;}catch(error){if(error.code!=='ENOENT')throw error;}
 const catalog=await rpc('studio_catalog');if(!catalog.library['context.assembler']||!catalog.library['places.query']||!catalog.library['agents.memory'])return;
 const state=await rpc('studio_state'),live=assemblyTownDocument(state.live.document),draft=state.draft?assemblyTownDocument(state.draft.document):null;
 if(live.changed||draft?.changed){await fs.writeFile(path.join(directory,'before-town-assembly-v1.json'),JSON.stringify(state));
  if(live.changed){const result=await rpc('studio_apply',{document:live.document,base_commit:state.live.commit,layout:assemblyTownLayout(state.draft?.layout,live.document)});if(!result.valid)throw Error('上下文装配迁移失败：'+JSON.stringify(result));}
  if(state.draft&&!state.draft.applied){const current=await rpc('studio_state');await rpc('studio_draft',{document:draft.document,expected_version:current.draft?.version??0,base_commit:current.live.commit,layout:assemblyTownLayout(state.draft.layout,draft.document)});}
 }
 const file=path.join(directory,'workspace-session.json');let workspace;try{workspace=JSON.parse(await fs.readFile(file,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
 if(workspace?.document){const update=assemblyTownDocument(workspace.document);if(update.changed){await fs.writeFile(path.join(directory,'before-town-assembly-workspace-v1.json'),JSON.stringify(workspace));workspace.document=update.document;workspace.layout=assemblyTownLayout(workspace.layout,update.document);workspace.base_commit=(await rpc('studio_state')).live.commit;const tmp=file+'.assembly.tmp';await fs.writeFile(tmp,JSON.stringify(workspace));await fs.rename(tmp,file);}}
 await fs.writeFile(marker,JSON.stringify({version:1,changed:live.changed}));
}
