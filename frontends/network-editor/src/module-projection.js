// Module cards are derived canvas objects. They never enter network.nodes.
export const moduleViewId=(node,module)=>'module-view:'+encodeURIComponent(node)+':'+encodeURIComponent(module);
const list=value=>typeof value==='string'?[value]:value??[];
export function moduleChannelGroups(module,definition){
 const declared=definition.frontend?.channel_groups;
 if(declared)return declared.map(group=>({label:group.label,channels:list(module.config?.[group.field]??definition.schema?.properties?.[group.field]?.default??[]),mode:module.config?.channel_modes?.[group.field]??'allow'}));
 return [{label:'访问',channels:list(module.channels),mode:module.channel_mode??'allow'}];
}
export function projectModules(document,catalog,layout,nodes,edges){
 const cards=[],byOwner=new Map(),base=new Map(nodes.map(node=>[node.id,node]));
 for(const owner of document.network.nodes){
  let index=0;
  for(const module of owner.tables?.modules??[]){
   const definition=catalog.modules?.[module.module_id];
   if(definition?.frontend?.display_as!=='subnode')continue;
   const id=moduleViewId(owner.node_id,module.module_id),groups=moduleChannelGroups(module,definition),height=28;
   const origin=base.get(owner.node_id)?.position??{x:0,y:0};
   const node={id,type:'network',width:72,height,measured:{width:72,height},position:layout[id]??{x:origin.x+110,y:origin.y+index*(height+20)},selectable:false,deletable:false,
    data:{kind:'亚节点',host:owner,module_id:module.module_id,channelGroups:groups,viewHeight:height,
     node:{node_id:id,type:'module_view',name:definition.label??module.module_id,description:definition.description??'',tables:{modules:[]},links:[]}}};
   index++;cards.push(node);if(!byOwner.has(owner.node_id))byOwner.set(owner.node_id,[]);byOwner.get(owner.node_id).push(node);
  }
 }
 const connections=edges.map(edge=>{
  const candidates=(byOwner.get(edge.source)??[]).filter(card=>edge.metadata.channels.length&&edge.metadata.channels.every(channel=>card.data.channelGroups.some(group=>group.mode==='allow'&&group.channels.includes(channel))));
  return candidates.length===1?{...edge,source:candidates[0].id}:edge;
 });
 return {nodes:[...nodes,...cards],edges:[...connections,...cards.map(card=>({id:'ownership:'+card.id,source:card.data.host.node_id,target:card.id,ownership:true,metadata:{channels:[]}}))]};
}
export function moduleConnection(connection,nodes){
 const source=nodes.find(n=>n.id===connection.source)?.data,target=nodes.find(n=>n.id===connection.target)?.data;
 const selected=source?.channelGroups?.find(group=>group.label===connection.sourceHandle)??target?.channelGroups?.find(group=>group.label===connection.targetHandle);
 return {...connection,source:source?.host?.node_id??connection.source,target:target?.host?.node_id??connection.target,...(selected?{channels:selected.channels}:{})};
}

export function modulePerspective(scene,focus){
 const card=focus&&scene.nodes.find(node=>node.id===moduleViewId(focus.owner,focus.module));
 if(!card)return null;
 const host=card.data.host.node_id,groups=card.data.channelGroups;
 const owners=new Map(scene.nodes.map(node=>[node.id,node.data.host?.node_id??node.id]));
 const universe=[...new Set([...scene.edges.flatMap(edge=>edge.metadata.channels),...groups.flatMap(group=>group.channels)])];
 const accepts=(channels,mode,channel)=>mode==='deny'?!channels.includes(channel):channels.includes(channel);
 const edges=scene.edges.filter(edge=>!edge.ownership&&owners.get(edge.source)===host).flatMap(edge=>{
  const channels=universe.filter(channel=>groups.some(group=>accepts(group.channels,group.mode,channel))&&accepts(edge.metadata.channels,edge.metadata.attributes?.channel_mode,channel));
  return channels.length?[{...edge,source:card.id,metadata:{...edge.metadata,channels,attributes:{...edge.metadata.attributes,channel_mode:'allow'}}}]:[];
 });
 const ids=new Set([host,card.id,...edges.map(edge=>edge.target)]);
 return {nodes:scene.nodes.filter(node=>ids.has(node.id)),edges:[...edges,...scene.edges.filter(edge=>edge.ownership&&edge.target===card.id)]};
}
