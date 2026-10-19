import fs from 'node:fs/promises';import path from 'node:path';
import {assemblyTownDocument,assemblyTownTemplates} from './context-town.mjs';
const kinds=['system_prompt','context','inputs','tail'];
const channel=c=>kinds.includes(c)?'context.assembler.'+c:c==='context.assemble'?'context.assembler':c;
export function subnodeTownDocument(document,{template=false}={}){
 const initial=assemblyTownDocument(document,{template}),doc=initial.document,nodes=doc.network.nodes,by=new Map(nodes.map(n=>[n.node_id,n])),before=JSON.stringify(doc);
 for(const group of nodes){const assembly=group.modules?.['context.assembler'];if(!assembly||group.type==='subnode')continue;const actor=by.get(assembly.config.bindings?.[0]?.node);if(!actor||!group.node_id.startsWith('context/'))continue;
  group.type='subnode';group.data_kind=null;group.divergence=0;group.parameters={parent_id:actor.node_id,use_parent_links:false,share_links:false};group.connections.interfaces=group.connections.interfaces.filter(e=>!(e.target_node_id===actor.node_id&&e.metadata.channels.includes('records')));
  assembly.config.bindings[0].node='$parent';assembly.config.channels=['context.assembler'];for(const kind of kinds)assembly.config[kind+'_channels']=['context.assembler.'+kind];assembly.access.channels=[...new Set(assembly.access.channels.map(channel))];
  for(const edge of group.connections.interfaces)edge.metadata.channels=edge.metadata.channels.map(channel);
  actor.connections.interfaces=actor.connections.interfaces.filter(e=>e.target_node_id!==group.node_id);
  for(const ref of actor.execution?.prepare??[])if(ref.node===group.node_id&&ref.module==='context.assembler')delete ref.channels;
  const input=actor.inputs?.['prepare:'+group.node_id+':context.assembler:assemble'];if(input)for(const event of input.inputs??[])if(event.id==='agents.context.opening')event.id='node:'+group.node_id+'/opening/'+event.id;
 }
 for(const node of nodes){const movement=node.modules?.['movement.here'];if(movement){movement.config.location_channels=[...new Set([...(movement.config.location_channels??['movement','tools']),'tools.collector'])];}
 for(const edge of node.connections.interfaces)if(edge.metadata.channels.includes('movement')&&!edge.metadata.channels.includes('tools.collector'))edge.metadata.channels.push('tools.collector');
  if(node.modules?.['context.text']){node.modules['context.text'].access.channels=[...new Set([...node.modules['context.text'].access.channels.map(channel)])];}
  const collector=node.modules?.['tools.collector'];if(node.type!=='agent'||!collector)continue;const id='tools/'+node.node_id;if(by.has(id))continue;
  const sub={type:'subnode',node_id:id,name:node.name+' · 工具收集',description:'',management_parent_id:null,divergence:0,module_strength:0,data_kind:null,parameters:{parent_id:node.node_id,use_parent_links:true,share_links:false},connections:{interfaces:[]},agent:null,modules:{'tools.collector':collector},offered_tools:[],toolboxes:[],expose:[],execution:null,inputs:null,context_cursor:null};collector.config.channels=['tools.collector'];collector.access.channels=[...new Set([...collector.access.channels.filter(c=>c!=='tools'),'tools.collector'])];delete node.modules['tools.collector'];nodes.push(sub);by.set(id,sub);node.execution.tool_sources=[...new Set([...(node.execution.tool_sources??[]),id])];node.execution.channels=[...new Set([...node.execution.channels,'tools.collector'])];
 }
 return {document:doc,changed:initial.changed||JSON.stringify(doc)!==before};
}
export function subnodeTownTemplates(templates=[]){return assemblyTownTemplates(templates).map(t=>({...t,document:subnodeTownDocument(t.document,{template:true}).document}));}

export async function updateTownSubnodes(rpc,directory){
 const marker=path.join(directory,'town-subnodes-v1.json');try{await fs.access(marker);return;}catch(e){if(e.code!=='ENOENT')throw e;}
 const catalog=await rpc('studio_catalog');if(!catalog.library['context.assembler']||!catalog.library['places.query']||!catalog.library['agents.memory'])return;
 const state=await rpc('studio_state'),live=subnodeTownDocument(state.live.document),draft=state.draft?subnodeTownDocument(state.draft.document):null;
 if(live.changed||draft?.changed){await fs.writeFile(path.join(directory,'before-town-subnodes-v1.json'),JSON.stringify(state));if(live.changed){const value=await rpc('studio_apply',{document:live.document,base_commit:state.live.commit,layout:state.draft?.layout??{}});if(!value.valid)throw Error('亚节点迁移校验失败：'+JSON.stringify(value));}if(state.draft&&!state.draft.applied){const now=await rpc('studio_state');await rpc('studio_draft',{document:draft.document,expected_version:now.draft?.version??0,base_commit:now.live.commit,layout:state.draft.layout??{}});}}
 const file=path.join(directory,'workspace-session.json');let workspace;try{workspace=JSON.parse(await fs.readFile(file,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
 if(workspace?.document){const converted=subnodeTownDocument(workspace.document);if(converted.changed){await fs.writeFile(path.join(directory,'before-subnode-workspace.json'),JSON.stringify(workspace));workspace.document=converted.document;workspace.base_commit=(await rpc('studio_state')).live.commit;const temporary=file+'.subnodes.tmp';await fs.writeFile(temporary,JSON.stringify(workspace));await fs.rename(temporary,file);}}
 await fs.writeFile(marker,JSON.stringify({changed:live.changed,version:1}));
}
